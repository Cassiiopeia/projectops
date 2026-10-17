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
            nxt.append("note show --all  # 전부 본다")
        if to_tidy:
            nxt.append(f"note tidy  # flutter/platform 범위 {to_tidy}건을 이 컴퓨터 범위로 옮길 계획을 본다")
        return emit({
            "file": str(_note_path(root)),
            "schema": notes.get("schema", _NOTE_SCHEMA),
            **body,
            "targets": notes.get("targets"),
            "full": bool(args.all),
            **({"warning": warning} if warning else {}),
            "summary": (f"제약 {len(cons)}개 · 화면 {len(notes.get('screens', {}))}개 · "
                        f"함정 {len(pits)}건 · 이 컴퓨터 함정 {len(machine.get('pitfalls', []))}건 · "
                        f"기록된 실행 {len(notes.get('runs', []))}회"
                        + ("" if args.all else " (요약)")),
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
                             "error": f"--result 에는 {kind} 의 --index(0~{len(entries) - 1})가 필요합니다",
                             "next": "note show --all  # index 를 본다"})
            e = entries[args.index]
            counted = _memory.bump(e, args.result, today)
            _save_notes(target_file, target)
            return emit({"file": str(target_file), "entry": e, "counted": counted,
                         "verify": _memory.needs_verify(e, today),
                         "summary": f"{args.action} #{args.index} ok={e['ok']} fail={e['fail']}"
                                    + ("" if counted else " (오늘 이미 센 결과)"),
                         "next": None})

        if not args.text:
            return emit({"ok": False, "code": "args_required",
                         "error": "--text 가 필요합니다" if args.action == "pitfall"
                         else "--text 에 지켜야 할 것을 적으세요"})
        secrets = _find_secrets(args.text + " " + (args.check or ""))
        if secrets:
            return emit({
                "ok": False, "code": "secret_detected",
                "error": f"기록하려는 내용에 {', '.join(secrets)}이(가) 들어 있습니다",
                "hint": ("이 파일은 평문으로 디스크에 남고 다음 실행마다 다시 읽힙니다. "
                         "구체적인 값 대신 '테스트 계정으로'처럼 바꿔 적으세요"),
            })
        fields = {"scope": args.scope} if args.action == "pitfall" else {"check": args.check}

        if args.merge_into is not None:
            # agent 가 같은 지식이라고 판단한 것 — 문장을 새것으로 바꾸고 성적은 이어 간다
            if not (0 <= args.merge_into < len(entries)):
                return emit({"ok": False, "code": "bad_index",
                             "error": f"--merge-into 는 0~{len(entries) - 1} 이어야 합니다"})
            e = entries[args.merge_into]
            e["text"] = args.text
            e.update({k: v for k, v in fields.items() if v is not None})
            _memory.bump(e, "ok", today)
            _save_notes(target_file, target)
            return emit({"file": str(target_file), "entry": e,
                         "summary": f"#{args.merge_into} 에 합쳤습니다 (ok={e['ok']})", "next": None})

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
                "summary": f"같은 내용이 이미 있어 새로 쓰지 않고 합쳤습니다 ({scope_name} #{i}, ok={e['ok']})",
                "next": (f"새 문장이 더 정확하면 note {args.action} --merge-into {i} --text \"…\""
                         + ((" --scope " + ("project" if scope_name == "repo" else e.get("scope", "platform")))
                            if args.action == "pitfall" else "")),
            })
        entries.append(_new_entry(args.text, today, **fields))
        new_index = len(entries) - 1
        _save_notes(target_file, target)
        nxt = None
        if related:
            nxt = (f"related 에 같은 지식이 있으면 note forget --kind {args.action} --index {new_index}"
                   + (f" --scope {args.scope}" if machine_scope else "")
                   + f" 후 note {args.action} --merge-into <그 index> --text \"…\" 로 합친다")
        return emit({
            "file": str(target_file), "index": new_index,
            **({"scope": "machine"} if machine_scope else {}),
            **({"related": related} if related else {}),
            **({"warning": warning} if warning else {}),
            "summary": (f"{args.action} 기록 완료"
                        + (" — 이 컴퓨터 범위(모든 레포)에 남겼습니다" if machine_scope else "")),
            "next": nxt,
        })

    elif args.action == "forget":
        # 지우는 것은 agent·사람의 명시적 판단으로만 (원칙 4) — 번호를 꼭 받는다
        if args.kind not in ("pitfall", "constraint") or args.index is None:
            return emit({"ok": False, "code": "args_required",
                         "error": "--kind pitfall|constraint 와 --index 가 필요합니다",
                         "next": "note show --all  # index 를 본다"})
        machine_scope = args.kind == "pitfall" and args.scope in _MACHINE_SCOPES
        mf = _machine_note_path()
        doc, doc_file = (_read_notes(mf)[0], mf) if machine_scope else (notes, f)
        entries = doc.get(args.kind + "s", [])
        if not (0 <= args.index < len(entries)):
            return emit({"ok": False, "code": "bad_index",
                         "error": f"--index 는 0~{len(entries) - 1} 이어야 합니다"})
        removed = entries.pop(args.index)
        _save_notes(doc_file, doc)
        return emit({"file": str(doc_file), "removed": removed,
                     "summary": f"{args.kind} #{args.index} 를 지웠습니다", "next": None})

    elif args.action == "target":
        vals = [t.strip() for t in (args.targets or "").split(",") if t.strip()]
        unknown = [t for t in vals if t not in TARGETS]
        if not vals or unknown:
            return emit({
                "ok": False, "code": "bad_targets",
                "error": (f"모르는 타겟: {', '.join(unknown)}" if unknown
                          else "--targets 에 무엇을 밟을 수 있는지 적으세요"),
                "hint": f"{'·'.join(TARGETS)} 중에서 쉼표로 구분 (예: server,web)",
            })
        if not args.why:
            return emit({
                "ok": False, "code": "why_required",
                "error": "--why 에 그렇게 판단한 근거를 적으세요",
                "hint": ("다음에 이 기록을 보는 사람이 맞는지 다시 볼 수 있어야 합니다. "
                         "예: \"Thymeleaf 템플릿으로 화면을 직접 뿌린다\""),
            })
        notes["targets"] = {"value": vals, "why": args.why, "added": today}

    elif args.action == "run":
        if not (args.name or args.text):
            # 인자 없이 부르면 "(지정 안 함)/(기록 없음)" 쓰레기 줄만 쌓인다 (#706)
            return emit({"ok": False, "code": "args_required",
                         "error": "--name(시나리오)이나 --text(결과 요약)가 필요합니다"})
        notes.setdefault("runs", []).append({
            "date": today,
            "scenario": args.name or "(지정 안 함)",
            "result": args.text or "(기록 없음)",
        })
        notes["runs"] = notes["runs"][-30:]   # 오래된 것은 버린다

    _save_notes(f, notes)
    return emit({
        "file": str(f),
        **extra,
        **({"warning": warning} if warning else {}),
        "summary": f"{args.action} 기록 완료 — {f.name}",
        "next": ("app tap 결과(screen_changed)를 보고 note screen --name … --target 라벨 --result ok|fail"
                 if args.action == "screen" and "graded" not in extra and args.target else None),
    })
