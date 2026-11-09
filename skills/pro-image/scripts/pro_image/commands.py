"""서브커맨드 처리: 입력 해석 > 모듈 호출 > 결과 + next (출력 형식은 image_cli.emit)"""
from __future__ import annotations

import platform
from pathlib import Path

from . import (board, codex_runner, converter, generation, harness, history, image_facts, postprocess, providers,
               settings, svg_render)


def _harness_dir(args) -> Path:
    # --harness > 설정 harness_dir > {레포}/docs/image-harness
    if getattr(args, "harness", None):
        return Path(args.harness).expanduser().resolve()
    return settings.harness_dir(settings.repository_root())


def _provider_row(name: str) -> dict:
    definition = providers.invocation(name)
    row = {"name": name, "kind": definition["kind"], "source": definition["source"],
           "is_available": providers.is_available(definition), "supports_alpha": definition["supports_alpha"]}
    if definition["kind"] == "codex" and row["is_available"]:
        executable = providers.executable_of(definition)
        login = codex_runner.login_facts()
        row.update(version=codex_runner.version(executable), auth_mode=login["auth_mode"],
                   image_generation=codex_runner.is_image_generation_enabled(executable),
                   is_ready=login["auth_mode"] == codex_runner.SUBSCRIPTION_AUTH_MODE
                   or not settings.is_subscription_required())
    else:
        row["is_ready"] = row["is_available"]
    return row


def cmd_providers(_args) -> dict:
    order, source = providers.priority()
    rows = [_provider_row(name) for name in providers.known_names()]
    ready = [name for name in order if any(row["name"] == name and row["is_ready"] for row in rows)]
    payload = {"priority": order, "priority_source": source, "ready_in_order": ready, "providers": rows,
               "converter": converter.available_tool(), "platform": platform.system()}
    if source == "default":
        return {**payload, "code": "ask_priority",
                "summary": f"No saved priority; ready now: {', '.join(ready) or 'none'}",
                "next": "ask the user once which tools to use and in what order, then save image.priority"}
    return {**payload, "summary": f"Will use {ready[0] if ready else 'none'} first ({', '.join(ready)})",
            "next": "harness"}


def cmd_harness(args) -> dict:
    harness_dir = _harness_dir(args)
    created = harness.initialize(harness_dir, settings.repository_root().name, args.character or []) if args.init else []
    described = harness.describe(harness_dir)
    if not described["style"]:
        return {**described, "created": created, "code": "no_style", "summary": "No STYLE.md yet",
                "next": "harness --init, then fill STYLE.md from the app's existing art"}
    return {**described, "created": created, "summary": f"{len(described['characters'])} character(s), "
            f"{len(described['references'])} reference(s), {len(described['kinds'])} kind guide(s)",
            "next": "read STYLE.md and the kind guide you need (`kind <name>`)"}


def cmd_kind(args) -> dict:
    harness_dir = _harness_dir(args)
    entry = harness.find_kind(harness_dir, args.kind)
    if not entry:
        return {"ok": False, "code": "unknown_kind", "kinds": [item["kind"] for item in harness.kinds(harness_dir)],
                "summary": f"No guide for '{args.kind}'", "next": "pick the closest kind, or add kinds/<name>.md"}
    approved = history.read(harness_dir / harness.HISTORY_FILE, args.kind, "approved", 3)
    return {**entry, "guide": Path(entry["path"]).read_text(encoding="utf-8"), "approved_examples": approved,
            "summary": f"{entry['source']} guide for {args.kind}, {len(approved)} approved example(s)"}


def _first_ready_provider() -> str | None:
    order, _ = providers.priority()
    for name in order:
        definition = providers.invocation(name)
        if definition and definition["kind"] != "agent" and generation.check_ready(definition, name) is None:
            return name
    return None


def cmd_run(args) -> dict:
    size = image_facts.parse_size(args.size)
    if not size:
        return {"ok": False, "code": "bad_args", "summary": "--size must look like 1536x1024"}
    prompt_path = Path(args.prompt).expanduser()
    if not prompt_path.is_file():
        return {"ok": False, "code": "prompt_missing", "summary": f"Prompt file not found: {prompt_path}"}
    provider_name = args.provider or _first_ready_provider()
    if not provider_name:
        return {"ok": False, "code": "no_provider", "summary": "No image tool is ready",
                "next": "providers; if none, draw it yourself (claude-vector) and tell the user"}
    harness_dir = _harness_dir(args)
    run_dir = settings.new_run_dir(settings.repository_root(), args.name)
    references = [Path(reference).expanduser() for reference in args.ref or []]
    prompt_text = prompt_path.read_text(encoding="utf-8")
    result = generation.generate(provider_name, args.name, prompt_text, references, size, args.alpha,
                                 args.key_color, harness_dir, run_dir)
    if result.get("ok") and result.get("image"):
        history.append(harness_dir / harness.HISTORY_FILE, {
            "name": args.name, "kind": args.kind, "provider": provider_name, "status": "candidate",
            "image": result["image"]["path"], "size": args.size, "alpha": args.alpha,
            "references": [str(path) for path in references], "prompt": prompt_text})
    return result


def cmd_check(args) -> dict:
    facts = image_facts.read_facts(Path(args.path).expanduser())
    problems = image_facts.find_problems(facts, image_facts.parse_size(args.size), args.alpha)
    return {"image": facts, "problems": problems, "code": "spec_mismatch" if problems else "ok",
            "summary": "matches" if not problems else "; ".join(problems)}


def cmd_remove_bg(args) -> dict:
    source, target = Path(args.path).expanduser(), Path(args.out).expanduser()
    if image_facts.read_facts(source).get("format") != "png":
        converter.to_png(source, target)
        source = target
    result = postprocess.remove_background(source, target, args.key_color, args.tolerance, args.mode)
    if result.get("ok"):
        result.update(image=image_facts.read_facts(target), summary=f"{round(result['transparent_share'] * 100)}% "
                      f"transparent ({result['mode']}, keys {result['keys']})",
                      next="open the result with Read; if edges look cut, lower --tolerance; if a halo remains, raise it")
    return result


def cmd_fit(args) -> dict:
    size = image_facts.parse_size(args.size)
    if not size:
        return {"ok": False, "code": "bad_args", "summary": "--size must look like 1536x1024"}
    target = Path(args.out).expanduser()
    tool = converter.fit(Path(args.path).expanduser(), target, size, args.mode)
    return {"image": image_facts.read_facts(target), "tool": tool, "summary": f"{args.mode} to {args.size} ({tool})"}


def cmd_render_svg(args) -> dict:
    size = image_facts.parse_size(args.size)
    if not size:
        return {"ok": False, "code": "bad_args", "summary": "--size must look like 512x512"}
    target = Path(args.out).expanduser()
    browser = svg_render.render(Path(args.svg).expanduser(), target, size)
    facts = image_facts.read_facts(target)
    return {"image": facts, "browser": browser, "summary": f"rendered {facts.get('width')}x{facts.get('height')}",
            "next": "open it with Read and judge it like any other result"}


def cmd_board(args) -> dict:
    images = [Path(path).expanduser() for path in args.images]
    missing = [str(path) for path in images if not path.is_file()]
    if missing:
        return {"ok": False, "code": "image_missing", "missing": missing, "summary": "Image not found"}
    target = Path(args.out).expanduser()
    method = board.build(images, target)
    return {"board": str(target), "method": method, "order": [str(path) for path in images],
            "summary": f"{len(images)} candidates numbered 1-{len(images)} from the top left",
            "next": "show the board to the user and ask which number to keep (AskUserQuestion)"}


def cmd_record(args) -> dict:
    record = history.append(_harness_dir(args) / harness.HISTORY_FILE, {
        "name": args.name, "kind": args.kind, "provider": args.provider, "status": args.status, "image": args.image,
        "placed_at": args.placed_at, "note": args.note})
    return {"record": record, "summary": f"{args.name} recorded as {args.status}",
            "next": "if the note is a lasting rule, add it to STYLE.md or the kind guide"}


def cmd_history(args) -> dict:
    rows = history.read(_harness_dir(args) / harness.HISTORY_FILE, args.kind, args.status, args.limit)
    return {"entries": rows, "summary": f"{len(rows)} entr{'y' if len(rows) == 1 else 'ies'}"}
