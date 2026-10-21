"""시나리오 모양: 타겟별 본보기, 타겟·기대 결과 규칙, 실행 가능 여부 검증"""
from __future__ import annotations

import re


# =========================================================================
# 부트스트랩 — 이 앱이 어떻게 생겼는지 코드에서 읽어낸다
# =========================================================================

_SHARED_DIR = "_shared"
_FLOWS_DIR = "flows"




def _template_for(target: str) -> dict:
    """타겟에 맞는 시나리오 본보기. 타겟마다 밟는 단위와 판정 근거가 다르다."""
    base = {
        "name": "{one line on what this walks}",
        "description": "{why this path matters}",
        "target": target,
        "precondition": None,   # 예: "_shared/login-kakao" — 앞에 붙일 흐름
        "steps": [dict(_STEP_TEMPLATES[target])],
    }
    if target == "app":
        # 참가자가 둘 이상일 때만 채운다. 비워 두면 기존처럼 기기 한 대로 밟는다.
        # 키는 device 서브커맨드의 --role 과 같은 값을 쓴다 (#583).
        base["roles"] = {}
        base["reset"] = {
            "device": "pm clear",
            "server": "{command that deletes the test account. null if none}",
        }
        # 환경 조건은 기기에서만 바꿀 수 있다
        base["conditions"] = [
            {"name": "Large text", "apply": "settings put system font_scale 1.3",
             "revert": "settings put system font_scale 1.0"},
            {"name": "Dark mode", "apply": "cmd uimode night yes",
             "revert": "cmd uimode night no"},
        ]
    elif target == "web":
        base["reset"] = {
            "browser": "{how to clear cookies and local storage. Usually a new context}",
            "server": "{command that deletes the test account. null if none}",
        }
        base["conditions"] = [
            {"name": "Narrow screen", "apply": "viewport 390x844", "revert": "viewport 1280x800"},
            {"name": "Dark mode", "apply": "colorScheme dark", "revert": "colorScheme light"},
        ]
    else:  # server
        base["base_url"] = "{API address. Empty uses the value detect found}"
        base["reset"] = {"server": "{command that deletes test data. null if none}"}
    return base


_REQUIRED_STEP_KEYS = ("screen", "do")

# 타겟별 단계 본보기. 같은 틀을 주면 웹·서버 쓰는 사람이 절반을 지우고 다시 써야 한다.
_STEP_TEMPLATES = {
    "app": {
        "screen": "{screen name}",
        "do": "{what to do — tap 'Start' / input 'value' / back}",
        "expect_screen": "{what should show next}",
        "expect_device": ["{key to check in the log, e.g. app.refreshToken}"],
        "expect_server": "{query to check on the server. null if none}",
        "human": None,
    },
    "web": {
        "screen": "{page name}",
        "do": "{click 'Log in' / type #email 'value' / goto /signup}",
        "expect_url": "{path it should go to, e.g. /home}",
        "expect_text": "{text that should show on screen}",
        "expect_server": "{query to check on the server. null if none}",
        "human": None,
    },
    "other": {
        "screen": "{name of this step}",
        "do": "{the exact command to run, e.g. npx projectops --type spring --yes}",
        "expect_exit": 0,
        "expect_output": "{text the output must contain. null if none}",
        "expect_file": "{path that must exist after the run. null if none}",
        "expect_absent": "{path that must **not** exist after the run. null if none}",
        "human": None,
    },
    "server": {
        "screen": "-",
        "do": "{POST /api/auth/login {\"id\":\"...\"}}",
        "auth": "{{token} to use the token from an earlier step. null if none}",
        "expect_status": 200,
        "expect_json": "{what to check in the response, e.g. $.accessToken is not empty}",
        "save": {"token": "$.accessToken"},
        "expect_server": "{query to check in the DB. null if none}",
        "human": None,
    },
}

# ── 타겟 = 무엇으로 조작하나 ─────────────────────────────────────────────
#
# **target이 정하는 것은 `do`를 누가 실행하느냐뿐이다.** expect_* 는 타겟과 무관하게 붙는다.
# 그래서 "웹에서 밟으며 서버 DB를 확인"하는 조합이 자연스럽게 표현된다 —
# 조작 대상과 판정 근거는 다른 이야기다.
TARGETS = ("app", "web", "server", "other")
# 값이 없는 예전 시나리오는 여기로 떨어진다 — 기존 파일을 한 글자도 고치지 않기 위해서다.
DEFAULT_TARGET = "app"

# 타겟별로 인정하는 기대 결과. 하나도 없으면 "화면이 떴으니 통과"로 끝나므로 막는다.
_EXPECT_KEYS = {
    "app": ("expect_screen", "expect_device", "expect_server"),
    "web": ("expect_screen", "expect_url", "expect_text", "expect_server"),
    "server": ("expect_status", "expect_json", "expect_server"),
    # other 는 화면도 응답도 없다. 남는 것은 **무엇이 만들어졌나**다.
    # expect_absent 가 특히 중요하다 — 지금까지 스킬은 "있어야 할 것"만 봤고,
    # 나오면 안 되는 것(테스트 코드 유출·임시 파일 잔존·구 파일)은 볼 눈이 없었다.
    "other": ("expect_exit", "expect_output", "expect_file", "expect_absent"),
}


def scenario_target(data: dict) -> str:
    """시나리오의 조작 대상. 모르는 값이면 기본값으로 떨어뜨리지 않고 그대로 돌려준다
    — _validate가 잡아서 사용자에게 알려야 조용히 엉뚱한 것을 밟지 않는다."""
    return data.get("target") or DEFAULT_TARGET

def _validate(data: dict) -> list[str]:
    """시나리오가 실행 가능한 모양인지 본다. 밟기 전에 걸러야 중간에 안 멈춘다."""
    problems = []
    if not data.get("name"):
        problems.append("name is empty")

    # 축을 먼저 확정한다. 모르는 값이면 조용히 기본값으로 밟지 않고 여기서 막는다 —
    # 오타 하나로 웹 시나리오가 adb를 타면 원인을 찾기 어렵다.
    target = scenario_target(data)
    if target not in TARGETS:
        problems.append(f"Unknown target '{target}' — must be one of {'·'.join(TARGETS)}")
        target = DEFAULT_TARGET
    expect_keys = _EXPECT_KEYS[target]

    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        problems.append("steps is empty — at least one step to walk is needed")
        return problems
    for i, st in enumerate(steps, 1):
        if not isinstance(st, dict):
            problems.append(f"step {i} is not an object")
            continue
        for k in _REQUIRED_STEP_KEYS:
            if not st.get(k):
                problems.append(f"step {i} has no {k}")
        # ⚠️ falsy 검사를 하면 안 된다. `expect_exit: 0` 은 **가장 흔한 기대값**인데
        #    0 은 falsy 라 "기대 결과가 없다"로 읽혀 멀쩡한 시나리오가 거부된다.
        #    빈 문자열·빈 목록은 안 적은 것으로 본다.
        if not any(st.get(k) not in (None, "", [], {}) for k in expect_keys):
            problems.append(
                f"step {i} ({st.get('screen','?')}) has no expected result — "
                f"one of {'·'.join(k.replace('expect_', '') for k in expect_keys)} "
                "is needed to judge a pass")

    problems += _validate_roles(data, steps, target)
    return problems


# 값 전달은 ${이름} 으로 쓴다. 시나리오 틀이 이미 {중괄호} 를 "여기를 채워라" 표시로
# 쓰고 있어서, 같은 기호를 쓰면 검증기가 둘을 구분하지 못한다 (#583).
_CAPTURE_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _validate_roles(data: dict, steps: list, target: str) -> list[str]:
    """참가자가 둘 이상인 시나리오가 실제로 실행 가능한 모양인지 본다.

    - `device` 가 선언 안 된 역할을 가리키면 어느 기기로 갈지 정해지지 않는다.
    - `${이름}` 을 앞선 단계가 만들지 않았으면 빈 값을 입력하게 된다. "A에서 만든
      값을 B에 넣는다"가 이 검증 없이는 조용히 빈칸으로 밟힌다.
    """
    problems: list[str] = []
    roles = data.get("roles") or {}
    if roles and not isinstance(roles, dict):
        return ["roles must be shaped {role_key: {...}}"]

    used = {st.get("device") for st in steps
            if isinstance(st, dict) and st.get("device")}
    unknown = sorted(d for d in used if d not in roles)
    if unknown:
        problems.append(
            f"step device is not in roles: {', '.join(unknown)} — "
            f"declare it in roles or remove device "
            f"(declared roles: {', '.join(roles) or 'none'})")

    if len(roles) > 1 and target != "app":
        problems.append(
            f"{len(roles)} roles but target is '{target}' — "
            "multiple devices only work for app so far")

    produced: set[str] = set()
    for i, st in enumerate(steps, 1):
        if not isinstance(st, dict):
            continue
        for field in ("do", "text", "expect_screen", "expect_server"):
            for ref in _CAPTURE_REF.findall(str(st.get(field) or "")):
                if ref not in produced:
                    problems.append(
                        f"step {i} uses ${{{ref}}} but no earlier step has "
                        f"capture: \"{ref}\" — it would be walked with an empty value")
        cap = st.get("capture")
        if cap:
            produced.add(cap)
    return problems
