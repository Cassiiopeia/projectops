#!/usr/bin/env python3
"""
ios_release.py

Version decisions for iOS test builds and releases, and Apple upload error interpretation (issue #643).
The only place Apple errors are interpreted. Add new error codes here together with a
real message sample in test_ios_release.py.

Version closing rule: an app version (train) closes the moment it is approved and does not reopen even after developer rejection.
Uploading to a closed version is rejected after a 12-18 minute build, so test builds switch to
the next patch version before building and releases fail immediately.

  - Commands: precheck-version | classify-error | archive-upload
  - Output: always JSON (ok / data / summary / next); logs and ::error:: go to stderr
  - Reasons (reason, reason_line) go into PR comments as is, so they use the repo language (catalog ios_release.*); logs are English (#769)
  - Environments where ASC lookup fails (missing secrets, insufficient permissions) proceed with the version.yml version

Usage:
  python3 ios_release.py precheck-version --mode test --version 2.1.2 --bundle-id com.a.b
  python3 ios_release.py precheck-version --mode test --version 2.1.2 --bundle-id com.a.b --base-version 2.4.0   # stale branch warning (Android test builds use the same command, #1006)
  python3 ios_release.py classify-error --log build/upload_attempt_1.log
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from xml.parsers.expat import ExpatError

sys.path.insert(0, str(Path(__file__).resolve().parent))
import asc_client  # noqa: E402
import build_number  # noqa: E402
from i18n.messages import t as message  # noqa: E402

# Waits live at module level so tests can set them to 0 seconds
sleep = time.sleep

# States after approval. DEVELOPER_REJECTED cannot tell pre-approval withdrawal from post-approval rejection, so it counts as open.
CLOSED_VERSION_STATES = {
    "ACCEPTED", "PENDING_DEVELOPER_RELEASE", "PENDING_APPLE_RELEASE",
    "PROCESSING_FOR_DISTRIBUTION", "READY_FOR_DISTRIBUTION", "REPLACED_WITH_NEW_VERSION",
}
# Old appStoreState values. Same meaning as the new ones plus sales-related states.
CLOSED_STORE_STATES = CLOSED_VERSION_STATES | {
    "READY_FOR_SALE", "PROCESSING_FOR_APP_STORE", "PREORDER_READY_FOR_SALE",
    "DEVELOPER_REMOVED_FROM_SALE", "REMOVED_FROM_SALE",
}

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


# ── Version ──────────────────────────────────────────────────────────────
def parse_version(s: str | None) -> tuple[int, int, int] | None:
    """Accept only 1-3 integers joined by dots. Missing parts become 0; anything else is None."""
    if not s:
        return None
    parts = str(s).strip().split(".")
    if not 1 <= len(parts) <= 3 or not all(p.isdigit() for p in parts):
        return None
    nums = [int(p) for p in parts] + [0] * (3 - len(parts))
    return nums[0], nums[1], nums[2]


def format_version(t: tuple[int, int, int]) -> str:
    return f"{t[0]}.{t[1]}.{t[2]}"


def next_patch(s: str) -> str:
    """Next patch version. ValueError for an unparsable string."""
    t = parse_version(s)
    if t is None:
        raise ValueError(message("ios_release.version_unparsable", value=repr(s)))
    return format_version((t[0], t[1], t[2] + 1))


def closed_max(versions: list[dict]) -> str | None:
    """Highest closed version. Checks both new and old state fields and skips unparsable versions."""
    best: tuple[int, int, int] | None = None
    for v in versions:
        closed = (v.get("appVersionState") in CLOSED_VERSION_STATES
                  or v.get("appStoreState") in CLOSED_STORE_STATES)
        t = parse_version(v.get("version")) if closed else None
        if t is not None and (best is None or t > best):
            best = t
    return format_version(best) if best else None


def decide_version(current: str, closed: str | None, mode: str) -> dict:
    """Decide the version to use. For a release, a closed version is not changed but reported as a failure (ok False)."""
    cur_t, closed_t = parse_version(current), parse_version(closed)
    base = {"ok": True, "version": current, "changed": False, "closed_max": closed}
    if closed_t is None:
        return {**base, "reason": message("ios_release.reason.no_closed")}
    if cur_t is None:
        # Leave version strings we cannot judge untouched (post-failure recovery covers it)
        return {**base, "reason": message("ios_release.reason.unparsable", current=repr(current))}
    if cur_t > closed_t:
        return {**base, "reason": message("ios_release.reason.open", current=current, closed=closed)}
    if mode == "release":
        return {**base, "ok": False,
                "reason": message("ios_release.reason.release_closed", current=current)}
    nxt = next_patch(closed)
    # Korean particles after a number (는/은, 로/으로) depend on the final consonant, so the text avoids particles
    why = (message("ios_release.reason.closed_same", current=current) if cur_t == closed_t
           else message("ios_release.reason.closed_lower", current=current, closed=closed))
    return {"ok": True, "version": nxt, "changed": True, "closed_max": closed,
            "reason": message("ios_release.reason.changed", why=why, next=nxt)}


def stale_branch_reason(current: str, base: str | None) -> str | None:
    """Merge-recommendation reason if the branch version is lower than the default branch's, else None (None quietly if not comparable)."""
    cur_t, base_t = parse_version(current), parse_version(base)
    if cur_t is None or base_t is None or cur_t >= base_t:
        return None
    return message("ios_release.stale_branch", current=current, base=base)


# ── Upload error classification ──────────────────────────────────────────────────
def _code(n: str) -> str:
    """Match Apple error codes only with context (#694).

    Forms the code takes in real logs: `ITMS-90189`, altool's `(90186)`,
    `.digits` after an uppercase code as in `STATE_ERROR.VALIDATION_ERROR.90061`.
    Matching bare digits misclassifies when a build number, byte count or ms duration has the same value,
    and the result decides retries and version switching.
    """
    return rf"(?:ITMS-{n}(?!\d)|(?<=[A-Z]\.){n}(?!\d)|\({n}\))"


_TRAIN_VERSION = re.compile(r"train version '(?P<v>[\d.]+)' is closed", re.I)
_APPROVED_VERSION = re.compile(r"previously approved version \[(?P<v>[\d.]+)\]", re.I)
_TOO_LOW_NUMBERS = [
    re.compile(r"must (?:contain a )?higher version than that of the previously uploaded version \[(?P<n>\d+)", re.I),
    re.compile(r"bundle version must be higher than the previously uploaded version: '(?P<n>\d+)'", re.I),
]

# Patterns per kind. Earlier kinds win (train_closed > too_low > duplicate)
_KIND_PATTERNS: list[tuple[str, list[re.Pattern]]] = [
    ("train_closed", [re.compile(_code("90186")), _TRAIN_VERSION,
                      re.compile(_code("90062")), _APPROVED_VERSION,
                      re.compile(_code("90478")), re.compile(r"later version has been closed", re.I)]),
    ("too_low", [re.compile(_code("90061")), *_TOO_LOW_NUMBERS]),
    ("duplicate", [re.compile(_code("90189")), re.compile(r"Redundant Binary Upload", re.I),
                   re.compile(r"INVALID\.DUPLICATE"), re.compile(r"(?<!\d)-19232(?!\d)")]),
]
_FALLBACK_LINE = re.compile(r"ITMS-\d+|ERROR|error|실패|\[!\]")
# altool's own success line. fastlane < 2.240 still fails on a stray ERROR line printed after it (Xcode 27.2, fastlane#30586)
_ALTOOL_UPLOAD_SUCCEEDED = "UPLOAD SUCCEEDED with no errors"
# DEPLOY_MODE values whose deploy lane ends at the TestFlight upload (Fastfile default: testflight_only)
_UPLOAD_ONLY_DEPLOY_MODES = ("store_only", "testflight_only")


def _first_group(patterns: list[re.Pattern], text: str, group: str) -> str | None:
    for p in patterns:
        m = p.search(text)
        if m and m.groupdict().get(group):
            return m.group(group)
    return None


def _clean_line(line: str) -> str:
    return line.strip()[:300]


def classify_upload_error(log: str) -> dict:
    """Classify the fastlane upload log. Color codes are stripped first."""
    text = _ANSI.sub("", log or "")
    kind, hit_patterns = "other", []
    for k, pats in _KIND_PATTERNS:
        matched = [p for p in pats if p.search(text)]
        if matched:
            kind, hit_patterns = k, matched
            break

    required = closed_version = None
    if kind == "train_closed":
        closed_version = _first_group([_TRAIN_VERSION, _APPROVED_VERSION], text, "v")
    elif kind == "too_low":
        n = _first_group(_TOO_LOW_NUMBERS, text, "n")
        required = int(n) if n else None

    reason = ""
    lines = text.splitlines()
    if hit_patterns:
        reason = next((_clean_line(l) for l in lines if any(p.search(l) for p in hit_patterns)), "")
    else:
        hits = [l for l in lines if _FALLBACK_LINE.search(l)]
        reason = _clean_line(hits[-1]) if hits else ""
    return {"kind": kind, "required_build": required, "closed_version": closed_version,
            "is_upload_reported_ok": _ALTOOL_UPLOAD_SUCCEEDED in text,
            "reason_line": reason or message("ios_release.no_reason")}


# ── CLI ───────────────────────────────────────────────────────────────
def _write_github_output(pairs: dict) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        for k, v in pairs.items():
            # A newline in a value breaks the GITHUB_OUTPUT format and the next line is read as another key
            f.write(f"{k}={_one_line(v)}\n")


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _stale_outputs(args: argparse.Namespace) -> dict:
    """Stale branch warning outputs (stale, stale_reason) — always emitted together, whether or not the ASC lookup succeeded."""
    reason = stale_branch_reason(args.version, args.base_version)
    return {"stale": str(reason is not None).lower(), "stale_reason": reason or ""}


def _precheck_fallback(args: argparse.Namespace, why: str) -> int:
    reason = message("ios_release.precheck.fallback", why=why)
    stale = _stale_outputs(args)
    print(f"warning: {reason}", file=sys.stderr)
    _write_github_output({"version": args.version, "changed": "false", "reason": reason, **stale})
    _emit({"ok": True, "version": args.version, "changed": False, "closed_max": None,
           "reason": reason, "fallback": True, "summary": reason, "next": None, **stale})
    return 0


def cmd_precheck(args: argparse.Namespace) -> int:
    token = asc_client.token_from_env()
    if not token:
        return _precheck_fallback(args, message("ios_release.asc.no_credentials"))
    try:
        app_id = asc_client.find_app_id(args.bundle_id, token)
        if not app_id:
            return _precheck_fallback(args, message("ios_release.asc.app_not_found", bundle_id=args.bundle_id))
        closed = closed_max(asc_client.list_app_store_versions(app_id, token))
    except asc_client.AscError as e:
        return _precheck_fallback(args, str(e))

    d = decide_version(args.version, closed, args.mode)
    stale = _stale_outputs(args)
    _write_github_output({"version": d["version"], "changed": str(d["changed"]).lower(), "reason": d["reason"], **stale})
    _emit({**d, **stale, "fallback": False, "summary": d["reason"],
           "next": None if d["ok"] else "bump the version in version.yml and run again"})
    if not d["ok"]:
        print(f"::error::{d['reason']}", file=sys.stderr)
        return 1
    return 0


def cmd_classify(args: argparse.Namespace) -> int:
    try:
        log = Path(args.log).read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"warning: could not read the log: {e}", file=sys.stderr)
        log = ""
    r = classify_upload_error(log)
    _emit({"ok": True, **r, "summary": f"{r['kind']}: {r['reason_line']}", "next": None})
    return 0


# ── archive-upload ────────────────────────────────────────────────────
STATE_NAME = "ios_release_state.json"
_REEXIST_CHECKS = 3
_REEXIST_INTERVAL = 20
# Info.plist of the main app and the extension/watch/App Clip bundles nested in it
_BUNDLE_PLIST = re.compile(
    r"^Payload/[^/]+\.app(?:/(?:PlugIns|Watch|AppClips)/[^/]+\.(?:appex|app))*/Info\.plist$")
_SECRET_ENV = re.compile(r"KEY|TOKEN|SECRET|PASSWORD", re.I)


class _Fail(Exception):
    """archive-upload failure. The message becomes reason_line as is."""


def _one_line(v) -> str:
    """Strip newlines and color codes into one line."""
    return " ".join(_ANSI.sub("", str(v)).split())


def _scrub(text: str) -> str:
    """Mask secrets held in environment variables so they never leak into logs or reasons."""
    for k, v in os.environ.items():
        if _SECRET_ENV.search(k) and len(v) >= 8:
            text = text.replace(v, "***")
    return text


def _reason(text: str) -> str:
    return _scrub(_one_line(text))[:300]


def run_cmd(cmd: list[str], cwd: str, env: dict) -> tuple[int, str]:
    """Run a command streaming its output to stderr live, and return the combined output.
    stdout is reserved for the single JSON line, so child output never goes to stdout."""
    try:
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", bufsize=1)
    except OSError as e:
        return 127, message("ios_release.run_failed", cmd=cmd[0], error=e)
    lines: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stderr.write(line)
        sys.stderr.flush()
        lines.append(line)
    return proc.wait(), "".join(lines)


def write_runtime_export_options(src: Path, dst: Path) -> Path:
    """Turn off automatic numbering only in a copy, leaving the original (so Xcode cannot change numbers during export)."""
    with open(src, "rb") as f:
        data = plistlib.load(f)
    data["manageAppVersionAndBuildNumber"] = False
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "wb") as f:
        plistlib.dump(data, f)
    return dst


def verify_ipa(ipa: Path, version: str, build: int) -> list[str]:
    """Check that every app/extension bundle in the IPA has the expected version and build number. Empty passes."""
    problems: list[str] = []
    try:
        zf = zipfile.ZipFile(ipa)
    except (OSError, zipfile.BadZipFile) as e:
        return [message("ios_release.ipa.cannot_open", name=ipa.name, error=e)]
    with zf:
        names = [n for n in zf.namelist() if _BUNDLE_PLIST.match(n)]
        if not any(n.count("/") == 2 for n in names):  # Payload/X.app/Info.plist
            return [message("ios_release.ipa.no_info_plist")]
        for n in sorted(names):
            rel = n[len("Payload/"):-len("/Info.plist")]
            try:
                info = plistlib.loads(zf.read(n))
            except (ExpatError, plistlib.InvalidFileException, ValueError, KeyError) as e:
                problems.append(message("ios_release.ipa.unreadable_plist", bundle=rel, error=e))
                continue
            got_b, got_v = info.get("CFBundleVersion"), info.get("CFBundleShortVersionString")
            if str(got_b) != str(build) or str(got_v) != str(version):
                problems.append(message("ios_release.ipa.mismatch", bundle=rel, got_build=got_b, build=build,
                                        got_version=got_v, version=version))
    return problems


def _last_error_line(out: str) -> str:
    """One line to show as the failure reason. The real cause is the `error: ...` line; the trailing `** ARCHIVE FAILED **`
    banner is a result, not a cause, so the banner is used only when there is no error line (E2E showed only the banner)."""
    lines = [l for l in _ANSI.sub("", out or "").splitlines() if l.strip()]
    errors = [l for l in lines if "error:" in l]
    if errors:
        # Drop the leading file path and keep only the cause sentence
        return _clean_line(errors[-1].split("error:", 1)[1])
    # run_cmd failure text depends on language (ko 실행 실패 / en failed to run)
    hits = [l for l in lines if re.search(r"\*\* .* FAILED|실행 실패|failed to run", l)]
    return _clean_line((hits or lines or [message("ios_release.no_output")])[-1])


def _int_env(name: str, default: int | None) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"warning: {name}={raw!r} is not an integer, ignoring it", file=sys.stderr)
        return default


class _Cfg:
    """Environment variable input. An empty string counts as missing (Actions passes missing secrets as empty values)."""

    def __init__(self) -> None:
        e = os.environ
        self.app_root = Path(e.get("APP_ROOT", "").strip() or ".")
        self.workspace = e.get("IOS_WORKSPACE", "").strip() or "Runner.xcworkspace"
        self.scheme = e.get("IOS_SCHEME", "").strip() or "Runner"
        self.version = e.get("VERSION", "").strip()
        self.mode = e.get("MODE", "").strip()
        self.app_identifier = e.get("APP_IDENTIFIER", "").strip()
        self.profile = e.get("IOS_PROVISIONING_PROFILE_NAME", "")
        self.floor = _int_env("BUILD_NUMBER_FLOOR", None)
        self.max_attempts = max(1, _int_env("MAX_ATTEMPTS", 5) or 5)
        self.ios_dir = self.app_root / "ios"
        self.state_path = self.ios_dir / "build" / STATE_NAME

    def validate(self) -> None:
        if not self.version:
            raise _Fail(message("ios_release.fail.version_required"))
        if self.mode not in ("test", "release"):
            raise _Fail(message("ios_release.fail.mode_invalid"))


def _asc_context(cfg: _Cfg) -> tuple[str, str]:
    """(token, app ID). If either cannot be obtained, raise AscError rather than _Fail."""
    token = asc_client.token_from_env()
    if not token:
        raise asc_client.AscError(message("ios_release.asc.no_credentials"))
    if not cfg.app_identifier:
        raise asc_client.AscError(message("ios_release.asc.no_app_identifier"))
    app_id = asc_client.find_app_id(cfg.app_identifier, token)
    if not app_id:
        raise asc_client.AscError(message("ios_release.asc.app_not_found", bundle_id=cfg.app_identifier))
    return token, app_id


def _asc_floor(cfg: _Cfg) -> int | None:
    """Latest ASC build number + 1. If the lookup fails, proceed without a floor."""
    try:
        token, app_id = _asc_context(cfg)
        latest = asc_client.recent_max_build(app_id, token)
    except asc_client.AscError as e:
        print(f"warning: could not look up the latest App Store Connect build number, using the time-based number: {e}", file=sys.stderr)
        return None
    return latest + 1 if latest else None


def _archive_and_export(cfg: _Cfg, version: str, number: int) -> Path:
    """Archive, export with runtime ExportOptions, verify IPA numbers. Returns the path of the IPA that passed."""
    env = dict(os.environ)
    ios = str(cfg.ios_dir)
    build_dir = cfg.ios_dir / "build"
    # Clear previous output so it does not mix in on retry
    shutil.rmtree(build_dir / "Runner.xcarchive", ignore_errors=True)
    shutil.rmtree(build_dir / "ipa", ignore_errors=True)

    rc, out = run_cmd([
        "xcodebuild", "-workspace", cfg.workspace, "-scheme", cfg.scheme,
        "-archivePath", "build/Runner.xcarchive", "-destination", "generic/platform=iOS", "archive",
        "CODE_SIGN_STYLE=Manual", f"PROVISIONING_PROFILE_SPECIFIER={cfg.profile}",
        "CODE_SIGN_IDENTITY=Apple Distribution",
        # Pass all four so it works whichever variable the extension targets use
        f"FLUTTER_BUILD_NUMBER={number}", f"CURRENT_PROJECT_VERSION={number}",
        f"FLUTTER_BUILD_NAME={version}", f"MARKETING_VERSION={version}",
    ], ios, env)
    if rc != 0:
        raise _Fail(_reason(message("ios_release.fail.archive", code=rc, line=_last_error_line(out))))

    try:
        write_runtime_export_options(cfg.ios_dir / "ExportOptions.plist", build_dir / "ExportOptions.runtime.plist")
    except (OSError, plistlib.InvalidFileException, ExpatError, ValueError) as e:
        raise _Fail(_reason(message("ios_release.fail.export_options", error=e)))
    rc, out = run_cmd([
        "xcodebuild", "-exportArchive", "-archivePath", "build/Runner.xcarchive",
        "-exportPath", "build/ipa", "-exportOptionsPlist", "build/ExportOptions.runtime.plist",
    ], ios, env)
    if rc != 0:
        raise _Fail(_reason(message("ios_release.fail.export", code=rc, line=_last_error_line(out))))

    ipas = sorted((build_dir / "ipa").glob("*.ipa"))
    if not ipas:
        raise _Fail(message("ios_release.fail.no_ipa"))
    if len(ipas) > 1:
        print(f"warning: found {len(ipas)} IPAs, using {ipas[0].name}", file=sys.stderr)
    problems = verify_ipa(ipas[0], version, number)
    if problems:
        more = message("ios_release.fail.bundle_mismatch_more", count=len(problems) - 1) if len(problems) > 1 else ""
        raise _Fail(_reason(message("ios_release.fail.bundle_mismatch", problem=problems[0], more=more)))
    return ipas[0].resolve()


def _save_state(cfg: _Cfg, version: str, number: int, attempt: int, ipa: Path) -> None:
    cfg.state_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.state_path.write_text(json.dumps(
        {"version": version, "build_number": number, "attempt": attempt, "ipa_path": str(ipa)},
        ensure_ascii=False), encoding="utf-8")


def _load_state(cfg: _Cfg) -> dict:
    try:
        st = json.loads(cfg.state_path.read_text(encoding="utf-8"))
        state = {"version": str(st["version"]), "build_number": int(st["build_number"]),
                 "attempt": int(st["attempt"]), "ipa_path": str(st["ipa_path"])}
    except FileNotFoundError:
        raise _Fail(message("ios_release.fail.state_missing", path=cfg.state_path))
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise _Fail(message("ios_release.fail.state_corrupt", path=cfg.state_path, error=type(e).__name__))
    if not Path(state["ipa_path"]).is_file():
        raise _Fail(message("ios_release.fail.state_no_ipa", path=state["ipa_path"]))
    return state


def _confirm_not_uploaded(cfg: _Cfg, number: int, reason: str) -> None:
    """Before re-uploading, check whether ASC already has this number. Do not retry if unsure."""
    try:
        token, app_id = _asc_context(cfg)
        for i in range(_REEXIST_CHECKS):
            if asc_client.build_exists(app_id, number, token):
                # It may be a post-upload step failure or a concurrent build with the same number in the same second; stop without telling them apart
                raise _Fail(_reason(message("ios_release.fail.already_uploaded", reason=reason)))
            if i < _REEXIST_CHECKS - 1:
                sleep(_REEXIST_INTERVAL)  # a build just uploaded may show up in the list late
    except asc_client.AscError as e:
        raise _Fail(_reason(message("ios_release.fail.reupload_unknown", error=e, reason=reason)))


def _is_build_in_asc(cfg: _Cfg, number: int) -> bool:
    """ASC lists this build number? (retries: a fresh upload shows up late; lookup errors count as no)"""
    try:
        token, app_id = _asc_context(cfg)
        for i in range(_REEXIST_CHECKS):
            if asc_client.build_exists(app_id, number, token):
                return True
            if i < _REEXIST_CHECKS - 1:
                sleep(_REEXIST_INTERVAL)
    except asc_client.AscError as e:
        print(f"warning: could not check App Store Connect for build {number}: {e}", file=sys.stderr)
    return False


def _accept_misread_upload(cfg: _Cfg, env: dict, number: int, reason: str) -> bool:
    """altool said the upload succeeded but fastlane failed > success only when the lane ends at the upload and ASC has the build

    Lanes that go on to the App Store step (store_prepare, store_submit) skipped it, so they still fail with the fix.
    """
    if not _is_build_in_asc(cfg, number):
        return False
    if env.get("DEPLOY_MODE", "testflight_only").strip() not in _UPLOAD_ONLY_DEPLOY_MODES:
        raise _Fail(_reason(message("ios_release.fail.altool_misread", number=number, reason=reason)))
    print(f"::warning title=fastlane misread the upload::altool reported success and App Store Connect has build {number}, "
          "but fastlane failed on a stray altool ERROR line (fastlane < 2.240, Xcode 27). Treated as uploaded; "
          "upgrade fastlane to 2.240 or later.")
    return True


def _next_closed_version(cfg: _Cfg, closed_version: str | None, reason: str) -> str:
    """Next patch version when the train is closed. If the version is unknown (90478), get it from ASC."""
    if not closed_version:
        try:
            token, app_id = _asc_context(cfg)
            closed_version = closed_max(asc_client.list_app_store_versions(app_id, token))
        except asc_client.AscError as e:
            raise _Fail(_reason(message("ios_release.fail.closed_unknown_error", error=e, reason=reason)))
    if not closed_version:
        raise _Fail(_reason(message("ios_release.fail.closed_unknown", reason=reason)))
    try:
        return next_patch(closed_version)
    except ValueError as e:
        raise _Fail(_reason(message("ios_release.fail.with_reason", error=e, reason=reason)))


def _phase_build(cfg: _Cfg, info: dict) -> None:
    floors = [cfg.floor, _asc_floor(cfg)]
    nb = build_number.next_build_number(floors=floors)
    number = nb["build_number"]
    info.update(build_number=number, version=cfg.version, attempts=0, built_at_utc=nb["built_at_utc"])
    ipa = _archive_and_export(cfg, cfg.version, number)
    _save_state(cfg, cfg.version, number, 1, ipa)
    info.update(attempts=1, ipa_path=str(ipa))


def _phase_upload(cfg: _Cfg, info: dict) -> None:
    st = _load_state(cfg)
    version, number, attempt, ipa = st["version"], st["build_number"], st["attempt"], Path(st["ipa_path"])
    info.update(build_number=number, version=version, attempts=attempt, ipa_path=str(ipa),
                built_at_utc=build_number.describe(number))
    while True:
        env = dict(os.environ)
        env.update(IPA_PATH=str(ipa), BUILD_NUMBER=str(number), APP_VERSION=version)
        if cfg.mode == "test":
            # Pin it even if another value is already set, so a test build never goes as far as review submission (#601)
            env["DEPLOY_MODE"] = "store_only"
        rc, out = run_cmd(["bundle", "exec", "fastlane", "deploy"], str(cfg.ios_dir), env)
        try:
            (cfg.ios_dir / "build" / f"upload_attempt_{attempt}.log").write_text(_scrub(out), encoding="utf-8")
        except OSError as e:
            print(f"warning: could not save the upload log: {e}", file=sys.stderr)
        if rc == 0:
            return

        r = classify_upload_error(out)
        reason = _reason(r["reason_line"])
        kind = r["kind"]
        if r["is_upload_reported_ok"] and _accept_misread_upload(cfg, env, number, reason):
            return
        if kind == "other":
            raise _Fail(reason)
        if kind == "train_closed" and cfg.mode == "release":
            raise _Fail(_reason(message("ios_release.fail.release_closed", reason=reason)))
        if attempt >= cfg.max_attempts:
            raise _Fail(_reason(message("ios_release.fail.attempts", count=cfg.max_attempts, reason=reason)))

        new_version = _next_closed_version(cfg, r["closed_version"], reason) if kind == "train_closed" else version
        _confirm_not_uploaded(cfg, number, reason)

        floors = [cfg.floor, number + 1]
        if kind == "too_low" and r["required_build"]:
            floors.append(r["required_build"] + 1)
        number = build_number.next_build_number(floors=floors)["build_number"]
        version = new_version
        attempt += 1
        info.update(build_number=number, version=version, attempts=attempt,
                    built_at_utc=build_number.describe(number))
        # Do not rebuild Flutter; restart from the archive
        ipa = _archive_and_export(cfg, version, number)
        info["ipa_path"] = str(ipa)
        _save_state(cfg, version, number, attempt, ipa)


def cmd_archive_upload(args: argparse.Namespace) -> int:
    info: dict = {}
    try:
        cfg = _Cfg()
        cfg.validate()
        (_phase_build if args.phase == "build" else _phase_upload)(cfg, info)
    except _Fail as e:
        reason = _reason(str(e))
        print(f"::error::{reason}", file=sys.stderr)
        _write_github_output({**info, "reason_line": reason})
        _emit({"ok": False, **info, "reason_line": reason, "summary": reason,
               "next": "check the reason and rerun the workflow if needed"})
        return 1
    done = "build done" if args.phase == "build" else "upload done"
    summary = f"{done}: build number {info.get('build_number')}, version {info.get('version')}, attempts {info.get('attempts')}"
    _write_github_output(info)
    _emit({"ok": True, **info, "summary": summary,
           "next": "archive-upload --phase upload" if args.phase == "build" else None})
    return 0


def _status_fail(reason: str) -> int:
    print(f"::error::{reason}", file=sys.stderr)
    _emit({"ok": False, "reason": reason, "summary": reason, "next": None})
    return 1


def _status_markdown(bundle_id: str, versions: list[dict], closed: str | None, recent: int | None) -> str:
    """Table for the run summary. Values are only version strings and state names, so no secrets can mix in."""
    lines = [f"## App Store Connect status ({bundle_id})", "",
             f"- Highest closed version: `{closed or 'none'}`",
             f"- Latest uploaded build number: `{recent if recent is not None else 'unavailable'}`", "",
             "| Version | State | Closed |", "|---|---|---|"]
    for v in versions:
        state = v.get("appVersionState") or v.get("appStoreState") or "-"
        lines.append(f"| {v['version']} | {state} | {'yes' if v['closed'] else 'no'} |")
    return "\n".join(lines) + "\n"


def cmd_asc_status(args: argparse.Namespace) -> int:
    """Only look up the app version state and latest build number (#651). Uploads or changes nothing.
    Unlike the precheck, the purpose is the lookup, so a failed lookup is reported as failure instead of falling back."""
    token = asc_client.token_from_env()
    if not token:
        return _status_fail("No App Store Connect credentials (check the APP_STORE_CONNECT_API_KEY_ID, ISSUER_ID and API_KEY_BASE64 secrets)")
    try:
        app_id = asc_client.find_app_id(args.bundle_id, token)
        if not app_id:
            return _status_fail(f"No app found for bundle ID {args.bundle_id}")
        rows = asc_client.list_app_store_versions(app_id, token)
    except asc_client.AscError as e:
        return _status_fail(f"App Store Connect lookup failed: {e}")
    try:
        recent = asc_client.recent_max_build(app_id, token)
    except asc_client.AscError as e:
        print(f"warning: could not look up the latest build number: {e}", file=sys.stderr)
        recent = None

    closed = closed_max(rows)
    versions = []
    for r in rows:
        t = parse_version(r.get("version"))
        is_closed = (r.get("appVersionState") in CLOSED_VERSION_STATES
                     or r.get("appStoreState") in CLOSED_STORE_STATES)
        versions.append({"version": r.get("version"), "appVersionState": r.get("appVersionState"),
                         "appStoreState": r.get("appStoreState"), "closed": is_closed, "_key": t or (0, 0, 0)})
    versions.sort(key=lambda v: v["_key"], reverse=True)  # newest version on top
    for v in versions:
        del v["_key"]

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(_status_markdown(args.bundle_id, versions, closed, recent))
    _write_github_output({"closed_max": closed or "", "recent_max_build": "" if recent is None else recent})
    _emit({"ok": True, "app_id": app_id, "versions": versions, "closed_max": closed,
           "recent_max_build": recent, "summary": f"highest closed version {closed or 'none'}, latest build number {recent}", "next": None})
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="iOS release decisions: version precheck, upload error classification, archive and upload")
    sub = p.add_subparsers(dest="cmd", required=True)
    pc = sub.add_parser("precheck-version", help="check for a closed (released) version before building")
    pc.add_argument("--mode", choices=["test", "release"], required=True)
    pc.add_argument("--version", required=True)
    pc.add_argument("--bundle-id", required=True)
    pc.add_argument("--base-version", default="", help="default-branch version, to warn when this branch is behind it")
    ce = sub.add_parser("classify-error", help="classify an upload log")
    ce.add_argument("--log", required=True)
    st = sub.add_parser("asc-status", help="show app version states and the latest build number (read only)")
    st.add_argument("--bundle-id", required=True)
    au = sub.add_parser("archive-upload", help="archive, verify, upload and retry")
    au.add_argument("--phase", choices=["build", "upload"], required=True)
    args = p.parse_args(argv)
    if args.cmd == "archive-upload":
        return cmd_archive_upload(args)
    if args.cmd == "asc-status":
        return cmd_asc_status(args)
    return cmd_precheck(args) if args.cmd == "precheck-version" else cmd_classify(args)


if __name__ == "__main__":
    sys.exit(main())
