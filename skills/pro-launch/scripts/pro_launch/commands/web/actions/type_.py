"""`web type` — 입력창에 글자를 넣는다. `--keys` 면 키를 하나씩 쳐 넣는다 (xterm · 코드 편집기처럼 fill 이 안 먹는 곳, #930)."""
from __future__ import annotations


from pro_launch.commands.web.element import locate_target, perform_on_target, target_wait_seconds
from pro_launch.commands.web.session import done_payload
from pro_launch.registry import Action

# 키 입력 사이 기본 간격(ms) — 터미널 에뮬레이터가 따라올 만큼
DEFAULT_KEY_DELAY_MILLISECONDS = 60


def _type_keys(page, args, state: dict) -> dict:
    """--keys: 대상(없으면 지금 초점)에 키를 하나씩 친다. fill 과 달리 keydown/keyup 이 발생한다"""
    delay = args.delay_ms if args.delay_ms is not None else DEFAULT_KEY_DELAY_MILLISECONDS
    info = None
    if args.selector or args.ref is not None:
        element, info, failure = locate_target(page, args, state, "type", should_wait=True,
                                               should_guard_mutating=False)
        if failure:
            return failure
        failure = perform_on_target(page, args, "type", info, lambda: element.focus(
            timeout=target_wait_seconds(args) * 1000))
        if failure:
            return failure
    page.keyboard.type(args.keys, delay=delay)
    payload = done_payload("type", page)
    payload.update({"target": info, "mode": "keys", "typed_characters": len(args.keys), "delay_ms": delay,
                    "summary": f"Typed {len(args.keys)} keys ({delay}ms apart)",
                    "next": "web text  # check the input took effect (Enter: web press --key Enter)"})
    return payload


def execute(page, args, state: dict) -> dict:
    if args.keys is not None:
        return _type_keys(page, args, state)
    if not ((args.selector or args.ref is not None) and args.text is not None):
        return {"ok": False, "code": "missing_argument", "url": None,
                "error": "--selector (or --ref) and --text are required (to type key by key, use --keys)"}
    # 입력창이 늦게 그려지는 화면이 있어 선택자는 붙기를 기다린다. 입력은 바꾸는 조작이 아니라 막지 않는다
    element, info, failure = locate_target(page, args, state, "type", should_wait=True,
                                           should_guard_mutating=False)
    if failure:
        return failure
    failure = perform_on_target(page, args, "type", info,
                                lambda: element.fill(args.text, timeout=target_wait_seconds(args) * 1000))
    if failure:
        return failure
    payload = done_payload(args.action, page)
    payload["target"] = info
    return payload


def configure(p) -> None:
    p.add_argument("--keys", default=None,
                   help="Type key by key (current focus if no target). For xterm · web terminals · editors — never for passwords")
    p.add_argument("--delay-ms", dest="delay_ms", type=int, default=None,
                   help=f"--keys: delay between keys (ms, default {DEFAULT_KEY_DELAY_MILLISECONDS})")


ACTION = Action(name="type", run=execute, configure=configure,
                options=("selector", "ref", "text", "secret_text", "target_timeout", "frame", "capture_requests"),
                help="Fill text into an input (passwords via --text-env · --cred, key by key via --keys)",
                example="web type --ref 2 --text-env APP_PW")
