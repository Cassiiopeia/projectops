"""device 동작별 받는 옵션 — 동작이 쓰지 않는 옵션은 조용히 무시하지 않고 bad_args 로 돌려보낸다 (#972).

device 동작은 옵션 묶음 하나를 함께 쓴다(하위 파서 없음). 그래서 acquire 에 준 --yes 처럼 그 동작에 뜻이 없는
옵션이 오류 없이 사라졌다. 여기 표가 동작마다 실제로 읽는 옵션의 원본이다 — 동작이 새 옵션을 읽으면 여기에도 넣는다.
"""
from __future__ import annotations

# 모든 동작이 받는 옵션 (dest 이름)
COMMON_OPTIONS = frozenset({"root"})
# 위치 인자 mode 의 표시 이름
MODE_LABEL = "<mode>"

_DEVICE_TARGET = ("device",)
# 동작 > 그 동작이 읽는 옵션 (dest 이름, mode 는 위치 인자)
OPTIONS_BY_ACTION: dict[str, frozenset[str]] = {
    "list": frozenset({"package", "run_dir"}),
    "bind": frozenset({"role", "serial", "note", "package", "run_dir"}),
    "unbind": frozenset({"role", "package", "run_dir"}),
    "show": frozenset({"package"}),
    "claim": frozenset({*_DEVICE_TARGET, "yes"}),
    "acquire": frozenset({*_DEVICE_TARGET, "platform", "form", "os", "purpose", "reason", "wait", "need", "fresh",
                          "count", "name", "window", "scale", "user_approved"}),
    "release": frozenset({*_DEVICE_TARGET, "lease", "all", "keep_booted", "yes"}),
    "shutdown": frozenset({*_DEVICE_TARGET, "yes"}),
    "create": frozenset({"platform", "reason", "purpose", "name", "form", "os", "ttl_days", "yes"}),
    "clone": frozenset({*_DEVICE_TARGET, "platform", "reason", "purpose", "name", "ttl_days", "yes"}),
    "erase": frozenset({*_DEVICE_TARGET, "platform", "yes"}),
    "delete": frozenset({*_DEVICE_TARGET, "platform", "yes"}),
    "mark": frozenset({*_DEVICE_TARGET, "platform", "kind", "name", "note", "verify"}),
    "unmark": frozenset({*_DEVICE_TARGET, "platform", "kind", "name"}),
    "adopt": frozenset({*_DEVICE_TARGET, "platform"}),
    "records": frozenset({"platform"}),
    "gc": frozenset({"apply", "sizes"}),
    "benchmark": frozenset({"platform", "full", "yes"}),
    "boot": frozenset({*_DEVICE_TARGET, "window", "scale", "cold", "user_approved"}),
    "reboot": frozenset({*_DEVICE_TARGET, "window", "scale", "cold", "yes"}),
    "locale": frozenset({*_DEVICE_TARGET, "lang", "region", "app", "restore", "yes"}),
    "appearance": frozenset({*_DEVICE_TARGET, "mode", "restore", "yes"}),
    "text-size": frozenset({*_DEVICE_TARGET, "mode", "restore", "yes"}),
}


def option_label(dest: str) -> str:
    """dest > 명령줄 표기 (run_dir > --run-dir, mode > <mode>)."""
    return MODE_LABEL if dest == "mode" else "--" + dest.replace("_", "-")


def unused_options(action: str, given: dict, defaults: dict) -> list[str]:
    """이 동작이 읽지 않는데 기본값과 다르게 준 옵션 > 표기 목록. 표에 없는 동작은 거르지 않는다."""
    allowed = OPTIONS_BY_ACTION.get(action)
    if allowed is None:
        return []
    return [option_label(dest) for dest, default in defaults.items()
            if dest not in allowed and dest not in COMMON_OPTIONS and given.get(dest, default) != default]


def unused_options_failure(action: str, unused: list[str]) -> dict:
    """bad_args 응답: 무시될 옵션 · 이 동작이 받는 옵션 · 메모리 위험에 --yes 를 쓴 경우의 안내."""
    valid = sorted(option_label(dest) for dest in OPTIONS_BY_ACTION[action] | COMMON_OPTIONS)
    payload = {"ok": False, "code": "bad_args", "action": action, "unused_options": unused, "valid_options": valid,
               "error": f"device {action} 는 {', '.join(unused)} 를 읽지 않는다 — 그대로 두면 조용히 무시된다",
               "next": f"device {action} 가 받는 옵션만 남겨 다시 부른다: {' '.join(valid)}"}
    if "--yes" in unused and "--user-approved" in valid:
        payload["next"] = ("--yes 를 빼고 다시 부른다 — --yes 는 메모리 위험 게이트를 넘지 않는다. 메모리 위험으로 멈추면 "
                           "사용자에게 reasons 를 보여 주고 답을 받은 뒤 --user-approved 를 붙인다")
    return payload
