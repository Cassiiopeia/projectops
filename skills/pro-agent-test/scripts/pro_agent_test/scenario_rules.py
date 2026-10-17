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
        "name": "{무엇을 밟는지 한 줄}",
        "description": "{왜 이 경로가 중요한지}",
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
            "server": "{테스트 계정을 지우는 명령. 없으면 null}",
        }
        # 환경 조건은 기기에서만 바꿀 수 있다
        base["conditions"] = [
            {"name": "큰 글씨", "apply": "settings put system font_scale 1.3",
             "revert": "settings put system font_scale 1.0"},
            {"name": "다크모드", "apply": "cmd uimode night yes",
             "revert": "cmd uimode night no"},
        ]
    elif target == "web":
        base["reset"] = {
            "browser": "{쿠키·로컬스토리지를 비우는 방법. 보통 새 컨텍스트}",
            "server": "{테스트 계정을 지우는 명령. 없으면 null}",
        }
        base["conditions"] = [
            {"name": "좁은 화면", "apply": "viewport 390x844", "revert": "viewport 1280x800"},
            {"name": "다크모드", "apply": "colorScheme dark", "revert": "colorScheme light"},
        ]
    else:  # server
        base["base_url"] = "{API 주소. 비우면 detect가 찾은 값을 쓴다}"
        base["reset"] = {"server": "{테스트 데이터를 지우는 명령. 없으면 null}"}
    return base


_REQUIRED_STEP_KEYS = ("screen", "do")

# 타겟별 단계 본보기. 같은 틀을 주면 웹·서버 쓰는 사람이 절반을 지우고 다시 써야 한다.
_STEP_TEMPLATES = {
    "app": {
        "screen": "{화면 이름}",
        "do": "{무엇을 하는지 — tap '시작하기' / input '값' / back}",
        "expect_screen": "{다음에 보여야 할 것}",
        "expect_device": ["{로그에서 확인할 키. 예: app.refreshToken}"],
        "expect_server": "{서버에서 확인할 쿼리. 없으면 null}",
        "human": None,
    },
    "web": {
        "screen": "{페이지 이름}",
        "do": "{click '로그인' / type #email '값' / goto /signup}",
        "expect_url": "{이동해야 할 경로. 예: /home}",
        "expect_text": "{화면에 보여야 할 문구}",
        "expect_server": "{서버에서 확인할 쿼리. 없으면 null}",
        "human": None,
    },
    "other": {
        "screen": "{이 단계 이름}",
        "do": "{돌릴 명령 그대로. 예: npx projectops --type spring --yes}",
        "expect_exit": 0,
        "expect_output": "{출력에 들어 있어야 할 문구. 없으면 null}",
        "expect_file": "{실행 뒤 있어야 할 경로. 없으면 null}",
        "expect_absent": "{실행 뒤 **없어야** 할 경로. 없으면 null}",
        "human": None,
    },
    "server": {
        "screen": "-",
        "do": "{POST /api/auth/login {\"id\":\"...\"}}",
        "auth": "{앞 단계에서 받은 토큰을 쓰려면 {token}. 없으면 null}",
        "expect_status": 200,
        "expect_json": "{응답에서 확인할 것. 예: $.accessToken 이 비지 않는다}",
        "save": {"token": "$.accessToken"},
        "expect_server": "{DB에서 확인할 쿼리. 없으면 null}",
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
        problems.append("name이 비었습니다")

    # 축을 먼저 확정한다. 모르는 값이면 조용히 기본값으로 밟지 않고 여기서 막는다 —
    # 오타 하나로 웹 시나리오가 adb를 타면 원인을 찾기 어렵다.
    target = scenario_target(data)
    if target not in TARGETS:
        problems.append(f"target '{target}' 을 모릅니다 — {'·'.join(TARGETS)} 중 하나여야 합니다")
        target = DEFAULT_TARGET
    expect_keys = _EXPECT_KEYS[target]

    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        problems.append("steps가 비었습니다 — 무엇을 밟을지 한 단계라도 있어야 합니다")
        return problems
    for i, st in enumerate(steps, 1):
        if not isinstance(st, dict):
            problems.append(f"{i}번째 step이 객체가 아닙니다")
            continue
        for k in _REQUIRED_STEP_KEYS:
            if not st.get(k):
                problems.append(f"{i}번째 step에 {k}가 없습니다")
        # ⚠️ falsy 검사를 하면 안 된다. `expect_exit: 0` 은 **가장 흔한 기대값**인데
        #    0 은 falsy 라 "기대 결과가 없다"로 읽혀 멀쩡한 시나리오가 거부된다.
        #    빈 문자열·빈 목록은 안 적은 것으로 본다.
        if not any(st.get(k) not in (None, "", [], {}) for k in expect_keys):
            problems.append(
                f"{i}번째 step({st.get('screen','?')})에 기대 결과가 없습니다 — "
                f"{'·'.join(k.replace('expect_', '') for k in expect_keys)} 중 하나는 "
                "있어야 통과 판정을 할 수 있습니다")

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
        return ["roles 는 {역할키: {...}} 모양이어야 합니다"]

    used = {st.get("device") for st in steps
            if isinstance(st, dict) and st.get("device")}
    unknown = sorted(d for d in used if d not in roles)
    if unknown:
        problems.append(
            f"step 의 device 가 roles 에 없습니다: {', '.join(unknown)} — "
            f"roles 에 선언하거나 device 를 지우세요 "
            f"(선언된 역할: {', '.join(roles) or '없음'})")

    if len(roles) > 1 and target != "app":
        problems.append(
            f"roles 가 {len(roles)}개인데 target 이 '{target}' 입니다 — "
            "기기를 여러 대 쓰는 것은 아직 app 에서만 됩니다")

    produced: set[str] = set()
    for i, st in enumerate(steps, 1):
        if not isinstance(st, dict):
            continue
        for field in ("do", "text", "expect_screen", "expect_server"):
            for ref in _CAPTURE_REF.findall(str(st.get(field) or "")):
                if ref not in produced:
                    problems.append(
                        f"{i}번째 step 이 ${{{ref}}} 를 쓰는데 앞선 단계에 "
                        f"capture: \"{ref}\" 가 없습니다 — 빈 값으로 밟게 됩니다")
        cap = st.get("capture")
        if cap:
            produced.add(cap)
    return problems
