"""The single place every command emits results — `out()` adds shared post-processing to the result."""
from __future__ import annotations

import json
import shlex
import time
from pathlib import Path

from common import troubleshoot
from common.access import needs_verify, record_result
from common.emit import emit
from common.state import repo_unknown

import harness_store
import journal
import knowledge

from pro_launch.runtime.plugin_version import plugin_version, take_newer_installed
from pro_launch.runtime.recent_roots import root_candidates
from pro_launch.runtime.context import ACCESS_CTX, INPUT_CTX, MEMORY_CTX, MIGRATION, OUTPUT_CTX, ROOT_CTX, TARGET_CTX

# skills/pro-launch — where the official troubleshooting (troubleshooting/) lives
SKILL_DIR = Path(__file__).resolve().parents[3]


# Fields to attach to this process's next response (dispatcher-gate warnings about someone else's device, etc.) — attached even if the action code does not know
PENDING_RESPONSE_FIELDS: dict = {}


def add_response_fields(fields: dict) -> None:
    PENDING_RESPONSE_FIELDS.update(fields)


def out(payload: dict) -> int:
    """Add previous results and pending response fields (gate warnings, etc.) to emit. Anything moved must be visible to the user."""
    for key, value in PENDING_RESPONSE_FIELDS.items():
        payload.setdefault(key, value)
    moved = [m for r in MIGRATION.values() for m in r.get("moved", [])]
    warns = [w for r in MIGRATION.values() for w in r.get("warnings", [])]
    if moved:
        payload["migrated"] = moved
    if warns:
        payload["migration_warnings"] = warns
    # summary is always a string (#825) — a None breaks callers' parsing (observed).
    if not payload.get("summary"):
        payload["summary"] = default_summary(payload)
    _root_warning(payload)
    _empty_value_warning(payload)
    _grade_access(payload)
    attach_known_fix(payload)
    _memory_hooks(payload)
    _harness_hooks(payload)
    return emit_shaped(payload)


def default_summary(payload: dict) -> str:
    """When summary is missing: on failure error > first reason > code (never write a failure as "done", #972) · on success "<action> done"."""
    act = payload.get("action")
    if payload.get("ok", True) is False:
        reasons = payload.get("reasons") if isinstance(payload.get("reasons"), list) else []
        cause = payload.get("error") or (reasons[0] if reasons else None)
        label = f"{act} failed" if act else "failed"
        return str(cause) if cause else f"{label}: {payload.get('code') or 'error'}"
    return payload.get("error") or (f"{act} done" if act else "done")


# Leading 4 fields — always first and always kept, so the next action survives truncated reading
HEAD_KEYS = ("ok", "code", "summary", "next")
# One-line failure cause (e.g. render's buried first error) — right after the head · kept in --brief too
CAUSE_KEYS = ("first_error", "unknown", "did_you_mean", "empty_values")
# Fixes, memory, journal and harness for this failure and area — after the cause · kept when trimmed
# journal was missing, so the first --brief call discarded the journal yet consumed it as 'shown today' (projectops#1023)
GUIDANCE_KEYS = ("known_fix", "known_fix_note", "memory", "memory_note", "learn_hint",
                 "journal", "journal_note", "journal_hint", "harness", "harness_note")
# Version + old-install warning on failures and doctor only (including success, once) — kept in reports · kept when trimmed
VERSION_KEYS = ("plugin_version", "newer_installed")
# Main result of read commands (logs lines · web text · ssh/local stdout · db rows · http json/text) — dropping it loses the value read (#1188)
# handoff: the `web signin` hand-over — without it the result has nothing to sign in with (#1231)
PRIMARY_OUTPUT_KEYS = ("lines", "text", "stdout", "stderr", "rows", "json", "handoff")
# Keys --brief keeps: head + error + cause + guidance + version + main result
BRIEF_KEYS = (*HEAD_KEYS, "error", *CAUSE_KEYS, *GUIDANCE_KEYS, *VERSION_KEYS, *PRIMARY_OUTPUT_KEYS)
# Keys kept in --brief on failure — the evidence next points to (#972)
FAILURE_BRIEF_KEYS = ("reasons", "output_tail", "non_device_consumers", "unused_options", "valid_options")
# --fields aliases: requested name > actual key with the same meaning (capture path comes out as file, #972)
FIELD_ALIASES = {"path": "file", "file": "path"}


def shape_payload(payload: dict) -> dict:
    """Shape output: 4-field defaults > plugin_version on failure > order (head > cause > guidance > rest) > --brief · --fields filtering.

    Values are not changed. Without flags the key set stays the same (except plugin_version on failure); only order changes.
    """
    # Defaults (same rule as emit) — if emit appended them later the order would break again
    payload.setdefault("ok", True)
    payload.setdefault("code", "ok" if payload["ok"] else "error")
    payload.setdefault("summary", None)
    payload.setdefault("next", None)
    # Not included in success responses (smaller responses, #897)
    if payload["ok"] is False:
        payload.setdefault("plugin_version", plugin_version())
    newer_installed = take_newer_installed()
    if newer_installed:
        payload.setdefault("newer_installed", newer_installed)
    leading = [k for k in (*HEAD_KEYS, *CAUSE_KEYS, *GUIDANCE_KEYS, *VERSION_KEYS) if k in payload]
    ordered = {k: payload[k] for k in leading}
    ordered.update((k, v) for k, v in payload.items() if k not in ordered)
    field_names = _resolve_field_aliases(OUTPUT_CTX.get("field_names"), ordered)
    kept_names = _kept_key_names(field_names, is_failed=ordered["ok"] is False)
    if kept_names is None:
        return ordered
    return {**{k: v for k, v in ordered.items() if k in kept_names}, **_unknown_field_report(field_names, ordered)}


def _resolve_field_aliases(field_names: list[str] | None, ordered: dict) -> list[str] | None:
    """If the requested key is missing and its alias exists, use the alias (--fields path > file)."""
    if not field_names:
        return field_names
    return [FIELD_ALIASES[name] if name not in ordered and FIELD_ALIASES.get(name) in ordered else name
            for name in field_names]


def _unknown_field_report(field_names: list[str] | None, ordered: dict) -> dict:
    """Keys in --fields that do not exist give {unknown_fields, available_fields} — never a silent empty result (#931)."""
    unknown = [name for name in field_names or [] if name not in ordered]
    if not unknown:
        return {}
    return {"unknown_fields": unknown, "available_fields": list(ordered)}


def _kept_key_names(field_names: list[str] | None, is_failed: bool) -> set[str] | None:
    """Key names kept by --brief · --fields. None when neither is given (keep all); union when both are."""
    is_brief = bool(OUTPUT_CTX.get("is_brief"))
    if not is_brief and not field_names:
        return None
    kept_names = {*HEAD_KEYS, *GUIDANCE_KEYS, *VERSION_KEYS}
    if is_brief:
        kept_names.update(BRIEF_KEYS)
        if is_failed:
            kept_names.update(FAILURE_BRIEF_KEYS)
    if field_names:
        kept_names.update(field_names)
    return kept_names


def emit_shaped(payload: dict) -> int:
    """Shape and emit a single JSON. Arg-error and exception paths that bypass out() use this too."""
    return emit(shape_payload(payload))


def attach_known_fix(payload: dict) -> None:
    """On failure attach official troubleshooting summaries (up to 2) as known_fix. No field when nothing matches.

    Unlike memory there is no daily cap — it is a verified fix for this failure, so it must show every time.
    No error may spoil the command result.
    """
    if payload.get("ok", True) is not False:
        return
    try:
        causes = payload.get("causes") if isinstance(payload.get("causes"), list) else []
        text = " ".join(str(v) for v in (payload.get("error"), payload.get("hint"), *causes) if v)
        fixes = troubleshoot.find_known_fixes(SKILL_DIR, payload.get("code"), text, areas=_failure_areas(payload))
        if fixes:
            payload["known_fix"] = fixes
            payload["known_fix_note"] = "Verified official fix. Try it first; full entry: kb show <id>"
    except Exception:   # noqa: BLE001 — official knowledge is auxiliary
        pass


def _failure_areas(payload: dict) -> tuple[str, ...] | None:
    """Area of this failure (response platform > memory area set by the action). None when unknown (no filtering) — keeps android fixes off iOS failures (#972)."""
    area = payload.get("platform") if payload.get("platform") in troubleshoot.AREAS else MEMORY_CTX.get("area")
    return (area,) if area in troubleshoot.AREAS else None


def _empty_value_warning(payload: dict) -> None:
    """On failure, point at options passed as empty values (bad_viewport: unknown viewport '', etc., #886)."""
    empty = INPUT_CTX.get("empty_values")
    if not empty or payload.get("ok", True) is not False or "empty_values" in payload:
        return
    payload["empty_values"] = empty
    payload["empty_values_note"] = (f"{', '.join(empty)} has an empty value — if you passed $VAR, check that "
                                    "the environment variable is set")


# Common failures from picking the wrong root — attach candidate roots and the command to rerun (#885)
ROOT_SENSITIVE_CODES = {"browser_not_open", "git_not_found"}


def _root_warning(payload: dict) -> None:
    if ROOT_CTX.get("source") == "last_used":
        payload["root_source"] = "last_used"
        payload["root_note"] = (f"Working folder ({ROOT_CTX.get('cwd')}) is not a repo, so the last used {ROOT_CTX.get('path')} was used — "
                                "for another repo add --root <path>")
    if ROOT_CTX.get("scratch"):
        payload["root_scratch"] = True
        payload["root_note"] = (f"{ROOT_CTX.get('path')} has no git and no project marker — state goes to a scratch bucket "
                                "(_scratch/<name>-<hash>) and is not remembered as a recent root. For a project, pass the repo absolute path with --root")
    is_failed = payload.get("ok", True) is False
    if is_failed and (ROOT_CTX.get("not_repo") or ROOT_CTX.get("unknown")
                          or payload.get("code") in ROOT_SENSITIVE_CODES):
        _attach_root_candidates(payload)
    if not ROOT_CTX.get("unknown"):
        return
    payload["root_unknown"] = True
    payload["root_warning"] = (f"Called from a folder with no known project ({ROOT_CTX.get('path')}) — "
                               "state goes to this machine's shared location and no repo memory is written")
    fix = "Call again with --root <project path> (or the PROJECT_ROOT environment variable)"
    nxt = payload.get("next")
    if not nxt:
        payload["next"] = fix
    elif isinstance(nxt, str) and fix not in nxt:
        payload["next"] = f"{fix}. Then: {nxt}"


def _attach_root_candidates(payload: dict) -> None:
    """Candidate roots (those with a live browser first) and retry commands to copy as is."""
    try:
        candidates = root_candidates()
    except Exception:   # noqa: BLE001 — candidates are auxiliary
        return
    current = ROOT_CTX.get("resolved")
    candidates = [c for c in candidates if c["path"] != current]
    if not candidates:
        return
    payload["root_candidates"] = candidates
    # browser_not_open retries only roots with a live browser — sending it elsewhere gives the same error again (#999)
    if payload.get("code") == "browser_not_open":
        # --root named this repo: sending the agent to another repo's live browser drives the wrong project (#1154)
        if ROOT_CTX.get("explicit"):
            return
        live = [c for c in candidates if c.get("has_live_browser")]
        if not live:
            return
        retry_root = live[0]["path"]
    else:
        retry_root = candidates[0]["path"]
    payload["retry"] = retry_command_with_root(retry_root)
    # The browser_not_open retry root has a browser — appending the current root's web open would mix two roots (#999)
    then = payload.get("next") if payload.get("code") != "browser_not_open" else None
    payload["next"] = (f"May have been called outside the repo — retry: {payload['retry']}"
                       + (f". Then: {then}" if then else ""))


def retry_command_with_root(root: str) -> str:
    """One line that reruns this command with --root <root> (the original --root is removed)."""
    raw = list(INPUT_CTX.get("raw") or [])
    kept, index = [], 0
    while index < len(raw):
        if raw[index] == "--root":
            index += 2
            continue
        if not raw[index].startswith("--root="):
            kept.append(raw[index])
        index += 1
    return "launch_cli.py " + " ".join(shlex.quote(token) for token in [*kept, "--root", root])


_ACCESS_FAIL_CODES = {"db_query_failed", "db_timeout", "logs_failed", "logs_timeout",
                      "request_failed"}


# For http, getting any response means the connection method is right — an unexpected status code is a scenario verdict
_ACCESS_OK_CODES = {"ok", "unexpected_status"}


def use_access(root: Path, key: str) -> None:
    """Mark that this command uses the method recorded under key in access. out() records the result."""
    ACCESS_CTX.update(root=root, key=key)


def _grade_access(payload: dict) -> None:
    key = ACCESS_CTX.pop("key", None)
    root = ACCESS_CTX.pop("root", None)
    if not key or root is None:
        return
    code = payload.get("code")
    ok = payload.get("ok", True) is not False and code in (None, *_ACCESS_OK_CODES)
    if not ok and code not in _ACCESS_FAIL_CODES:
        return
    try:
        prev = record_result(root, key, ok, code)
    except Exception:   # noqa: BLE001 — the record is auxiliary
        return
    if needs_verify(prev):
        lf = prev.get("last_fail") or {}
        payload["verify"] = True
        payload["verify_note"] = (f"access '{key}' failed last time ({lf.get('date')}, {lf.get('code')}) — "
                                  + ("it worked this time" if ok else
                                     "it failed again. Re-read the code and fix it with access set"))


_FIX_WINDOW_SEC = 30 * 60   # a success in the same area within this window after a failure may be a 'newly learned method'


def set_area(area: str | None, root: Path | None = None, key_prefix: str | None = None) -> None:
    """key_prefix: attach only memories with this prefix (e.g. per server name `server.<name>.`)."""
    if area in knowledge.AREAS:
        MEMORY_CTX.update(area=area, root=root or MEMORY_CTX.get("root") or Path(".").resolve(),
                           key_prefix=key_prefix)


def _memory_hooks(payload: dict) -> None:
    """Attach memory · learn_hint on success after failure. No error may spoil the command result."""
    area = MEMORY_CTX.get("area")
    # If HOME is relative, records would land under the working folder — skip writing (tests actually did this)
    if not area or not knowledge.base_dir().is_absolute():
        return
    try:
        root = MEMORY_CTX["root"]
        unknown = repo_unknown(root)
        paths = {"machine": knowledge.store_path("machine", root)}
        if not unknown:
            paths["repo"] = knowledge.store_path("repo", root)
        seen_dir = knowledge.store_path("machine" if unknown else "repo", root).parent
        mem = knowledge.surface(paths, area, seen_dir / "memory_seen.json",
                                key_prefix=MEMORY_CTX.get("key_prefix"))
        if mem:
            payload["memory"] = mem
            payload["memory_note"] = ("Methods that worked on this machine. If you used one, record the result with "
                                      f"learn --area {area} --key <key> --how <how> --result ok|fail")
        hint = _track_attempt(seen_dir / "attempts.json", area, payload)
        if hint:
            payload["learn_hint"] = hint
        _journal_hooks(payload, area, root, unknown, seen_dir)
    except Exception:   # noqa: BLE001 — memory is auxiliary. The main command result is emitted even on failure
        pass


def _journal_hooks(payload: dict, area: str, root: Path, unknown: bool, seen_dir: Path) -> None:
    """Work journal — attach recent entries when returning to the same area, and prompt to write one when work ends."""
    path = journal.store_path(root)
    # Failed responses are easily discarded — attach but do not count as 'shown today', so it is attached again on the next success
    rows = journal.surface(path, area, seen_dir / "journal_seen.json", mark=payload.get("ok", True) is not False)
    if rows:
        payload["journal"] = rows
        payload["journal_note"] = ("Earlier work records in this area. Reference only — when repeating the work, reuse "
                                   "the order and decision criteria, but confirm changing actions with the user. "
                                   "Add what changed with journal --add")
    # The moment work ends (closing the window) is the best time to write — ask the user first
    if payload.get("action") == "close" and payload.get("ok", True) is not False and not unknown:
        payload["journal_hint"] = (
            "If this work is likely to be repeated, ask the user \"Shall I record this work?\" and, if they agree, write it with "
            f"journal --add \"<what and why · order · decision criteria · result · what will be confusing next time>\" --title <title> --area {area} "
            "--site <part of the address>. If the user asked for a record first, write it without asking (never write secrets). "
            "For a workflow that repeats, keep the guide and helper scripts in a harness folder: harness new <name> --url <pattern>")


def set_target(url: str | None = None, host: str | None = None, root: Path | None = None,
               area: str | None = None, app: str | None = None, window=None) -> None:
    """URL·host·app·window this command targets. out() attaches matching harnesses to the response (projectops#1023 · #1024).
    app: package name·bundle ID · window: window title·program name (one string or several)."""
    if isinstance(window, (list, tuple)):
        window = [str(w) for w in window if w] or None
    TARGET_CTX.update({k: v for k, v in (("url", url), ("host", host), ("root", root), ("area", area),
                                         ("app", app), ("window", window)) if v})


def _harness_hooks(payload: dict) -> None:
    """Attach the harness (guide) matching this URL·host·app·window. Once a day per harness; not consumed by failed responses."""
    area = TARGET_CTX.get("area") or MEMORY_CTX.get("area")
    if area == harness_store.APP_AREA and MEMORY_CTX.get("area") in harness_store.APP_PLATFORMS:
        area = MEMORY_CTX["area"]   # with a device chosen, filter by platform (ios·android) — so areas: ["ios"] does not attach on Android
    url = TARGET_CTX.get("url")
    if not url and area == "web" and isinstance(payload.get("url"), str) and "://" in payload["url"]:
        url = payload["url"]   # actions on an already-open browser (click · text …) match the current page URL
    host = TARGET_CTX.get("host")
    app = TARGET_CTX.get("app")
    window = TARGET_CTX.get("window")
    if not (url or host or app or window) or not knowledge.base_dir().is_absolute():
        return
    try:
        root = TARGET_CTX.get("root") or MEMORY_CTX.get("root") or Path(".").resolve()
        seen_dir = knowledge.store_path("machine" if repo_unknown(root) else "repo", root).parent
        rows = harness_store.surface(root, seen_dir / harness_store.SEEN_FILE, url=url, host=host, area=area,
                                     mark=payload.get("ok", True) is not False, app=app, window=window)
        if rows:
            payload["harness"] = rows
            payload["harness_note"] = ("A guide for this site or workflow exists. Read its README before repeating the work and "
                                       "follow its loop and human-check points; helper scripts are optional. "
                                       "Full guide: harness show <name>. Update the README when the screen or steps changed")
    except Exception:   # noqa: BLE001 — the guide is auxiliary. The main command result is emitted even on failure
        pass


# Failure > success chain log (#863) — session-check points at "areas that got unstuck but were never learned"
RESOLVED_FILE = "resolved.json"
RESOLVED_KEEP = 20
# Failure codes excluded from the learn_hint chain — condition waits, verdicts and misuse are not new methods to learn
INTENDED_FAILURE_CODES = frozenset({"wait_timeout", "expect_not_met", "unexpected_status", "not_found",
                                    "index_out_of_range", "bad_args", "args_required", "args_invalid",
                                    "missing_argument", "unexpected_argument", "text_required", "value_required",
                                    "target_required"})


def _track_attempt(f: Path, area: str, payload: dict) -> str | None:
    """After a failure then success in the same area, suggest 'record it if this is a newly learned method'.

    The best moment for the agent to leave a memory is right after getting unstuck. The tool points at that moment.
    It counts failures and, once resolved, writes the chain (area · count · last failure code) to resolved.json.
    """
    ok = payload.get("ok", True) is not False and payload.get("code") in (None, "ok")
    # Intended failures (wait timeout · arg error · missing target) are not being stuck — kept out of the chain (#972)
    if not ok and payload.get("code") in INTENDED_FAILURE_CODES:
        return None
    try:
        last = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        last = {}
    now = time.time()
    prev = last.get(area) or {}
    if ok:
        last.pop(area, None)
    else:
        # Old failures outside the window are not this chain — count from scratch
        earlier = int(prev.get("fails") or 1) if prev and now - prev.get("at", 0) < _FIX_WINDOW_SEC else 0
        last[area] = {"code": payload.get("code"), "at": now, "fails": earlier + 1}
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(last), encoding="utf-8")
    except OSError:
        pass
    if not (ok and prev and now - prev.get("at", 0) < _FIX_WINDOW_SEC):
        return None
    fails = int(prev.get("fails") or 1)
    _append_resolved(f.parent / RESOLVED_FILE, {"area": area, "fails": fails,
                                                "last_code": prev.get("code"), "at": now})
    times = f" {fails} times" if fails > 1 else ""
    return (f"Just got past '{prev.get('code')}' after failing{times}. If the method is reusable, record it with "
            f"learn --area {area} --key <short-key> --how '<what and how>' --result ok "
            "(long story: --detail. Do not record missing installs, one-offs or secrets)")


def _append_resolved(f: Path, row: dict) -> None:
    try:
        rows = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        rows = []
    rows = [*(rows if isinstance(rows, list) else []), row][-RESOLVED_KEEP:]
    try:
        f.write_text(json.dumps(rows), encoding="utf-8")
    except OSError:
        pass
