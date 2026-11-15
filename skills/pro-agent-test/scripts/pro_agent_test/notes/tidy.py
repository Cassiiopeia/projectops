"""note tidy: move mixed-scope pitfalls > machine scope · launch knowledge"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from common import memory as _memory

from pro_agent_test.launch_bridge import _launch
from pro_agent_test.notes.recall import _find_dup
from pro_agent_test.notes.store import _machine_note_path, _note_path, _read_notes, _save_notes
from pro_agent_test.storage import _MACHINE_SCOPES, _SHOW_CHARS, _repo_key


# ── note tidy — move mixed-scope records to where they belong (#837) ────────────────
#
# Measured (one app): of 39 pitfalls, 18 flutter/platform ones only got a "promote to the skill" hint and piled up
# in the repo, and tool usage (ASC login etc.) overlapped launch knowledge. Only moves, never deletes.

# Wording that looks like tool usage → launch knowledge area
_TOOL_AREAS = (
    ("web", re.compile(r"(?i)\bgstack\b|\bplaywright\b|\bchromium\b|\bCDP\b|App Store Connect"
                       r"|\bheaded\b|\bbrowse\b")),
    ("ios", re.compile(r"(?i)\bmaestro\b|\bsimctl\b|\bxcrun\b|\btestflight\b")),
    # Words like uiautomator·AVD also appear in QA judgements (don't log this screen as a defect etc.), so excluded
    ("android", re.compile(r"(?i)\bscreenrecord\b")),
)
# Negative assertions ("X does not work") are not remembered by principle — not moved, only listed for review
_NEGATIVE = re.compile(r"안 ?된다|수 없다|불가")
_TOOL_ANY = re.compile(r"(?i)\blaunch_cli\b|\be2e_cli\b")
_LAUNCH_HOW_MAX = 200     # pro-launch knowledge.MAX_HOW — longer entries get truncated on save, so not moved


def _tool_area(text: str) -> tuple[bool, str | None]:
    """(is it tool usage, launch area)."""
    for area, pat in _TOOL_AREAS:
        if pat.search(text):
            return True, area
    return bool(_TOOL_ANY.search(text)), None


def _launch_key(text: str) -> str:
    """launch knowledge key. A few English words + a short hash — the same key overwrites the existing entry, so keep keys distinct."""
    ascii_words = re.findall(r"[A-Za-z][A-Za-z0-9_.-]+", text)[:3]
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:4]
    return "-".join([*(w.lower() for w in ascii_words), digest])[:60] or f"pitfall-{digest}"


def _tidy_plan(notes: dict, overrides: dict[int, str]) -> dict:
    to_machine, to_launch, skipped, review = [], [], [], []
    for i, p in enumerate(notes.get("pitfalls") or []):
        if not isinstance(p, dict) or not p.get("text"):
            continue
        text, scope = p["text"], p.get("scope", "project")
        if _NEGATIVE.search(text):
            review.append({"index": i, "text": _memory.clip(text, _SHOW_CHARS),
                           "reason": "negative claim — check it still holds; if not, note forget or --result fail"})
        is_tool, area = _tool_area(text)
        if i in overrides:
            is_tool, area = True, overrides[i]
        if is_tool:
            if not area:
                skipped.append({"index": i, "text": _memory.clip(text, _SHOW_CHARS),
                                "reason": "looks like tool usage but no area could be decided — set it with --launch "
                                          f"{i}=web|ios|android|server or leave it"})
                continue
            if len(" ".join(text.split())) > _LAUNCH_HOW_MAX:
                skipped.append({"index": i, "text": _memory.clip(text, _SHOW_CHARS),
                                "reason": f"over {_LAUNCH_HOW_MAX} characters, cannot move to launch as is — shorten it, "
                                          f"record with launch_cli learn --area {area}, then note forget --index {i}"})
                continue
            to_launch.append({"index": i, "area": area, "key": _launch_key(text),
                              "scope": "repo" if scope == "project" else "machine",
                              "text": _memory.clip(text, _SHOW_CHARS)})
        elif scope in _MACHINE_SCOPES:
            to_machine.append({"index": i, "scope": scope, "text": _memory.clip(text, _SHOW_CHARS)})
    return {"to_machine": to_machine, "to_launch": to_launch, "skipped": skipped, "review": review}


def _note_tidy(args, root: Path, notes: dict, today: str) -> dict:
    overrides = {}
    for o in args.launch or []:
        i, sep, area = o.partition("=")
        if not (sep and i.strip().isdigit() and area.strip() in ("ios", "android", "web", "server")):
            return {"ok": False, "code": "bad_launch",
                    "error": f"--launch '{o}' must look like 'number=area'", "hint": "e.g. 28=web"}
        overrides[int(i)] = area.strip()
    plan = _tidy_plan(notes, overrides)
    if not args.apply:
        n = len(plan["to_machine"]) + len(plan["to_launch"])
        return {"ok": True, "applied": False, **plan,
                "summary": (f"{n} to move (this machine {len(plan['to_machine'])} · "
                            f"launch {len(plan['to_launch'])}) · {len(plan['skipped'])} to keep — not moved yet"),
                "next": f"note tidy --apply --root {root}  # move per the plan" if n else None}

    pits = notes.get("pitfalls") or []
    moved: set[int] = set()
    failed = []
    for row in plan["to_launch"]:
        data, raw, rc = _launch(["learn", "--area", row["area"], "--key", row["key"],
                                 "--how", " ".join(pits[row["index"]]["text"].split()),
                                 "--result", "ok", "--scope", row["scope"], "--root", str(root)])
        if data and data.get("ok"):
            moved.add(row["index"])
            row["launch"] = {"key": (data.get("entry") or {}).get("key"), "scope": data.get("scope")}
        else:
            failed.append({**row, "error": (data or {}).get("error") or raw[-200:]})

    mf = _machine_note_path()
    machine, warn = _read_notes(mf)
    if warn:
        return {"ok": False, "code": "machine_unreadable", "error": warn,
                "next": "The machine notes file is not valid JSON. Open the file named in error, fix or move it aside, then retry"}
    merged = 0
    for row in plan["to_machine"]:
        p = pits[row["index"]]
        hit, _ = _find_dup(p["text"], {"machine": machine["pitfalls"]})
        if hit:
            # The same knowledge already exists — merge scores and keep the more recent sentence
            m = machine["pitfalls"][hit[1]]
            ok, fail, last = _memory.stats(m)
            pok, pfail, plast = _memory.stats(p)
            m["ok"], m["fail"] = ok + pok, fail + pfail
            if plast > last:
                m["text"], m["last_seen"] = p["text"], plast
            merged += 1
        else:
            machine["pitfalls"].append({**p, "from": _repo_key(root)})
        moved.add(row["index"])
    # Write machine scope first — stopping midway only duplicates, never loses
    if plan["to_machine"]:
        _save_notes(mf, machine)
    if moved:
        notes["pitfalls"] = [p for i, p in enumerate(pits) if i not in moved]
        _save_notes(_note_path(root, create=True), notes)
    return {"ok": not failed, "code": "ok" if not failed else "partly_moved", "applied": True,
            **plan, "failed": failed, "machine_file": str(mf), "merged_in_machine": merged,
            "summary": (f"moved {len(moved)} (this machine {len(plan['to_machine'])} · launch "
                        f"{len(plan['to_launch']) - len(failed)}, merged {merged}) · kept {len(plan['skipped'])}"),
            "next": "note show  # see the result" if not failed else "read the errors in failed and fix them"}
