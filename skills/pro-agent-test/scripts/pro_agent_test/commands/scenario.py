"""scenario: create (init) · list · validate (show) scenarios"""
from __future__ import annotations

import re
from pathlib import Path

from common.emit import emit

from pro_agent_test.notes.recall import _TARGET_WORDS, _surface
from pro_agent_test.scenario_rules import (TARGETS, _FLOWS_DIR, _SHARED_DIR, _template_for, _validate,
                                           scenario_target)
from pro_agent_test.storage import _expand, _resolve_scenario, _scenario_dir, _scenario_files


# Characters allowed in scenario names. Korean also matches \w — path separators and a leading dot are not allowed
_SAFE_NAME = re.compile(r"\w[\w.\- ]*")


def cmd_scenario(args) -> int:
    root = Path(args.root).resolve()
    d = _scenario_dir(root, create=(args.action == "init"))

    if args.action == "list":
        files = _scenario_files(d)
        rows = []
        for f in files:
            rel = f.relative_to(d)
            # flows/{group}/x.json → group / _shared/x.json → _shared
            # sitting directly in the root means not yet classified
            if len(rel.parts) > 2 and rel.parts[0] == _FLOWS_DIR:
                group = rel.parts[1]
            elif len(rel.parts) > 1:
                group = rel.parts[0]
            else:
                group = "(ungrouped)"
            rows.append({"file": str(rel), "name": _safe_name(f), "group": group})
        return emit({
            "dir": str(d),
            "scenarios": rows,
            "summary": f"{len(files)} scenario(s)" if files else "no scenarios",
            "next": None if files else f"create the folder first with bootstrap --path {root}",
        })

    if args.action == "init":
        if not args.name:
            return emit({"ok": False, "code": "name_required",
                         "error": "set the file name with --name"})
        if args.target not in TARGETS:
            return emit({"ok": False, "code": "unknown_target",
                         "error": f"Unknown target '{args.target}'",
                         "hint": f"one of {'·'.join(TARGETS)}"})
        # If the name becomes a path, the file is written outside the scenario folder (#707)
        if not _SAFE_NAME.fullmatch(args.name) or ".." in args.name:
            return emit({"ok": False, "code": "bad_name",
                         "error": f"--name '{args.name}' contains characters that are not allowed",
                         "hint": "use only letters, digits, underscores, hyphens, dots and spaces; '/' '\\' '..' are "
                                 "not allowed. Set a subfolder with --group"})
        if args.group and (args.group.startswith(("/", "\\")) or ".." in Path(args.group).parts
                           or "\\" in args.group):
            return emit({"ok": False, "code": "bad_group",
                         "error": f"--group '{args.group}' cannot point outside the folder"})
        # With --group, under flows/{group}/; _shared means it is a precondition
        if args.group == _SHARED_DIR:
            target_dir = d / _SHARED_DIR
        elif args.group:
            target_dir = d / _FLOWS_DIR / args.group
        else:
            target_dir = d
        f = target_dir / f"{args.name}.json"
        # Last line of defence — never write unless the path is under the scenario folder
        if d.resolve() not in f.resolve().parents:
            return emit({"ok": False, "code": "bad_name",
                         "error": "cannot create outside the scenario folder"})
        target_dir.mkdir(parents=True, exist_ok=True)
        if f.exists() and not args.force:
            return emit({"ok": False, "code": "already_exists",
                         "error": f"{f} already exists", "hint": "overwrite with --force"})
        import json
        f.write_text(json.dumps(_template_for(args.target), ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
        return emit({
            "file": str(f),
            "summary": f"template created: {f.relative_to(d)}",
            "next": "fill in the {braced} placeholders, then validate with scenario show",
        })

    # show
    if not args.name:
        return emit({"ok": False, "code": "name_required", "error": "--name is required"})
    f = _resolve_scenario(d, args.name)
    if f is None:
        return emit({"ok": False, "code": "not_found",
                     "error": f"'{args.name}' not found",
                     "next": f"scenario list --root {root}"})
    import json
    try:
        data, pre_problems = _expand(d, f)
    except json.JSONDecodeError as e:
        return emit({"ok": False, "code": "invalid_json", "error": f"{f}: {e}"})

    problems = _validate(data) + pre_problems
    # Running with template slots unfilled presses the wrong thing — flag it as a problem
    placeholders = [k for k in json.dumps(data, ensure_ascii=False).split('"')
                    if k.startswith("{") and k.endswith("}")]
    if placeholders:
        problems.append(
            f"{len(placeholders)} unfilled placeholder(s) — a scenario left as the template cannot run")

    # Include a few rules and pitfalls overlapping this scenario (once a day per scenario, #837)
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
        "summary": (f"{data.get('name','?')} — {len(data.get('steps',[]))} step(s)"
                    + (f", {len(problems)} problem(s)" if problems else "")),
        "next": None if not problems else "fix the problems, then check again",
    })


def _safe_name(f: Path) -> str:
    import json
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("name", "?")
    except Exception:
        return "(unreadable)"
