"""scenario: 시나리오 만들기(init) · 목록(list) · 검증(show)"""
from __future__ import annotations

import re
from pathlib import Path

from common.emit import emit

from pro_agent_test.notes.recall import _TARGET_WORDS, _surface
from pro_agent_test.scenario_rules import (TARGETS, _FLOWS_DIR, _SHARED_DIR, _template_for, _validate,
                                           scenario_target)
from pro_agent_test.storage import _expand, _resolve_scenario, _scenario_dir, _scenario_files


# 시나리오 이름으로 허용하는 문자. 한글도 \w 에 든다 — 경로 구분자·선행 점은 못 쓴다
_SAFE_NAME = re.compile(r"\w[\w.\- ]*")


def cmd_scenario(args) -> int:
    root = Path(args.root).resolve()
    d = _scenario_dir(root, create=(args.action == "init"))

    if args.action == "list":
        files = _scenario_files(d)
        rows = []
        for f in files:
            rel = f.relative_to(d)
            # flows/{그룹}/x.json → 그룹 / _shared/x.json → _shared
            # 루트에 그냥 있으면 아직 분류되지 않은 것이다
            if len(rel.parts) > 2 and rel.parts[0] == _FLOWS_DIR:
                group = rel.parts[1]
            elif len(rel.parts) > 1:
                group = rel.parts[0]
            else:
                group = "(미분류)"
            rows.append({"file": str(rel), "name": _safe_name(f), "group": group})
        return emit({
            "dir": str(d),
            "scenarios": rows,
            "summary": f"{len(files)}개" if files else "시나리오 없음",
            "next": None if files else f"bootstrap --path {root} 로 폴더부터 만드세요",
        })

    if args.action == "init":
        if not args.name:
            return emit({"ok": False, "code": "name_required",
                         "error": "--name 으로 파일 이름을 정하세요"})
        if args.target not in TARGETS:
            return emit({"ok": False, "code": "unknown_target",
                         "error": f"target '{args.target}' 을 모릅니다",
                         "hint": f"{'·'.join(TARGETS)} 중 하나"})
        # 이름이 경로가 되면 시나리오 폴더 밖에 파일이 써진다 (#707)
        if not _SAFE_NAME.fullmatch(args.name) or ".." in args.name:
            return emit({"ok": False, "code": "bad_name",
                         "error": f"--name '{args.name}' 에 쓸 수 없는 문자가 있습니다",
                         "hint": "글자·숫자·밑줄·하이픈·점·공백만 쓰고 '/' '\\' '..' 는 쓸 수 없습니다. "
                                 "하위 폴더는 --group 으로 정합니다"})
        if args.group and (args.group.startswith(("/", "\\")) or ".." in Path(args.group).parts
                           or "\\" in args.group):
            return emit({"ok": False, "code": "bad_group",
                         "error": f"--group '{args.group}' 은 폴더 밖을 가리킬 수 없습니다"})
        # --group 을 주면 flows/{그룹}/ 아래, _shared 면 전제로 둔다
        if args.group == _SHARED_DIR:
            target_dir = d / _SHARED_DIR
        elif args.group:
            target_dir = d / _FLOWS_DIR / args.group
        else:
            target_dir = d
        f = target_dir / f"{args.name}.json"
        # 마지막 방어선 — 어떤 경로로든 시나리오 폴더 아래가 아니면 쓰지 않는다
        if d.resolve() not in f.resolve().parents:
            return emit({"ok": False, "code": "bad_name",
                         "error": "시나리오 폴더 밖에는 만들 수 없습니다"})
        target_dir.mkdir(parents=True, exist_ok=True)
        if f.exists() and not args.force:
            return emit({"ok": False, "code": "already_exists",
                         "error": f"{f} 가 이미 있습니다", "hint": "--force 로 덮어씁니다"})
        import json
        f.write_text(json.dumps(_template_for(args.target), ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
        return emit({
            "file": str(f),
            "summary": f"템플릿 생성: {f.relative_to(d)}",
            "next": "중괄호로 표시된 자리를 채운 뒤 scenario show 로 검증하세요",
        })

    # show
    if not args.name:
        return emit({"ok": False, "code": "name_required", "error": "--name 을 지정하세요"})
    f = _resolve_scenario(d, args.name)
    if f is None:
        return emit({"ok": False, "code": "not_found",
                     "error": f"'{args.name}' 을 찾지 못했습니다",
                     "next": f"scenario list --root {root}"})
    import json
    try:
        data, pre_problems = _expand(d, f)
    except json.JSONDecodeError as e:
        return emit({"ok": False, "code": "invalid_json", "error": f"{f}: {e}"})

    problems = _validate(data) + pre_problems
    # 템플릿 자리를 안 채운 채 실행하면 엉뚱한 걸 누른다 — 문제로 잡는다
    placeholders = [k for k in json.dumps(data, ensure_ascii=False).split('"')
                    if k.startswith("{") and k.endswith("}")]
    if placeholders:
        problems.append(
            f"채우지 않은 자리가 {len(placeholders)}개 있습니다 — 템플릿 그대로면 실행할 수 없습니다")

    # 이 시나리오와 겹치는 규칙·함정을 몇 건 싣는다 (시나리오마다 하루 한 번, #837)
    target = scenario_target(data)
    mem = _surface(root, f"scenario:{args.name}",
                   " ".join([json.dumps(data, ensure_ascii=False), _TARGET_WORDS.get(target, "")]))
    return emit({
        "ok": not problems,
        "code": "ok" if not problems else "scenario_invalid",
        **({"memory": mem} if mem else {}),
        "file": str(f.relative_to(d)),
        "scenario": data,
        "precondition": data.get("precondition"),
        "precondition_steps": data.get("_precondition_steps", 0),
        "problems": problems,
        "unfilled_placeholders": placeholders[:10],
        "summary": (f"{data.get('name','?')} — {len(data.get('steps',[]))}단계"
                    + (f", 문제 {len(problems)}건" if problems else "")),
        "next": None if not problems else "problems를 고친 뒤 다시 확인하세요",
    })


def _safe_name(f: Path) -> str:
    import json
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("name", "?")
    except Exception:
        return "(읽기 실패)"
