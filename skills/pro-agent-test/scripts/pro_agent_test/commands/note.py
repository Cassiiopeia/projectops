"""note: 이 프로젝트에서 알아낸 것 쌓기 (show · target · constraint · screen · pitfall · run · tidy · forget)"""
from __future__ import annotations

from pathlib import Path

from common import memory as _memory
from common.access import find_secrets as _find_secrets
from common.emit import emit

from pro_agent_test.notes.recall import _brief, _find_dup, _new_entry, _ranked, _screen_view
from pro_agent_test.notes.screen import _note_screen
from pro_agent_test.notes.store import (_NOTE_SCHEMA, _load_notes, _machine_note_path, _note_path, _read_notes,
                                        _save_notes)
from pro_agent_test.notes.tidy import _note_tidy
from pro_agent_test.scenario_rules import TARGETS
from pro_agent_test.storage import _MACHINE_SCOPES, _SHOW_CHARS, _SHOW_MAX


def cmd_note(args) -> int:
    """밟으면서 알아낸 것을 프로젝트에 남긴다.

    같은 앱을 다음에 밟을 때 좌표를 처음부터 찾거나 같은 함정에 다시 빠지지 않게
    한다. skill은 어느 프로젝트에나 같지만, 이 파일은 프로젝트마다 다르게 자란다.
    """
    from datetime import date

    root = Path(args.root).resolve()
    notes, warning = _load_notes(root)
    today = date.today().isoformat()
    extra: dict = {}

    if args.action == "show":
        machine, _ = _read_notes(_machine_note_path())
        pits, cons = notes.get("pitfalls", []), notes.get("constraints", [])
        to_tidy = sum(1 for x in pits if isinstance(x, dict)
                      and x.get("scope", "project") != "project")
        if args.all:
            body = {
                "constraints": [{**e, "index": i, "verify": _memory.needs_verify(e, today)}
                                for i, e in enumerate(cons) if isinstance(e, dict)],
                "pitfalls": [{**e, "index": i, "verify": _memory.needs_verify(e, today)}
                             for i, e in enumerate(pits) if isinstance(e, dict)],
                "machine_pitfalls": machine.get("pitfalls", []),
                "screens": notes.get("screens", {}),
                "runs": notes.get("runs", [])[-30:],
            }
        else:
            # 요약 — 23KB 를 통째로 주면 아무도 다 읽지 않는다 (#837 실측)
            body = {
                "constraints": [_brief(i, e, _SHOW_CHARS, today) for i, e in _ranked(cons, today)[:_SHOW_MAX]],
                "pitfalls": [_brief(i, e, _SHOW_CHARS, today) for i, e in _ranked(pits, today)[:_SHOW_MAX]],
                "machine_pitfalls": [_brief(i, e, _SHOW_CHARS, today, "machine")
                                     for i, e in _ranked(machine.get("pitfalls", []), today)[:3]],
                "screens": {k: _screen_view(v, False) for k, v in (notes.get("screens") or {}).items()
                            if isinstance(v, dict)},
                "runs": [{**r, "result": _memory.clip(r.get("result"), 200)}
                         for r in notes.get("runs", [])[-3:] if isinstance(r, dict)],
            }
        nxt = []
        if not args.all and (len(cons) > _SHOW_MAX or len(pits) > _SHOW_MAX):
            nxt.append("note show --all  # see everything")
        if to_tidy:
            nxt.append(f"note tidy  # see the plan to move {to_tidy} flutter/platform-scope entry(ies) to this machine's scope")
        return emit({
            "file": str(_note_path(root)),
            "schema": notes.get("schema", _NOTE_SCHEMA),
            **body,
            "targets": notes.get("targets"),
            "full": bool(args.all),
            **({"warning": warning} if warning else {}),
            "summary": (f"{len(cons)} constraint(s) · {len(notes.get('screens', {}))} screen(s) · "
                        f"{len(pits)} pitfall(s) · {len(machine.get('pitfalls', []))} machine pitfall(s) · "
                        f"{len(notes.get('runs', []))} recorded run(s)"
                        + ("" if args.all else " (summary)")),
            "next": " · ".join(nxt) or None,
        })

    if args.action == "tidy":
        if warning:
            return emit({"ok": False, "code": "note_unreadable", "error": warning})
        return emit(_note_tidy(args, root, notes, today))

    f = _note_path(root, create=True)
    if args.action == "screen":
        r = _note_screen(args, notes, today)
        if not r.pop("ok"):
            return emit({"ok": False, **r})
        extra = r

    elif args.action in ("pitfall", "constraint"):
        kind = args.action + "s"
        machine_scope = args.action == "pitfall" and args.scope in _MACHINE_SCOPES
        mf = _machine_note_path()
        machine, mwarn = (_read_notes(mf) if args.action == "pitfall" else ({"pitfalls": []}, None))
        if mwarn:
            return emit({"ok": False, "code": "machine_unreadable", "error": mwarn})
        target = machine if machine_scope else notes
        target_file = mf if machine_scope else f
        entries = target.setdefault(kind, [])

        if args.result:
            # 이미 있는 항목의 성적 — 다시 겪었으면 ok, 틀린 기억이었으면 fail
            if args.index is None or not (0 <= args.index < len(entries)):
                return emit({"ok": False, "code": "bad_index",
                             "error": f"--result needs a {kind} --index (0~{len(entries) - 1})",
                             "next": "note show --all  # see the index"})
            e = entries[args.index]
            counted = _memory.bump(e, args.result, today)
            _save_notes(target_file, target)
            return emit({"file": str(target_file), "entry": e, "counted": counted,
                         "verify": _memory.needs_verify(e, today),
                         "summary": f"{args.action} #{args.index} ok={e['ok']} fail={e['fail']}"
                                    + ("" if counted else " (already counted today)"),
                         "next": None})

        if not args.text:
            return emit({"ok": False, "code": "args_required",
                         "error": "--text is required" if args.action == "pitfall"
                         else "write what must hold in --text"})
        secrets = _find_secrets(args.text + " " + (args.check or ""))
        if secrets:
            return emit({
                "ok": False, "code": "secret_detected",
                "error": f"The text to record contains {', '.join(secrets)}",
                "hint": ("This file stays on disk in plain text and is read again on every run. "
                         "Write something like 'with the test account' instead of the actual value"),
            })
        fields = {"scope": args.scope} if args.action == "pitfall" else {"check": args.check}

        if args.merge_into is not None:
            # agent 가 같은 지식이라고 판단한 것 — 문장을 새것으로 바꾸고 성적은 이어 간다
            if not (0 <= args.merge_into < len(entries)):
                return emit({"ok": False, "code": "bad_index",
                             "error": f"--merge-into must be 0~{len(entries) - 1}"})
            e = entries[args.merge_into]
            e["text"] = args.text
            e.update({k: v for k, v in fields.items() if v is not None})
            _memory.bump(e, "ok", today)
            _save_notes(target_file, target)
            return emit({"file": str(target_file), "entry": e,
                         "summary": f"merged into #{args.merge_into} (ok={e['ok']})", "next": None})

        # 쓰기 전에 비슷한 것을 찾는다 — 이 범위 먼저, 그다음 다른 범위 (원칙 3)
        docs = {("machine" if machine_scope else "repo"): (target, target_file)}
        if args.action == "pitfall":
            if machine_scope:
                docs["repo"] = (notes, f)
            else:
                docs["machine"] = (machine, mf)
        hit, related = _find_dup(args.text, {k: d.get(kind, []) for k, (d, _) in docs.items()})
        if hit:
            scope_name, i = hit
            hit_doc, hit_file = docs[scope_name]
            e = hit_doc[kind][i]
            counted = _memory.bump(e, "ok", today)
            _save_notes(hit_file, hit_doc)
            return emit({
                "file": str(hit_file), "merged_into": {"scope": scope_name, "index": i, "text": e["text"]},
                "entry": e, "counted": counted,
                "summary": f"the same content already exists, so it was merged instead of added ({scope_name} #{i}, ok={e['ok']})",
                "next": (f"if the new text is more accurate: note {args.action} --merge-into {i} --text \"…\""
                         + ((" --scope " + ("project" if scope_name == "repo" else e.get("scope", "platform")))
                            if args.action == "pitfall" else "")),
            })
        entries.append(_new_entry(args.text, today, **fields))
        new_index = len(entries) - 1
        _save_notes(target_file, target)
        nxt = None
        if related:
            nxt = (f"if related holds the same knowledge: note forget --kind {args.action} --index {new_index}"
                   + (f" --scope {args.scope}" if machine_scope else "")
                   + f", then merge with note {args.action} --merge-into <that index> --text \"…\"")
        return emit({
            "file": str(target_file), "index": new_index,
            **({"scope": "machine"} if machine_scope else {}),
            **({"related": related} if related else {}),
            **({"warning": warning} if warning else {}),
            "summary": (f"{args.action} recorded"
                        + (" — kept at this machine's scope (all repos)" if machine_scope else "")),
            "next": nxt,
        })

    elif args.action == "forget":
        # 지우는 것은 agent·사람의 명시적 판단으로만 (원칙 4) — 번호를 꼭 받는다
        if args.kind not in ("pitfall", "constraint") or args.index is None:
            return emit({"ok": False, "code": "args_required",
                         "error": "--kind pitfall|constraint and --index are required",
                         "next": "note show --all  # see the index"})
        machine_scope = args.kind == "pitfall" and args.scope in _MACHINE_SCOPES
        mf = _machine_note_path()
        doc, doc_file = (_read_notes(mf)[0], mf) if machine_scope else (notes, f)
        entries = doc.get(args.kind + "s", [])
        if not (0 <= args.index < len(entries)):
            return emit({"ok": False, "code": "bad_index",
                         "error": f"--index must be 0~{len(entries) - 1}"})
        removed = entries.pop(args.index)
        _save_notes(doc_file, doc)
        return emit({"file": str(doc_file), "removed": removed,
                     "summary": f"deleted {args.kind} #{args.index}", "next": None})

    elif args.action == "target":
        vals = [t.strip() for t in (args.targets or "").split(",") if t.strip()]
        unknown = [t for t in vals if t not in TARGETS]
        if not vals or unknown:
            return emit({
                "ok": False, "code": "bad_targets",
                "error": (f"unknown target(s): {', '.join(unknown)}" if unknown
                          else "write what can be walked in --targets"),
                "hint": f"comma-separated, from {'·'.join(TARGETS)} (e.g. server,web)",
            })
        if not args.why:
            return emit({
                "ok": False, "code": "why_required",
                "error": "write the evidence for that judgment in --why",
                "hint": ("Whoever reads this record next must be able to re-check it. "
                         "e.g. \"pages are rendered directly with Thymeleaf templates\""),
            })
        notes["targets"] = {"value": vals, "why": args.why, "added": today}

    elif args.action == "run":
        if not (args.name or args.text):
            # 인자 없이 부르면 "(지정 안 함)/(기록 없음)" 쓰레기 줄만 쌓인다 (#706)
            return emit({"ok": False, "code": "args_required",
                         "error": "--name (scenario) or --text (result summary) is required"})
        notes.setdefault("runs", []).append({
            "date": today,
            "scenario": args.name or "(not set)",
            "result": args.text or "(not recorded)",
        })
        notes["runs"] = notes["runs"][-30:]   # 오래된 것은 버린다

    _save_notes(f, notes)
    return emit({
        "file": str(f),
        **extra,
        **({"warning": warning} if warning else {}),
        "summary": f"{args.action} recorded — {f.name}",
        "next": ("check the app tap result (screen_changed), then note screen --name … --target <label> --result ok|fail"
                 if args.action == "screen" and "graded" not in extra and args.target else None),
    })
