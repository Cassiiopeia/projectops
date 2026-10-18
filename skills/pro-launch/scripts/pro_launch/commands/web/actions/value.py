"""`web value` — 입력칸 · 요소의 값을 출력하지 않고 저장한다 (#930).

Client Secret 처럼 입력칸 안에만 있는 값은 `web text` 에 안 나와 OCR 로 읽다 I/l 을 틀렸다. 값은 상태 폴더의 0600 파일에만
쓰고 결과에는 길이와 sha256 앞자리만 싣는다. 다른 입력칸에 넣을 때는 `web type --text-env 이름`.
"""
from __future__ import annotations

import hashlib

from pro_launch.commands.web.element import locate_target
from pro_launch.commands.web.saved_values import invalid_name_failure, is_valid_env_name, save_value, saved_next
from pro_launch.commands.web.session import done_payload
from pro_launch.registry import Action
from pro_launch.runtime.context import project_root

# 입력칸이면 value, 그 밖(복사 버튼 옆 코드 상자 등)이면 보이는 글자
READ_VALUE_JS = "(e) => (typeof e.value === 'string' ? e.value : (e.innerText || e.textContent || ''))"


def execute(page, args, state: dict) -> dict:
    if args.save_env and not is_valid_env_name(args.save_env):
        return invalid_name_failure("value", args.save_env)
    # 읽기만 한다 — 읽기 전용 세션에서도 막지 않는다
    element, info, failure = locate_target(page, args, state, "value", should_wait=True, should_guard_mutating=False)
    if failure:
        return failure
    value = element.evaluate(READ_VALUE_JS)
    info["text"] = ""   # 입력칸 설명의 text 에는 값이 그대로 들어 있다 — 결과에 값이 새지 않게 비운다
    if value is None or value == "":
        return {"ok": False, "code": "value_empty", "action": "value", "target": info, "url": page.url,
                "error": "값이 비어 있습니다", "next": "web inspect  # 값이 든 입력칸을 다시 고른다"}
    payload = done_payload("value", page)
    payload["target"] = info
    if args.save_env:
        payload.update(save_value(project_root(args), args.save_env, value))
        payload["summary"] = f"값 {len(value)}자를 {args.save_env} 로 저장했다 (출력하지 않음)"
        payload["next"] = saved_next(args.save_env)
    else:
        # 저장 이름이 없으면 값은 어디에도 두지 않고 모양만 알린다
        payload.update({"length": len(value), "sha256_prefix": hashlib.sha256(value.encode("utf-8")).hexdigest()[:12],
                        "summary": f"값 {len(value)}자 (저장하지 않음)",
                        "next": "web value --ref <번호> --save-env NAME  # 값을 출력 없이 저장한다"})
    return payload


def configure(p) -> None:
    p.add_argument("--save-env", dest="save_env", default=None,
                   help="값을 이 이름으로 저장한다 (출력하지 않음). web type --text-env 이름 으로 다시 쓴다")


ACTION = Action(name="value", run=execute, configure=configure, options=("selector", "ref", "target_timeout", "frame"),
                help="입력칸 · 요소의 값을 출력하지 않고 저장한다 (길이 · 해시만 보여 준다)",
                example="web value --selector '#client-secret' --save-env CLIENT_SECRET")
