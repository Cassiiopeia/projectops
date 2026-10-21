"""`web select` — 드롭다운(<select>)에서 값이나 보이는 이름으로 하나를 고른다 (#892)."""
from __future__ import annotations


from pro_launch.commands.web.element import locate_target, perform_on_target, target_wait_seconds
from pro_launch.commands.web.session import done_payload
from pro_launch.registry import Action

# <select> 의 선택지 목록 (값 · 보이는 이름 · 선택 여부)
OPTIONS_JS = """(e) => e.tagName.toLowerCase() !== 'select' ? null : [...e.options].map(op => ({
  value: op.value, label: (op.label || op.text || '').replace(/\\s+/g, ' ').trim(), selected: op.selected }))"""


def pick_option(options: list[dict], wanted: str) -> dict | None:
    """값 일치 > 이름 일치 > 이름 대소문자 무시 일치 순으로 고른다."""
    for is_match in (lambda o: o["value"] == wanted, lambda o: o["label"] == wanted,
                     lambda o: o["label"].lower() == wanted.strip().lower()):
        hit = next((o for o in options if is_match(o)), None)
        if hit:
            return hit
    return None


def execute(page, args, state: dict) -> dict:
    if args.value is None:
        return {"ok": False, "code": "missing_argument", "error": "--value is required"}
    element, info, failure = locate_target(page, args, state, "select", should_wait=True)
    if failure:
        return failure
    options = element.evaluate(OPTIONS_JS)
    if options is None:
        return {"ok": False, "code": "not_a_select", "action": "select", "target": info, "url": page.url,
                "error": f"'{info.get('tag')}' is not a <select>",
                "next": "For a custom dropdown, open it with web click, then pick the option with web find and click it"}
    chosen = pick_option(options, args.value)
    if chosen is None:
        return {"ok": False, "code": "option_not_found", "action": "select", "target": info, "url": page.url,
                "options": options[:30], "error": f"No option matches '{args.value}'",
                "next": "Call again with one of the value or label entries in options"}
    before = next((o for o in options if o["selected"]), None)
    failure = perform_on_target(page, args, "select", info, lambda: element.select_option(
        value=chosen["value"], timeout=target_wait_seconds(args) * 1000))
    if failure:
        return failure
    payload = done_payload("select", page)
    payload.update({"target": info, "selected": chosen, "before": before,
                    "summary": f"Selected '{chosen['label']}' ({chosen['value']})"})
    return payload


def configure(p) -> None:
    p.add_argument("--value", default=None, help="Value or visible label of the option to pick")


ACTION = Action(name="select", run=execute, configure=configure,
                options=("selector", "ref", "target_timeout", "confirm_mutating"),
                help="Pick one option in a dropdown (<select>) by value or visible label",
                example='web select --ref 4 --value "Seoul"')
