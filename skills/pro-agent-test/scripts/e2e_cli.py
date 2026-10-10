#!/usr/bin/env python3
"""e2e_cli — pro-agent-test 전용 CLI (projectops 3-layer 표준, Layer 2).

**QA 절차만** 담는다. 앱·웹·서버를 띄우고 조작하고 찍는 능력은 pro-launch 로 옮겼다 (#629·#631).

서브커맨드:
    detect    무엇을 밟을 수 있는지 — pro-launch detect 결과 + 확인해 적어 둔 타겟(note target)
    scenario  밟기 시나리오 만들기 · 목록 · 검증
    note      이 프로젝트에서 알아낸 것을 쌓는다
    api       서버 시나리오를 끝까지 밟는다 (단건 요청은 pro-launch http)
    other     앱·웹·서버가 아닌 것을 밟는다

옮긴 명령(doctor · devices · device · web · access · db · logs · shrink · get-output-path)은
**한 마이너 버전 동안** pro-launch 로 그대로 넘겨주고, 결과에 새 자리를 알리는 next 를 싣는다.

출력: MCP-style JSON (ok/code/summary/next 4필드 보장).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common import memory as _memory  # noqa: E402
from common.access import find_secrets as _find_secrets  # noqa: E402
from common.access import load_access as _load_access  # noqa: E402
from common.cli_parser import JSONArgumentParser, run_cli  # noqa: E402
from common.emit import emit  # noqa: E402
from common.http import request as _http_request  # noqa: E402
from common.state import base_dir as _base_dir  # noqa: E402
from common.state import repo_key, state_dir  # noqa: E402


# =========================================================================
# pro-launch 로 옮긴 명령 — 넘겨주기 층 (#631)
# =========================================================================
#
# 스킬끼리 파이썬 import 는 하지 않는다. 같은 플러그인 안의 launch_cli.py 를
# 서브프로세스로 부르고, 결과는 그대로 돌려주되 "이제 저쪽을 쓰라"는 next 를 싣는다.
# 다음 마이너에서 이 층을 지운다.

MOVED = ("doctor", "devices", "device", "web", "access", "db", "logs", "shrink",
         "get-output-path")

_LAUNCH_CLI = _HERE.parents[2] / "pro-launch" / "scripts" / "launch_cli.py"


def _launch(argv: list[str]) -> tuple[dict | None, str, int]:
    """launch_cli 를 부르고 (JSON, 원문, 종료코드). 표준입력은 넘기지 않는다."""
    if not _LAUNCH_CLI.is_file():
        return None, "", 1
    r = subprocess.run([sys.executable, str(_LAUNCH_CLI), *argv], capture_output=True,
                       text=True, encoding="utf-8", stdin=subprocess.DEVNULL,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    try:
        data = json.loads((r.stdout or "").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        data = None
    return data, (r.stdout or "") + (r.stderr or ""), r.returncode


def delegate(argv: list[str]) -> int:
    """옮긴 명령을 pro-launch 로 넘긴다. 산출물은 여전히 agent-test 폴더에 받는다."""
    cmd = argv[0]
    if cmd == "get-output-path" and "--skill" not in argv:
        argv = [*argv, "--skill", "agent-test"]
    data, raw, rc = _launch(argv)
    if data is None and rc == 0 and raw.strip():
        # --help 처럼 JSON 이 아닌 정상 출력 — 그대로 보여준다
        sys.stdout.write(raw)
        return 0
    if data is None:
        return emit({"ok": False, "code": "launch_unavailable",
                     "error": f"pro-launch 의 launch_cli.py 를 부르지 못했습니다 ({_LAUNCH_CLI})",
                     "output": raw[-400:],
                     "hint": "projectops 설치가 온전한지 확인하세요 — pro-launch 가 함께 깔려 있어야 합니다"})
    moved = f"pro-launch 의 launch_cli.py {cmd} 를 쓴다 (e2e_cli {cmd} 는 다음 마이너에서 제거)"
    data["moved_to"] = f"launch_cli.py {cmd}"
    data["next"] = f"{data['next']} · {moved}" if data.get("next") else moved
    return emit(data)


# =========================================================================
# detect — 띄울 수 있는 것(pro-launch) + 확인해 적어 둔 것(note target)
# =========================================================================

def _recorded_targets(root: Path) -> dict | None:
    """agent가 코드를 보고 확인해 적어 둔 것. 선언보다 이쪽을 믿는다."""
    notes, _ = _load_notes(root)
    rec = notes.get("targets")
    if not isinstance(rec, dict):
        return None
    vals = [t for t in rec.get("value", []) if t in TARGETS]
    return {"targets": vals, "why": rec.get("why")} if vals else None


def cmd_detect(args) -> int:
    """무엇을 밟을 수 있는지. 판정 순서: ① --target ② note target ③ version.yml ④ 마커 파일.

    ③④ 와 기기·브라우저 정보는 pro-launch 가 준다. 여기서는 QA 가 확인해 적어 둔 것만 얹는다.
    """
    start = Path(args.path).resolve()
    data, raw, _ = _launch(["detect", "--path", str(start)])
    if data is None:
        return emit({"ok": False, "code": "launch_unavailable",
                     "error": "pro-launch detect 를 부르지 못했습니다", "output": raw[-400:]})
    root = Path(data.get("root") or start)

    targets = list(data.get("kinds") or [])
    source = data.get("source")
    rec = _recorded_targets(root)
    if rec:
        targets, source = rec["targets"], "recorded"
    if getattr(args, "target", None):
        if args.target not in TARGETS:
            return emit({"ok": False, "code": "unknown_target",
                         "error": f"target '{args.target}' 을 모릅니다",
                         "hint": f"{'·'.join(TARGETS)} 중 하나"})
        targets = [args.target]

    # 감지와 다른 타겟으로 정해졌으면 그 타겟의 정보(기기·브라우저·접속)를 다시 모은다.
    # 안 그러면 "web 을 밟는다"고 적어 두고도 브라우저 준비 상태를 못 본다.
    launchable = [t for t in targets if t in ("app", "web", "server")]
    if launchable and set(launchable) != set(data.get("kinds") or []):
        again, _, _ = _launch(["detect", "--path", str(start), "--kinds", ",".join(launchable)])
        if again is not None:
            data = again

    payload: dict = {k: v for k, v in data.items()
                     if k not in ("kinds", "source", "confirm", "summary", "next", "ok", "code")}
    payload.update({"targets": targets, "target_source": source,
                    "knowledge_dir": str(_home_dir(root))})
    if rec:
        # 왜 그렇게 판단했는지를 함께 보여준다 — 다음에 이 기록이 맞는지 다시 볼 수 있어야 한다
        payload["recorded_why"] = rec.get("why")

    # version.yml 은 **무엇인가**를 선언할 뿐, 무엇을 밟을 수 있는지가 아니다 (#591).
    # 서버가 화면을 직접 뿌리는 구조면 web 도 밟아야 한다 — 판단은 agent 의 일이다.
    if source == "version.yml" and not getattr(args, "target", None):
        payload["confirm"] = {
            "why": ("이 targets 는 version.yml 선언에서 나왔습니다 — 확인된 것이 아닙니다. "
                    "서버가 화면을 직접 뿌리면 web 도 밟아야 합니다"),
            "check": ("코드를 보고 판단하세요: 템플릿 폴더(templates·views·resources/templates)·"
                      "정적 파일·라우트가 HTML을 돌려주는지. 앱·웹 클라이언트가 한 레포에 "
                      "같이 있는 경우도 마찬가지입니다"),
            "record": (f"note target --root {root} --targets {','.join(targets) or 'server'}"
                       ",web --why \"{판단 근거}\"   # 맞으면 그대로 두면 됩니다"),
        }

    nxt = None
    if not targets:
        nxt = "무엇을 밟을지 알 수 없습니다 — --target app|web|server|other 로 직접 알려주세요"
    elif "app" in targets:
        dev = (payload.get("app") or {}).get("devices") or {}
        if not (dev.get("android") or dev.get("ios_booted")):
            nxt = "pro-launch devices  # 기기가 없습니다. AVD 나 시뮬레이터를 부팅하세요"
    if not nxt and "web" in targets and not ((payload.get("web") or {}).get("playwright") or {}).get("ready"):
        nxt = "pro-launch web setup  # 웹을 밟으려면 브라우저가 필요합니다 (먼저 사용자에게 묻는다)"
    # 이 앱에서 알아낸 규칙·함정을 몇 건 싣는다 — note show 를 부르지 않아도 보이게 (#837)
    mem = _surface(root, "detect:" + ",".join(targets),
                   " ".join([*targets, *(_TARGET_WORDS.get(t, "") for t in targets)]))
    if mem:
        payload["memory"] = mem
    payload["summary"] = f"{root.name}: 타겟={'·'.join(targets) if targets else '없음'} ({source})"
    payload["next"] = nxt
    return emit(payload)


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


def _repo_key(root: Path) -> str:
    """프로젝트를 가리키는 키 (common/state.py 가 단독으로 정한다)."""
    return repo_key(root)


def _home_dir(root: Path) -> Path:
    """쌓은 것(learned.json · 시나리오 · flows)을 두는 곳. 프로젝트 밖(홈)이라 워크트리를 만들어도 살아남는다.

    기기·브라우저·접속 정보는 pro-launch 의 자리(~/.projectops/launch/)로 옮겼다 (#629).
    """
    return state_dir("agent-test", root)


def _scenario_dir(root: Path, create: bool = False) -> Path:
    """시나리오·지식을 둘 곳.

    예전에는 프로젝트 안(`docs/testing/e2e`)이었는데, 그 폴더는 .gitignore로 추적에서
    빠져 있어 **새 워크트리에 복사되지 않았다.** 이슈마다 워크트리를 만드는 흐름에서는
    이슈 하나가 끝날 때마다 쌓은 지식이 통째로 사라졌다 (이슈 #586).

    이제 홈에 두고 git remote로 프로젝트를 구분한다.
    """
    home = _home_dir(root)
    if create and not home.is_dir():
        home.mkdir(parents=True, exist_ok=True)
    return home


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


def _scenario_files(d: Path) -> list[Path]:
    """시나리오 파일 목록. flows/ 하위와 _shared/ 를 함께 본다.

    app-map·learned 는 시나리오가 아니므로 제외한다.
    """
    if not d.is_dir():
        return []
    # app-map 은 bootstrap 시절 산출물, memory_seen 은 기억을 실은 날 기록 (#837)
    skip = {"app-map.json", _NOTE_FILE, _SEEN_FILE}
    out = [f for f in d.rglob("*.json")
           if f.name not in skip and not f.name.startswith("learned.broken-")]
    return sorted(out)


def _resolve_scenario(d: Path, name: str) -> Path | None:
    """이름으로 파일을 찾는다. `flows/auth/x` 처럼 경로를 줘도, `x` 만 줘도 된다."""
    direct = d / f"{name}.json"
    # 폴더 밖 파일(../x)은 시나리오가 아니다 (#707)
    if direct.exists() and d.resolve() in direct.resolve().parents:
        return direct
    matches = [f for f in _scenario_files(d) if f.stem == name]
    return matches[0] if len(matches) == 1 else None


def _expand(d: Path, path: Path, seen: list[str] | None = None) -> tuple[dict, list[str]]:
    """전제를 펼쳐 전체 단계를 만든다.

    로그인처럼 거의 모든 시나리오의 앞에 붙는 흐름을 매번 적지 않게 한다.
    순환 참조는 여기서 끊는다 — 무한 재귀로 죽는 대신 문제로 보고한다.
    """
    import json
    seen = seen or []
    key = str(path)
    if key in seen:
        return {}, [f"전제가 순환합니다: {' → '.join(seen + [key])}"]
    data = json.loads(path.read_text(encoding="utf-8"))
    pre = data.get("precondition")
    if not pre:
        return data, []

    target = _resolve_scenario(d, pre)
    if target is None:
        return data, [f"전제 '{pre}' 를 찾지 못했습니다"]
    base, problems = _expand(d, target, seen + [key])
    merged = dict(data)
    merged["steps"] = list(base.get("steps", [])) + list(data.get("steps", []))
    merged["_precondition_steps"] = len(base.get("steps", []))
    if base.get("reset") and not data.get("reset"):
        merged["reset"] = base["reset"]
    return merged, problems


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


# =========================================================================
# 학습 노트 — 이 프로젝트에서만 통하는 것을 쌓아 간다
# =========================================================================
#
# 기억 원칙: skills/references/memory-principles.md (#833 · #837)
#  - 읽기는 agent 호출에 맡기지 않는다 → detect · scenario show 응답에 몇 건만 싣는다 (_surface)
#  - 쓰기 전에 비슷한 항목을 찾는다 → 확실하면 합치고, 애매하면 related 로 보여 준다
#  - 성적(ok·fail·last_seen)과 낡음 → 지우지 않고 verify 로 표시해 뒤로 민다
#  - 레포와 무관한 것(flutter·platform)은 이 컴퓨터 범위 한 곳에 둔다

_NOTE_FILE = "learned.json"
_SEEN_FILE = "memory_seen.json"     # 응답에 기억을 실은 날 (하루·영역 1회)
_MACHINE = "_machine"               # ~/.projectops/agent-test/_machine/ — 이 컴퓨터 범위

_SHOW_MAX = 5                       # note show 요약: 제약·함정 각각 이만큼
_SHOW_CHARS = 120                   # 요약에서 항목당 글자 수
_SURFACE_CHARS = 200                # 응답에 싣는 항목당 글자 수 (원칙: 200자)
_NOTE_MIN_WORDS = 3                 # 고유어가 이보다 적은 짧은 문장은 자동으로 합치지 않는다
_MACHINE_SCOPES = ("flutter", "platform")


def _note_path(root: Path, create: bool = False) -> Path:
    return _scenario_dir(root, create) / _NOTE_FILE


def _machine_note_path() -> Path:
    return _base_dir() / "agent-test" / _MACHINE / _NOTE_FILE


# 이 파일이 담는 구조의 판. 필드를 없애는 변경을 할 때만 올린다.
# 2: screens 에 variants 축 추가 (#583)
# 3: variants 의 taps(픽셀) → targets(요소·비율), 원본은 legacy_taps 로 보존 (#838)
_NOTE_SCHEMA = 3


def _variant_key(role: str | None, screen_size: str | None) -> str:
    """좌표 한 벌을 구분하는 키.

    해상도가 같아도 **빌드가 다르면 화면이 다르다.** 역할마다 다른 빌드가 깔리는 일이
    흔해서(한쪽만 재설치되기도 한다) 역할을 키에 넣는다. 역할 이름은 JSON 키로만
    쓰이므로 한글·공백이 들어와도 안전하다 — 셸 변수명으로는 쓰지 않는다.
    """
    return "%s@%s" % (role or "default", screen_size or "?")


def _promote_screen(entry: dict) -> dict:
    """구 포맷(화면당 좌표 한 벌)을 변형 하나로 올린다.

    읽는 순간 올리고 파일은 다음 쓰기에 갱신된다. 기존 프로젝트가 쌓아 둔 기록을
    깨뜨리지 않는 것이 조건이다 — 지우고 다시 재라고 하면 아무도 안 쓴다.
    """
    if "variants" in entry:
        return entry
    legacy = {k: entry.pop(k) for k in ("taps", "measured_on") if k in entry}
    entry["variants"] = ({_variant_key(None, legacy.get("measured_on")): legacy}
                         if legacy else {})
    return entry


_SIZE = re.compile(r"(\d{2,5})x(\d{2,5})")
_LOCATORS = ("text", "id", "desc")


def _fmt_ratio(v: float) -> str:
    """0.815 처럼 짧게. 소수 넷째 자리면 1080 폭에서도 1px 안쪽이다."""
    return f"{round(v, 4):.4f}".rstrip("0").rstrip(".") or "0"


def _px_to_at(xy: str, size: str | None) -> str | None:
    """'540,1956' @ '1080x2400' → '0.5,0.815'. 바꿀 수 없으면 None."""
    m = _SIZE.fullmatch(size or "")
    p = re.fullmatch(r"\s*(\d+)\s*,\s*(\d+)\s*", xy or "")
    if not (m and p):
        return None
    w, h = int(m.group(1)), int(m.group(2))
    x, y = int(p.group(1)), int(p.group(2))
    if not (0 <= x <= w and 0 <= y <= h):
        return None
    return f"{_fmt_ratio(x / w)},{_fmt_ratio(y / h)}"


def _migrate_variant(v: dict) -> dict:
    """픽셀 taps 를 비율 targets 로 바꾼다 (#838).

    `launch_cli app tap` 은 픽셀을 거절한다(#826). 옛 기록을 그대로 두면 쓸 수 없다.
    바꾼 값은 계산일 뿐 확인된 것이 아니라 verify 를 붙이고, 원본은 legacy_taps 로 남긴다.
    읽을 때마다 메모리에서 바꾸고, 파일은 다음 쓰기에서 갱신된다.
    """
    taps = v.get("taps")
    if not isinstance(taps, dict):
        return v
    v.pop("taps")
    targets = v.setdefault("targets", {})
    unconverted = []
    for label, xy in taps.items():
        if label in targets:
            continue
        at = _px_to_at(str(xy), v.get("measured_on"))
        if at:
            targets[label] = {"at": at, "verify": True}
        else:
            unconverted.append(label)
    v["legacy_taps"] = {**(v.get("legacy_taps") or {}), **taps}
    if unconverted:
        # 해상도를 모르면 비율로 바꿀 수 없다 — 지우지 않고 다시 재라고 알린다
        v["unconverted"] = sorted(set((v.get("unconverted") or []) + unconverted))
    return v


def _migrate_screens(notes: dict) -> None:
    screens = notes.get("screens")
    if not isinstance(screens, dict):
        return
    for entry in screens.values():
        if not isinstance(entry, dict):
            continue
        _promote_screen(entry)
        for v in (entry.get("variants") or {}).values():
            if isinstance(v, dict):
                _migrate_variant(v)


def _read_notes(f: Path) -> tuple[dict, str | None]:
    """쌓인 기록을 읽는다. 읽지 못해도 **지우지 않는다.**

    반환: (내용, 경고). 경고가 있으면 호출부가 사용자에게 알려야 한다.

    깨진 파일을 빈 값으로 덮으면 그동안 쌓은 것이 조용히 사라진다. 편집 중 충돌이나
    부분 쓰기로 깨질 수 있으므로, 이때는 원본을 따로 보관하고 새로 시작한다.
    """
    import json
    from datetime import datetime

    empty = {"schema": _NOTE_SCHEMA, "constraints": [], "screens": {},
             "pitfalls": [], "runs": []}
    if not f.exists():
        return empty, None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("최상위가 객체가 아닙니다")
    except (json.JSONDecodeError, ValueError, OSError) as e:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = f.with_suffix(f".broken-{stamp}.json")
        try:
            backup.write_bytes(f.read_bytes())
            where = str(backup.name)
        except OSError:
            where = "(백업 실패)"
        return empty, f"{f.name}을 읽지 못했습니다({e}). 원본을 {where}로 옮겼습니다"

    # 모르는 필드는 건드리지 않는다 — 다른 하네스나 다음 버전이 쓴 것일 수 있다
    for k, v in empty.items():
        data.setdefault(k, v)
    for k in ("constraints", "pitfalls", "runs"):
        if not isinstance(data.get(k), list):
            data[k] = []
    _migrate_screens(data)
    return data, None


def _load_notes(root: Path) -> tuple[dict, str | None]:
    return _read_notes(_note_path(root))


def _save_notes(f: Path, notes: dict) -> None:
    """원자적으로 쓴다 — 쓰는 도중 멈춰도 기존 파일이 깨지지 않는다.

    쓸 때 판 번호를 지금 판으로 올린다 — 읽을 때 바꾼 구조(targets 등)가 이때 파일에 들어간다.
    """
    import json
    import os
    notes["schema"] = _NOTE_SCHEMA
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f"{f.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(notes, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.replace(tmp, f)      # 같은 파일시스템 안에서는 원자적이다


# ── 항목 요약 · 응답에 싣기 ─────────────────────────────────────────────

def _brief(i: int, e: dict, chars: int, now: str | None = None, scope: str | None = None) -> dict:
    ok, fail, last = _memory.stats(e)
    row = {"index": i, "text": _memory.clip(e.get("text"), chars)}
    if e.get("check"):
        row["check"] = _memory.clip(e["check"], chars)
    if scope:
        row["scope"] = scope
    if ok or fail:
        row["ok"], row["fail"] = ok, fail
    if _memory.needs_verify(e, now):
        row["verify"] = True
    return row


def _ranked(entries: list, now: str | None = None) -> list[tuple[int, dict]]:
    rows = [(i, e) for i, e in enumerate(entries) if isinstance(e, dict) and e.get("text")]
    rows.sort(key=lambda r: _memory.rank(r[1], now), reverse=True)
    return rows


def _target_verify(t: dict, now: str | None = None) -> bool:
    """화면 대상은 성적이 생긴 뒤에만 낡음을 따진다 — 갓 적은 대상을 '오래됨'으로 보지 않는다."""
    if t.get("verify"):
        return True
    return ("ok" in t or "fail" in t) and _memory.needs_verify(t, now)


def _screen_view(entry: dict, full: bool) -> dict:
    """화면 기록. 요약에서는 누를 대상만 보여 준다 — 원본 픽셀은 --all 에서만."""
    if full:
        return entry
    out = {"anchor": entry.get("anchor"), "variants": {}}
    for k, v in (entry.get("variants") or {}).items():
        if not isinstance(v, dict):
            continue
        tg = {}
        for label, t in (v.get("targets") or {}).items():
            if not isinstance(t, dict):
                continue
            tg[label] = _locator(t)
            if _target_verify(t):
                tg[label]["verify"] = True
        row = {"targets": tg}
        for kk in ("measured_on", "build", "unconverted"):
            if v.get(kk):
                row[kk] = v[kk]
        out["variants"][k] = row
    return out


# 타겟별로 맥락에 더하는 말 — 함정 문장과 겹칠 만한 것
_TARGET_WORDS = {
    "app": "앱 화면 에뮬레이터 기기 adb 스크롤 좌표 Flutter",
    "web": "웹 브라우저 페이지 화면 viewport",
    "server": "서버 API DB 로그 요청 응답 토큰",
    "other": "명령 실행 파일 출력",
}


def _surface(root: Path, slot: str, context: str, now: str | None = None) -> dict | None:
    """응답에 실을 기억 — 제약 2 · 함정 2 · 이 컴퓨터 범위 함정 1 까지.

    agent 가 `note show` 를 부르지 않아도 보이게 한다(원칙 1). slot(영역)마다 하루 한 번만
    싣는다 — 매번 실으면 토큰만 쓰고 아무도 읽지 않는다. 실패가 크게 앞서는 것은 싣지 않는다.
    """
    # HOME 이 상대 경로면 작업 폴더 아래에 기록이 생긴다 — 쓰지 않는다
    if not _base_dir().is_absolute():
        return None
    seen_file = _home_dir(root) / _SEEN_FILE
    if _memory.seen_today(seen_file, slot, now, mark=False):
        return None
    if not _note_path(root).exists() and not _machine_note_path().exists():
        return None
    notes, _ = _load_notes(root)
    machine, _ = _read_notes(_machine_note_path())
    ctx = _memory.words(context)

    def pick(entries: list, n: int, scope: str | None = None, need_ctx: bool = False) -> list:
        rows = []
        for i, e in _ranked(entries, now):
            if _memory.hidden(e):
                continue
            rel = len(_memory.words(f"{e.get('text', '')} {e.get('check') or ''}") & ctx)
            if need_ctx and not rel:
                continue
            rows.append((rel, _memory.rank(e, now), i, e))
        rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
        out, kept = [], []
        for _, _, i, e in rows:
            if any(_memory.similar(e, k, field="text", min_words=_NOTE_MIN_WORDS) for k in kept):
                continue
            kept.append(e)
            out.append(_brief(i, e, _SURFACE_CHARS, now, scope))
            if len(out) >= n:
                break
        return out

    constraints = pick(notes.get("constraints") or [], 2)
    pitfalls = pick(notes.get("pitfalls") or [], 2)
    # 이 컴퓨터 범위는 맥락과 겹칠 때만 — 모든 레포에 모든 플랫폼 함정을 들이밀지 않는다
    pitfalls += pick(machine.get("pitfalls") or [], 1, scope="machine", need_ctx=True)
    if not (constraints or pitfalls):
        return None
    _memory.seen_today(seen_file, slot, now, mark=True)
    out = {}
    if constraints:
        out["constraints"] = constraints
    if pitfalls:
        out["pitfalls"] = pitfalls
    out["note"] = ("이 앱에서 알아낸 규칙·함정 일부다(하루 한 번). 전부는 note show --all. "
                   "다시 확인했으면 note pitfall|constraint --index N --result ok|fail 로 남긴다")
    return out


# ── 쓰기 전에 비슷한 것 찾기 ────────────────────────────────────────────

def _find_dup(text: str, lists: dict[str, list]) -> tuple[tuple[str, int] | None, list[dict]]:
    """(합칠 자리 (범위, 위치) 또는 None, 애매하게 비슷한 것들). 범위 순서대로 먼저 찾은 것이 이긴다."""
    probe = {"text": text}
    hit, related = None, []
    for scope, entries in lists.items():
        best, rel = _memory.find_similar(probe, entries, field="text", min_words=_NOTE_MIN_WORDS)
        if best is not None and hit is None:
            hit = (scope, best)
        for i, sc in rel:
            related.append({"scope": scope, "index": i, "score": sc,
                            "text": _memory.clip(entries[i].get("text"), _SHOW_CHARS)})
    related.sort(key=lambda r: -r["score"])
    return hit, related[:3]


def _new_entry(text: str, today: str, **extra) -> dict:
    """새 항목. 겪어서 적는 것이므로 한 번 확인된 것(ok=1)으로 시작한다."""
    e = {"text": text, **{k: v for k, v in extra.items() if v is not None}, "added": today}
    _memory.bump(e, "ok", today)
    return e


# ── 화면 대상 (#838) ────────────────────────────────────────────────────

class _TargetError(ValueError):
    def __init__(self, code: str, message: str, hint: str | None = None):
        super().__init__(message)
        self.code, self.hint = code, hint


def _parse_target(spec: str, size: str | None) -> tuple[str, dict]:
    """'라벨=text:문구' · '라벨=id:x|index=1' · '라벨=at:0.5,0.8' → (라벨, 대상).

    픽셀은 받지 않는다 — app tap 이 픽셀을 거절하므로 저장해 봐야 쓸 수 없다(#826).
    해상도를 알면 비율로 바꾼 값을 안내한다.
    """
    label, sep, rest = spec.partition("=")
    label = label.strip()
    if not (sep and label and rest.strip()):
        raise _TargetError("bad_target", f"--target '{spec}' 는 '라벨=종류:값' 형식이어야 합니다",
                           "예: 로그인=text:로그인하기 / 메뉴=id:menu_btn / 지도핀=at:0.5,0.8")
    rest = rest.strip()
    px = re.fullmatch(r"(?:at:)?\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*", rest)
    if px and (float(px.group(1)) > 1 or float(px.group(2)) > 1):
        conv = _px_to_at(f"{int(float(px.group(1)))},{int(float(px.group(2)))}", size)
        raise _TargetError(
            "pixels_rejected", f"--target '{spec}' 는 픽셀 좌표입니다 — 저장하지 않습니다",
            (f"비율로 적으세요: --target \"{label}=at:{conv}\" ({size} 기준). " if conv else
             "화면 크기로 나눈 0~1 비율로 적으세요(--screen-size 를 주면 바꿔 드립니다). ")
            + "요소가 보이면 text:/id:/desc: 가 먼저입니다")
    kind, colon, val = rest.partition(":")
    kind = kind.strip().lower()
    if not colon or kind not in (*_LOCATORS, "at"):
        raise _TargetError("bad_target", f"--target '{spec}' 의 종류를 모릅니다",
                           "text: · id: · desc: · at: 중 하나 (예: 시작=text:시작하기)")
    if kind == "at":
        m = re.fullmatch(r"\s*(\d*\.?\d+)\s*,\s*(\d*\.?\d+)\s*", val)
        if not m or not all(0 <= float(g) <= 1 for g in m.groups()):
            raise _TargetError("bad_target", f"--target '{spec}' 의 at 은 0~1 비율 두 개여야 합니다",
                               "예: 시작=at:0.5,0.815")
        return label, {"at": f"{_fmt_ratio(float(m.group(1)))},{_fmt_ratio(float(m.group(2)))}"}
    idx = None
    m = re.search(r"\|index=(\d+)\s*$", val)
    if m:
        idx, val = int(m.group(1)), val[:m.start()]
    if not val.strip():
        raise _TargetError("bad_target", f"--target '{spec}' 의 값이 비었습니다")
    t = {kind: val.strip()}
    if idx is not None:
        t["index"] = idx
    return label, t


def _locator(t: dict) -> dict:
    return {k: t[k] for k in (*_LOCATORS, "index", "at") if k in t}


def _tap_hint(t: dict) -> str:
    """이 대상을 누르는 launch_cli 인자."""
    if "at" in t:
        return f"app tap --at {t['at']}"
    k = next(k for k in _LOCATORS if k in t)
    s = f"app tap --{k} \"{t[k]}\""
    return s + (f" --index {t['index']}" if t.get("index") else "")


def _note_screen(args, notes: dict, today: str) -> dict:
    """화면 기록을 쓰거나(--target 라벨=…) 성적을 남긴다(--result + --target 라벨). 실패면 ok=False 결과."""
    if not args.name:
        return {"ok": False, "code": "args_required", "error": "--name 이 필요합니다"}
    # 쓰레기 값이 learned.json 에 남으면 다음 실행마다 그대로 읽힌다 — 쓰기 전에 거른다 (#706)
    if args.screen_size and not _SIZE.fullmatch(args.screen_size):
        return {"ok": False, "code": "bad_screen_size",
                "error": f"--screen-size '{args.screen_size}' 는 가로x세로 숫자여야 합니다",
                "hint": "예: 1080x2400"}
    screens = notes.setdefault("screens", {})
    existing = screens.get(args.name)

    if args.result:
        # 성적 기록 — app tap 으로 눌러서 화면이 바뀌었으면 ok, 못 찾았거나 그대로면 fail
        labels = [t.split("=", 1)[0].strip() for t in (args.target or []) if t.strip()]
        if not labels:
            return {"ok": False, "code": "args_required",
                    "error": "--result 에는 --target 라벨(누른 대상 이름)이 필요합니다"}
        if not existing:
            return {"ok": False, "code": "screen_not_found",
                    "error": f"화면 '{args.name}' 기록이 없습니다", "next": "note show --all"}
        variants = existing.get("variants") or {}
        want = (_variant_key(args.role, args.screen_size)
                if (args.role or args.screen_size) else None)
        graded = []
        for label in labels:
            cands = [(k, v) for k, v in variants.items()
                     if isinstance(v, dict) and label in (v.get("targets") or {})
                     and (want is None or k == want)]
            if len(cands) != 1:
                return {"ok": False,
                        "code": "target_not_found" if not cands else "ambiguous_variant",
                        "error": (f"'{args.name}' 에 '{label}' 대상이 없습니다" if not cands else
                                  f"'{label}' 이 여러 기기 기록에 있습니다: {', '.join(k for k, _ in cands)}"),
                        "hint": "--role · --screen-size 로 어느 기록인지 고릅니다"}
            k, v = cands[0]
            t = v["targets"][label]
            counted = _memory.bump(t, args.result, today)
            graded.append({"variant": k, "label": label, "ok": t["ok"], "fail": t["fail"],
                           "counted": counted, "verify": _target_verify(t, today)})
        return {"ok": True, "graded": graded}

    if args.taps:
        # 옛 입력. 픽셀은 저장하지 않는다 — 바꾼 비율을 알려 준다 (#838)
        conv = [f"{t.split('=', 1)[0]}=at:{_px_to_at(t.split('=', 1)[1], args.screen_size)}"
                for t in args.taps if "=" in t and _px_to_at(t.split("=", 1)[1], args.screen_size)]
        return {"ok": False, "code": "pixels_rejected",
                "error": "--taps 는 픽셀 좌표라 더는 받지 않습니다 — app tap 이 픽셀을 거절합니다",
                "hint": ("--target 으로 적으세요" + (f": {' '.join(repr(c) for c in conv)}" if conv else
                         " (요소면 '라벨=text:문구', 캔버스면 '라벨=at:0.5,0.8')"))}
    if not existing and not args.anchor:
        return {"ok": False, "code": "args_required",
                "error": "새 화면에는 --anchor(이 화면임을 알아보는 단서)가 필요합니다"}

    key = _variant_key(args.role, args.screen_size)
    size = args.screen_size or ((existing or {}).get("variants", {}).get(key) or {}).get("measured_on")
    parsed = {}
    for spec in args.target or []:
        try:
            label, t = _parse_target(spec, size)
        except _TargetError as e:
            return {"ok": False, "code": e.code, "error": str(e), **({"hint": e.hint} if e.hint else {})}
        parsed[label] = t

    entry = _promote_screen(screens.setdefault(args.name, {}))
    if args.anchor:
        entry["anchor"] = args.anchor          # 이 화면임을 알아보는 단서
    variant = entry["variants"].setdefault(key, {})
    targets = variant.setdefault("targets", {})
    for label, t in parsed.items():
        cur = targets.get(label)
        if isinstance(cur, dict) and _locator(cur) == t:
            continue                           # 같은 대상이면 성적을 지킨다
        targets[label] = t                     # 대상이 바뀌면 옛 성적을 물려받지 않는다
    if args.screen_size:
        variant["measured_on"] = args.screen_size
    if args.build:
        # 빌드가 바뀌면 화면도 바뀔 수 있다. 막지 않고 꺼낼 때 알려 준다.
        variant["build"] = args.build
    variant["updated"] = today
    entry["updated"] = today
    return {"ok": True, "variant": key, "targets": {k: _tap_hint(v) for k, v in targets.items()}}


# ── note tidy — 범위가 섞인 기록을 제자리로 옮긴다 (#837) ────────────────
#
# 실측(어느 앱): 함정 39건 중 flutter/platform 18건이 "스킬로 올려라"는 안내만 받고 레포에
# 쌓였고, 도구 사용법(ASC 로그인 등)은 launch knowledge 와 겹쳤다. 옮기기만 하고 지우지 않는다.

# 도구 사용법으로 보이는 말 → launch knowledge 의 영역
_TOOL_AREAS = (
    ("web", re.compile(r"(?i)\bgstack\b|\bplaywright\b|\bchromium\b|\bCDP\b|App Store Connect"
                       r"|\bheaded\b|\bbrowse\b")),
    ("ios", re.compile(r"(?i)\bmaestro\b|\bsimctl\b|\bxcrun\b|\btestflight\b")),
    # uiautomator·AVD 같은 말은 QA 판단(이 화면을 결함으로 적지 마라 등)에도 나와 넣지 않는다
    ("android", re.compile(r"(?i)\bscreenrecord\b")),
)
# 부정 단정("X 는 안 된다")은 기억하지 않는 것이 원칙이다 — 옮기지 않고 다시 볼 목록에만 올린다
_NEGATIVE = re.compile(r"안 ?된다|수 없다|불가")
_TOOL_ANY = re.compile(r"(?i)\blaunch_cli\b|\be2e_cli\b")
_LAUNCH_HOW_MAX = 200     # pro-launch knowledge.MAX_HOW — 넘으면 잘려 저장되므로 옮기지 않는다


def _tool_area(text: str) -> tuple[bool, str | None]:
    """(도구 사용법인가, launch 영역)."""
    for area, pat in _TOOL_AREAS:
        if pat.search(text):
            return True, area
    return bool(_TOOL_ANY.search(text)), None


def _launch_key(text: str) -> str:
    """launch knowledge 키. 영문 단어 몇 개 + 짧은 해시 — 같은 키면 기존 항목을 덮으므로 겹치지 않게 한다."""
    ascii_words = re.findall(r"[A-Za-z][A-Za-z0-9_.-]+", text)[:3]
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:4]
    return "-".join([*(w.lower() for w in ascii_words), digest])[:60] or f"pitfall-{digest}"


def _tidy_plan(notes: dict, overrides: dict[int, str]) -> dict:
    to_machine, to_launch, skipped, review = [], [], [], []
    for i, p in enumerate(notes.get("pitfalls") or []):
        if not isinstance(p, dict) or not p.get("text"):
            continue
        text, scope = p["text"], p.get("scope", "project")
        if _NEGATIVE.search(text):
            review.append({"index": i, "text": _memory.clip(text, _SHOW_CHARS),
                           "reason": "부정 단정 — 지금도 맞는지 확인하고, 아니면 note forget 또는 --result fail"})
        is_tool, area = _tool_area(text)
        if i in overrides:
            is_tool, area = True, overrides[i]
        if is_tool:
            if not area:
                skipped.append({"index": i, "text": _memory.clip(text, _SHOW_CHARS),
                                "reason": "도구 사용법으로 보이나 영역을 못 정했다 — --launch "
                                          f"{i}=web|ios|android|server 로 지정하거나 그대로 둔다"})
                continue
            if len(" ".join(text.split())) > _LAUNCH_HOW_MAX:
                skipped.append({"index": i, "text": _memory.clip(text, _SHOW_CHARS),
                                "reason": f"{_LAUNCH_HOW_MAX}자를 넘어 launch 에 그대로 못 옮긴다 — 줄여서 "
                                          f"launch_cli learn --area {area} 로 남기고 note forget --index {i}"})
                continue
            to_launch.append({"index": i, "area": area, "key": _launch_key(text),
                              "scope": "repo" if scope == "project" else "machine",
                              "text": _memory.clip(text, _SHOW_CHARS)})
        elif scope in _MACHINE_SCOPES:
            to_machine.append({"index": i, "scope": scope, "text": _memory.clip(text, _SHOW_CHARS)})
    return {"to_machine": to_machine, "to_launch": to_launch, "skipped": skipped, "review": review}


def _note_tidy(args, root: Path, notes: dict, today: str) -> dict:
    overrides = {}
    for o in args.launch or []:
        i, sep, area = o.partition("=")
        if not (sep and i.strip().isdigit() and area.strip() in ("ios", "android", "web", "server")):
            return {"ok": False, "code": "bad_launch",
                    "error": f"--launch '{o}' 는 '번호=영역' 형식이어야 합니다", "hint": "예: 28=web"}
        overrides[int(i)] = area.strip()
    plan = _tidy_plan(notes, overrides)
    if not args.apply:
        n = len(plan["to_machine"]) + len(plan["to_launch"])
        return {"ok": True, "applied": False, **plan,
                "summary": (f"옮길 것 {n}건 (이 컴퓨터 {len(plan['to_machine'])} · "
                            f"launch {len(plan['to_launch'])}) · 남길 것 {len(plan['skipped'])}건 — 아직 안 옮겼다"),
                "next": f"note tidy --apply --root {root}  # 계획대로 옮긴다" if n else None}

    pits = notes.get("pitfalls") or []
    moved: set[int] = set()
    failed = []
    for row in plan["to_launch"]:
        data, raw, rc = _launch(["learn", "--area", row["area"], "--key", row["key"],
                                 "--how", " ".join(pits[row["index"]]["text"].split()),
                                 "--result", "ok", "--scope", row["scope"], "--root", str(root)])
        if data and data.get("ok"):
            moved.add(row["index"])
            row["launch"] = {"key": (data.get("entry") or {}).get("key"), "scope": data.get("scope")}
        else:
            failed.append({**row, "error": (data or {}).get("error") or raw[-200:]})

    mf = _machine_note_path()
    machine, warn = _read_notes(mf)
    if warn:
        return {"ok": False, "code": "machine_unreadable", "error": warn}
    merged = 0
    for row in plan["to_machine"]:
        p = pits[row["index"]]
        hit, _ = _find_dup(p["text"], {"machine": machine["pitfalls"]})
        if hit:
            # 같은 지식이 이미 있다 — 성적을 합치고 더 최근 문장을 남긴다
            m = machine["pitfalls"][hit[1]]
            ok, fail, last = _memory.stats(m)
            pok, pfail, plast = _memory.stats(p)
            m["ok"], m["fail"] = ok + pok, fail + pfail
            if plast > last:
                m["text"], m["last_seen"] = p["text"], plast
            merged += 1
        else:
            machine["pitfalls"].append({**p, "from": _repo_key(root)})
        moved.add(row["index"])
    # 이 컴퓨터 범위를 먼저 쓴다 — 중간에 멈춰도 사라지지 않고 겹칠 뿐이다
    if plan["to_machine"]:
        _save_notes(mf, machine)
    if moved:
        notes["pitfalls"] = [p for i, p in enumerate(pits) if i not in moved]
        _save_notes(_note_path(root, create=True), notes)
    return {"ok": not failed, "code": "ok" if not failed else "partly_moved", "applied": True,
            **plan, "failed": failed, "machine_file": str(mf), "merged_in_machine": merged,
            "summary": (f"{len(moved)}건 옮김 (이 컴퓨터 {len(plan['to_machine'])} · launch "
                        f"{len(plan['to_launch']) - len(failed)}, 합침 {merged}) · 남김 {len(plan['skipped'])}"),
            "next": "note show  # 결과를 본다" if not failed else "failed 의 error 를 보고 고친다"}


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


# =========================================================================
# 엣지케이스 — 코드에서 "밟아야 할 실패 경로"를 뽑아낸다
# =========================================================================

# (정규식, 무엇을 밟아야 하는가, 어떻게 만드는가)
_SECRET_KEYS = ("password", "secret", "token", "key")


# ── 서버 타겟: API 시퀀스를 밟는다 (이슈 #586) ───────────────────────────
#
# 화면이 없는 백엔드도 이 스킬로 검증한다. 핵심은 **이전 응답에서 값을 뽑아 다음
# 요청에 물리는 것**이다 — 로그인 없이는 그다음 요청이 전부 401이라 한 걸음도 못 간다.

def _parse_do(do: str) -> tuple[str, str, dict | None]:
    """단계의 `do`를 메서드·경로·본문으로 가른다.

    형식: `POST /api/auth/login {"id": "x"}`  (본문은 없어도 된다)
    """
    m = re.match(r"\s*([A-Z]+)\s+(\S+)\s*(\{.*\}|\[.*\])?\s*$", do, re.S)
    if not m:
        raise ValueError(
            f'단계를 읽을 수 없습니다: {do!r} — "POST /api/x {{...}}" 형식이어야 합니다')
    body = None
    if m.group(3):
        try:
            body = json.loads(m.group(3))
        except json.JSONDecodeError as e:
            raise ValueError(f"본문이 올바른 JSON이 아닙니다: {e}") from e
    return m.group(1).upper(), m.group(2), body


def _fill(value, saved: dict):
    """{token} 자리에 앞 단계에서 저장한 값을 끼운다. 중첩 구조도 따라 내려간다."""
    if isinstance(value, str):
        def sub(m):
            key = m.group(1)
            if key not in saved:
                raise ValueError(f"{{{key}}} 를 채울 값이 없습니다 — 앞 단계의 save를 확인하세요")
            return str(saved[key])
        return re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", sub, value)
    if isinstance(value, dict):
        return {k: _fill(v, saved) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill(v, saved) for v in value]
    return value


def _jsonpath(data, expr: str):
    """`$.a.b[0]` 정도만 읽는다.

    전체 JSONPath 라이브러리를 쓰지 않는 이유는 이 스크립트가 표준 라이브러리만으로
    돌아야 하기 때문이다. 응답에서 토큰 하나 꺼내는 데는 이걸로 충분하다.
    """
    cur = data
    for part in re.findall(r"[^.\[\]]+|\[\d+\]", expr.lstrip("$.")):
        if part.startswith("["):
            idx = int(part[1:-1])
            if not isinstance(cur, list) or idx >= len(cur):
                return None
            cur = cur[idx]
        else:
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
    return cur


def _api_call(base: str, method: str, path: str, body, headers: dict, timeout: int = 30) -> dict:
    """한 요청을 보낸다. 실패해도 예외로 끝내지 않는다 — 실패 응답 자체가 검증 대상인 경우가 많다."""
    url = path if path.startswith("http") else base.rstrip("/") + "/" + path.lstrip("/")
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json", "Accept": "application/json", **headers}
    r = _http_request(method, url, h, data, timeout=timeout)
    r.pop("raw", None)
    r.pop("headers", None)
    return r


# =========================================================================
# other — 앱·웹·서버가 아닌 것을 밟는다
#
# CI 워크플로·CLI 툴·라이브러리·템플릿·배치. 종류를 열거하지 않는다 — 열거하면
# 목록에 없는 것은 또 못 한다.
#
# **무엇을 돌릴지와 무엇이 맞는지는 agent 가 정한다.** 여기서 하는 일은 셋뿐이다.
#   ① 돌리고 종료코드·출력을 돌려준다
#   ② 실행 전후 **파일 변화**를 보여준다 — 사람은 출력만 보고 부작용을 놓친다
#   ③ 두 번 돌려 같은지 본다 — 멱등은 중요한데 손으로는 거의 안 해본다
# =========================================================================

# 파일 목록을 뜰 때 건너뛸 것. 이것을 세면 느리기만 하고 알려주는 것이 없다.
_SNAP_SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__",
              ".gradle", "build", "dist", ".next", ".dart_tool", "Pods"}
_SNAP_MAX = 20000          # 이보다 많으면 관찰을 포기하고 그 사실을 알린다


def _fingerprint(f: Path, digest: bool) -> tuple:
    """파일 한 개의 지문.

    **두 가지 다른 질문에 같은 기준을 쓰면 안 된다** (실측으로 겪었다).

      "이 명령이 무엇을 건드렸나"  → 수정시각. 덮어썼으면 건드린 것이다.
      "두 번 돌려도 상태가 같은가"  → **내용**. 덮어써도 내용이 같으면 멱등이다.

    앞의 것은 stat 만으로 충분하고(싸다), 뒤의 것은 내용을 읽어야 한다(비싸다).
    그래서 내용 해시는 `--twice` 일 때만 뜬다.
    """
    st = f.stat()
    if not digest:
        # 나노초까지 본다. 초 단위로 보면 같은 초에 같은 크기로 바뀐 파일을 놓친다
        # — 실측으로 겪었다 ("old" → "new" 가 안 잡혔다).
        return (st.st_size, st.st_mtime_ns)
    h = hashlib.sha256()
    with f.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return (st.st_size, h.hexdigest())


def _snapshot(paths: list[Path], digest: bool = False) -> tuple[dict, str | None]:
    """경로별 파일 상태. 너무 많으면 (부분, 경고)를 돌려준다."""
    seen: dict[str, tuple] = {}
    for base in paths:
        if not base.exists():
            continue
        if base.is_file():
            seen[str(base)] = _fingerprint(base, digest)
            continue
        for f in base.rglob("*"):
            if len(seen) >= _SNAP_MAX:
                return seen, f"파일이 {_SNAP_MAX}개를 넘어 관찰을 멈췄습니다 — --watch 를 좁히세요"
            if any(part in _SNAP_SKIP for part in f.parts):
                continue
            try:
                if f.is_file():
                    seen[str(f)] = _fingerprint(f, digest)
            except OSError:
                continue
    return seen, None


def _diff_snapshot(before: dict, after: dict, root: Path) -> dict:
    def rel(p: str) -> str:
        try:
            return str(Path(p).relative_to(root))
        except ValueError:
            return p
    created = sorted(rel(k) for k in after.keys() - before.keys())
    deleted = sorted(rel(k) for k in before.keys() - after.keys())
    modified = sorted(rel(k) for k in (after.keys() & before.keys()) if before[k] != after[k])
    return {"created": created[:100], "modified": modified[:100], "deleted": deleted[:100],
            "counts": {"created": len(created), "modified": len(modified), "deleted": len(deleted)}}


def _tail(text: str, n: int = 40) -> str:
    lines = (text or "").splitlines()
    return "\n".join(lines[-n:])


def _exec_once(command: str, cwd: Path, env: dict, timeout: int) -> dict:
    t0 = time.time()
    try:
        r = subprocess.run(["bash", "-lc", command], cwd=str(cwd), env=env,
                           capture_output=True, text=True, timeout=timeout)
        return {"exit_code": r.returncode, "stdout": r.stdout or "", "stderr": r.stderr or "",
                "elapsed_ms": int((time.time() - t0) * 1000), "timed_out": False}
    except subprocess.TimeoutExpired:
        return {"exit_code": None, "stdout": "", "stderr": "",
                "elapsed_ms": int((time.time() - t0) * 1000), "timed_out": True}


def _judge(step: dict, run: dict, cwd: Path) -> list[str]:
    """기대 결과와 대조한다. 조건을 주지 않았으면 아무 말도 하지 않는다."""
    bad: list[str] = []
    if run["timed_out"]:
        return ["제한 시간 안에 끝나지 않았습니다"]

    want_exit = step.get("expect_exit")
    if want_exit is not None and run["exit_code"] != want_exit:
        bad.append(f"종료코드가 {run['exit_code']} 입니다 (기대: {want_exit})")

    want_out = step.get("expect_output")
    if want_out:
        if want_out not in (run["stdout"] + run["stderr"]):
            bad.append(f"출력에 '{want_out}' 이 없습니다")

    # 존재 여부는 **실행 뒤** 기준이다. 변화가 아니다 — 변화는 files 를 본다.
    want_file = step.get("expect_file")
    if want_file and not (cwd / want_file).exists():
        bad.append(f"'{want_file}' 이 만들어지지 않았습니다")

    absent = step.get("expect_absent")
    if absent and (cwd / absent).exists():
        bad.append(f"'{absent}' 이 남아 있습니다 — 나오면 안 되는 것입니다")
    return bad


def _run_other_step(step: dict, root: Path, cwd: Path, watch: list[Path],
                    env: dict, timeout: int, twice: bool) -> dict:
    before, warn = (_snapshot(watch) if watch else ({}, None))
    run = _exec_once(step["do"], cwd, env, timeout)
    after, warn2 = (_snapshot(watch) if watch else ({}, None))

    out: dict = {
        "do": step["do"],
        "exit_code": run["exit_code"],
        "elapsed_ms": run["elapsed_ms"],
        "stdout_tail": _tail(run["stdout"]),
        "stderr_tail": _tail(run["stderr"]),
    }
    if run["timed_out"]:
        out["timed_out"] = True
    if watch:
        out["files"] = _diff_snapshot(before, after, root)
    if warn or warn2:
        out["watch_warning"] = warn or warn2

    problems = _judge(step, run, cwd)

    if twice and not run["timed_out"]:
        # 멱등은 **내용** 기준이다. 1회차 뒤 상태를 내용으로 떠 둔다.
        content1, _ = (_snapshot(watch, digest=True) if watch else ({}, None))
        run2 = _exec_once(step["do"], cwd, env, timeout)
        content2, _ = (_snapshot(watch, digest=True) if watch else ({}, None))

        # **멱등은 "한 번 더 돌려도 상태가 그대로"다.** 변화 목록끼리 비교하면 안 된다 —
        # 1회차는 파일을 만들고(created) 2회차는 덮어쓰므로(modified) 목록은 당연히
        # 다르고, 그래도 결과 상태는 같을 수 있다. 실측으로 오판을 겪어 고쳤다.
        settled = (content1 == content2) if watch else None
        out["second_run"] = {
            "exit_code": run2["exit_code"],
            "same_exit": run2["exit_code"] == run["exit_code"],
            "same_stdout": run2["stdout"] == run["stdout"],
            "settled": settled,          # 두 번째 실행 뒤 내용이 그대로인가
            "changed_again": (_diff_snapshot(content1, content2, root) if watch else None),
        }
        # 멱등이 깨진 것이 곧 결함은 아니다 — 로그·타임스탬프가 섞였을 수도 있다.
        # 판단은 agent 가 한다. 여기서는 "달랐다"는 사실만 올린다.
        if run2["exit_code"] != run["exit_code"]:
            problems.append(f"두 번째 실행의 종료코드가 다릅니다 ({run['exit_code']} → {run2['exit_code']})")
        elif settled is False:
            d = out["second_run"]["changed_again"]["counts"]
            # **단정하지 않는다.** 실측해 보니 세 건 다 타임스탬프와 append-only 로그
            # 때문이었다. 매번 "멱등이 아니다"라고 외치면 사람이 곧 무시하게 된다.
            # 사실만 올리고 어디를 보면 되는지 알려준다 — 판단은 agent 가 한다.
            problems.append(
                f"두 번 돌리자 상태가 또 바뀌었습니다 (생성 {d['created']} · 수정 {d['modified']} "
                f"· 삭제 {d['deleted']}) — second_run.changed_again 의 파일을 열어 "
                f"시간·로그 때문인지, 진짜로 멱등이 아닌지 보세요")

    out["problems"] = problems
    out["ok"] = not problems
    return out


def cmd_other(args) -> int:
    """명령을 돌리고, 무엇이 만들어졌는지까지 함께 본다."""
    root = Path(args.root).resolve()
    cwd = Path(args.cwd).resolve() if args.cwd else root
    if not cwd.is_dir():
        return emit({"ok": False, "code": "cwd_not_found", "error": f"{cwd} 가 없습니다"})

    env = dict(os.environ)
    for kv in (args.env or []):
        if "=" not in kv:
            return emit({"ok": False, "code": "bad_env",
                         "error": f"--env 는 K=V 형태여야 합니다: {kv}"})
        k, v = kv.split("=", 1)
        env[k] = v

    watch = [Path(w) if Path(w).is_absolute() else (cwd / w) for w in (args.watch or [])]

    # ── 시나리오를 밟는 경우: 화면을 보고 판단할 것이 없으므로 한 번에 끝까지 간다
    #    (server 타겟과 같은 이유. 앞이 실패하면 뒤는 밟지 않는다 — 진짜 원인이 묻힌다)
    if args.name:
        d = _scenario_dir(root)
        f = _resolve_scenario(d, args.name)
        if f is None:
            return emit({"ok": False, "code": "scenario_not_found",
                         "error": f"시나리오 '{args.name}' 을 찾지 못했습니다",
                         "next": f"scenario list --root {root}"})
        data, pre = _expand(d, f)
        problems = _validate(data) + pre
        if problems:
            return emit({"ok": False, "code": "scenario_invalid", "problems": problems})
        if scenario_target(data) != "other":
            return emit({"ok": False, "code": "wrong_target",
                         "error": f"이 시나리오의 target은 '{scenario_target(data)}' 입니다",
                         "hint": "other run --name 은 other 타겟 전용입니다"})

        results, failed_at = [], None
        for i, st in enumerate(data["steps"], 1):
            if st.get("human"):
                results.append({"step": i, "human": st["human"], "skipped": True})
                continue
            r = _run_other_step(st, root, cwd, watch, env, args.timeout, args.twice)
            r["step"] = i
            r["screen"] = st.get("screen")
            results.append(r)
            if not r["ok"]:
                failed_at = i
                break
        return emit({
            "ok": failed_at is None,
            "code": "ok" if failed_at is None else "step_failed",
            "scenario": data.get("name"),
            "steps": results,
            "failed_at": failed_at,
            "summary": ("끝까지 밟았습니다" if failed_at is None
                        else f"{failed_at}번째 단계에서 멈춤"),
            "next": (None if failed_at is None else
                     "stderr_tail 과 files 를 읽고 원인을 짚으세요"),
        })

    # ── 한 번만 돌리는 경우
    if not args.command:
        return emit({"ok": False, "code": "args_required",
                     "error": "--command 또는 --name 중 하나가 필요합니다",
                     "hint": "--command 는 한 번 돌리고, --name 은 시나리오를 끝까지 밟습니다"})

    step = {"do": args.command}
    for k, v in (("expect_exit", args.expect_exit), ("expect_output", args.expect_output),
                 ("expect_file", args.expect_file), ("expect_absent", args.expect_absent)):
        if v is not None:
            step[k] = v
    r = _run_other_step(step, root, cwd, watch, env, args.timeout, args.twice)
    judged = any(k in step for k in _EXPECT_KEYS["other"])
    r.update({
        "code": "ok" if r["ok"] else "expectation_failed",
        "cwd": str(cwd),
        "judged": judged,
        "summary": (f"종료코드 {r['exit_code']} · {r['elapsed_ms']}ms"
                    + (f" · 문제 {len(r['problems'])}건" if r["problems"] else "")),
        "next": (None if judged else
                 "기대 결과를 주지 않았습니다 — 출력과 files 를 읽고 직접 판단하세요"),
    })
    return emit(r)


def cmd_api(args) -> int:
    """서버 시나리오를 밟는다.

    한 번의 호출로 시나리오 전체를 밟는다 — 앱·웹과 달리 화면을 보고 판단할 것이
    없으므로 쪼갤 이유가 없고, 토큰 체이닝이 한 프로세스 안에서 끝나야 단순하다.
    """
    root = Path(args.root).resolve()
    d = _scenario_dir(root)
    f = _resolve_scenario(d, args.name)
    if f is None:
        return emit({"ok": False, "code": "scenario_not_found",
                     "error": f"시나리오 '{args.name}' 을 찾지 못했습니다",
                     "next": f"scenario list --root {root}"})

    data, problems = _expand(d, f)
    if problems:
        return emit({"ok": False, "code": "scenario_invalid", "problems": problems})
    problems = _validate(data)
    if problems:
        return emit({"ok": False, "code": "scenario_invalid", "problems": problems})
    if scenario_target(data) != "server":
        return emit({"ok": False, "code": "wrong_target",
                     "error": f"이 시나리오의 target은 '{scenario_target(data)}' 입니다",
                     "hint": "api 는 server 타겟 전용입니다"})

    base = args.base_url or data.get("base_url") or ""
    if not base or base.startswith("{"):
        # 시나리오에 없으면 기록해 둔 것을 쓴다. 코드에서 짐작하지 않는다.
        rec = _load_access(root).get("base_url")
        base = (rec.get("url") if isinstance(rec, dict) else rec) or ""
    if not base:
        return emit({"ok": False, "code": "base_url_required",
                     "error": "API 주소를 알 수 없습니다",
                     "next": ("--base-url 로 넘기거나, 코드를 읽어 알아낸 뒤 "
                              "access set --key base_url --json '{\"url\":\"http://...\"}'")})

    if not re.match(r"https?://[^\s/]+", base):
        return emit({"ok": False, "code": "bad_base_url",
                     "error": f"API 주소 '{base}' 는 http(s):// 로 시작해야 합니다",
                     "next": "--base-url http://127.0.0.1:8080 처럼 전체 주소를 넘긴다"})

    saved: dict = {}
    results = []
    failed_at = None
    for i, st in enumerate(data["steps"], 1):
        if st.get("human"):
            results.append({"step": i, "status": "paused", "human": st["human"]})
            failed_at = i
            break
        try:
            method, path, body = _parse_do(_fill(st["do"], saved))
            body = _fill(body, saved) if body is not None else None
            headers = {}
            if st.get("auth"):
                headers["Authorization"] = f"Bearer {_fill(st['auth'], saved)}"
        except ValueError as e:
            results.append({"step": i, "status": "error", "error": str(e)})
            failed_at = i
            break

        res = _api_call(base, method, path, body, headers, timeout=args.timeout)
        row = {"step": i, "do": f"{method} {path}", "elapsed_ms": res.get("elapsed_ms")}
        if not res["ok"]:
            row.update({"status": "error", "error": res["error"]})
            results.append(row)
            failed_at = i
            break

        row["http_status"] = res["status"]
        checks = []
        want = st.get("expect_status")
        if want is not None:
            ok = res["status"] == want
            checks.append({"expect_status": want, "got": res["status"], "ok": ok})
        # expect_json 은 사람이 읽는 설명이다. 자동 판정은 save/상태코드로 하고,
        # 여기서는 실제 응답을 함께 남겨 agent가 눈으로 대조하게 한다.
        if st.get("expect_json"):
            row["response"] = res["json"]
            checks.append({"expect_json": st["expect_json"], "ok": None})
        if st.get("expect_server"):
            row["expect_server"] = st["expect_server"]   # 실제 조회는 db 서브커맨드로

        for key, expr in (st.get("save") or {}).items():
            val = _jsonpath(res["json"], expr) if res["json"] is not None else None
            saved[key] = val
            checks.append({"save": key, "from": expr, "got": None if val is None else "받음",
                           "ok": val is not None})

        row["checks"] = checks
        row["status"] = "ok" if all(c.get("ok") is not False for c in checks) else "fail"
        results.append(row)
        if row["status"] == "fail":
            failed_at = i
            break

    done = failed_at is None
    return emit({
        "ok": done,
        "scenario": data.get("name"),
        "base_url": base,
        "steps": results,
        "saved_keys": sorted(saved),
        "summary": (f"{len(results)}단계 전부 통과" if done
                    else f"{failed_at}번째 단계에서 멈춤"),
        "next": (None if done else
                 "logs --root <루트>  # 서버 로그로 원인을 좁히세요. 없으면 access set --key logs"),
    })


def build_parser() -> JSONArgumentParser:
    # 인자 오류도 JSON(bad_args)으로 — 에이전트는 stdout JSON 만 읽는다 (#708)
    parser = JSONArgumentParser(
        prog="e2e_cli",
        description="agent QA — 앱·웹·서버를 밟아 버그를 찾는다 (실행·캡처는 pro-launch)",
        epilog=("옮긴 명령: " + " · ".join(MOVED)
                + " — pro-launch 의 launch_cli.py 로 넘겨준다 (다음 마이너에서 제거)"),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_d = sub.add_parser("detect", help="무엇을 밟을 수 있는지 (pro-launch detect + note target)")
    p_d.add_argument("--path", default=".", help="탐색 시작 경로 (기본: 현재 디렉터리)")
    p_d.add_argument("--target", default=None,
                     help=f"밟을 대상을 직접 지정 ({'·'.join(TARGETS)}). 생략하면 감지한다")
    p_d.set_defaults(func=cmd_detect)

    p_sc = sub.add_parser("scenario", help="프로젝트별 밟기 시나리오 관리")
    p_sc.add_argument("action", choices=["init", "list", "show"])
    p_sc.add_argument("--target", default=DEFAULT_TARGET,
                      help=f"무엇으로 조작하나 ({'·'.join(TARGETS)}, 기본 {DEFAULT_TARGET})")
    p_sc.add_argument("--name", help="시나리오 파일 이름 (확장자 제외)")
    p_sc.add_argument("--root", default=".", help="프로젝트 루트")
    p_sc.add_argument("--group",
                      help="init: flows/{그룹}/ 아래에 만든다. _shared 면 전제로 둔다")
    p_sc.add_argument("--force", action="store_true", help="init 시 덮어쓰기")
    p_sc.set_defaults(func=cmd_scenario)

    p_n = sub.add_parser("note", help="이 프로젝트에서 알아낸 것을 쌓는다")
    p_n.add_argument("action",
                     choices=["show", "target", "constraint", "screen", "pitfall", "run",
                              "tidy", "forget"])
    p_n.add_argument("--root", default=".")
    p_n.add_argument("--name", help="screen: 화면 이름 / run: 시나리오 이름")
    p_n.add_argument("--anchor", help="screen: 이 화면임을 알아보는 단서(문구 등). 새 화면이면 필수")
    p_n.add_argument("--target", nargs="*", default=None,
                     help=("screen: 누를 대상. '라벨=text:문구' · '라벨=id:x' · '라벨=desc:x' "
                           "(뒤에 '|index=N') · 요소가 없을 때만 '라벨=at:0.5,0.8'. 픽셀은 거절. "
                           "--result 와 함께면 라벨만"))
    p_n.add_argument("--taps", nargs="*", help=argparse.SUPPRESS)   # 옛 픽셀 입력 — 거절하고 --target 을 안내
    p_n.add_argument("--screen-size", help="screen: 잰 화면 해상도. 예 1080x2400 (at 비율 변환 안내에 쓴다)")
    p_n.add_argument("--result", choices=["ok", "fail"], default=None,
                     help=("screen: 그 대상을 눌러 화면이 바뀌었으면 ok, 못 찾았거나 그대로면 fail / "
                           "pitfall·constraint: --index 항목을 다시 겪었으면 ok, 틀렸으면 fail"))
    p_n.add_argument("--index", type=int, default=None,
                     help="pitfall·constraint·forget: 항목 번호 (note show 의 index)")
    p_n.add_argument("--merge-into", dest="merge_into", type=int, default=None,
                     help="pitfall·constraint: 같은 지식으로 판단한 항목 번호 — 문장을 바꾸고 성적은 잇는다")
    p_n.add_argument("--kind", choices=["pitfall", "constraint"], default=None,
                     help="forget: 무엇을 지우나")
    p_n.add_argument("--all", action="store_true", help="show: 요약 대신 전부")
    p_n.add_argument("--apply", action="store_true", help="tidy: 계획대로 실제로 옮긴다 (없으면 계획만)")
    p_n.add_argument("--launch", nargs="*", default=None,
                     help="tidy: launch knowledge 로 옮길 함정과 영역을 직접 지정 ('번호=web' 등)")
    p_n.add_argument("--role", default=None,
                     help="screen: 어느 역할의 기기에서 쟀는지 (device --role 과 같은 키)")
    p_n.add_argument("--build", default=None,
                     help="screen: 그때 깔려 있던 빌드 표식 (device list 의 apk 값)")
    p_n.add_argument("--text",
                     help="constraint: 지켜야 할 것 / pitfall: 함정 / run: 결과 요약")
    p_n.add_argument("--check",
                     help="constraint: 밟으면서 무엇을 보면 위반을 알 수 있는지")
    p_n.add_argument("--targets",
                     help=f"target: 실제로 밟을 수 있는 것 ({'·'.join(TARGETS)}, 쉼표 구분)")
    p_n.add_argument("--why", help="target: 코드를 보고 그렇게 판단한 근거")
    p_n.add_argument(
        "--scope", choices=["project", "flutter", "platform"], default="project",
        help=("pitfall 범위. project=이 앱에서만 / flutter=모든 Flutter 앱 / "
              "platform=기기·OS 차원. project가 아니면 이 컴퓨터 범위(_machine)에 남긴다"))
    p_n.set_defaults(func=cmd_note)

    p_api = sub.add_parser("api", help="서버 시나리오를 밟는다 (target: server)")
    p_api.add_argument("--name", required=True, help="시나리오 이름")
    p_api.add_argument("--root", default=".", help="프로젝트 루트")
    p_api.add_argument("--base-url", dest="base_url", default=None,
                       help="API 주소. 생략하면 시나리오·설정에서 찾는다")
    p_api.add_argument("--timeout", type=int, default=30, help="요청당 제한 시간(초)")
    p_api.set_defaults(func=cmd_api)

    p_ot = sub.add_parser("other", help="앱·웹·서버가 아닌 것을 밟는다 (target: other)")
    p_ot.add_argument("action", choices=["run"])
    p_ot.add_argument("--root", default=".")
    p_ot.add_argument("--command", help="돌릴 명령. --name 과 둘 중 하나")
    p_ot.add_argument("--name", help="시나리오 이름. 끝까지 밟는다")
    p_ot.add_argument("--cwd", help="어디서 돌릴지 (기본: --root)")
    p_ot.add_argument("--watch", nargs="*", default=None,
                      help="실행 전후 파일 변화를 볼 경로. 주지 않으면 보지 않는다")
    p_ot.add_argument("--twice", action="store_true", help="두 번 돌려 같은지 본다")
    p_ot.add_argument("--env", nargs="*", default=None, help="K=V 형태로 여러 개")
    p_ot.add_argument("--timeout", type=int, default=120)
    p_ot.add_argument("--expect-exit", type=int, default=None)
    p_ot.add_argument("--expect-output", default=None)
    p_ot.add_argument("--expect-file", default=None)
    p_ot.add_argument("--expect-absent", default=None)
    p_ot.set_defaults(func=cmd_other)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # 옮긴 명령은 파서에 올리지 않고 그대로 넘긴다 — 인자 계약이 pro-launch 쪽에 산다
    if argv and argv[0] in MOVED:
        return delegate(argv)
    return run_cli(build_parser(), argv)


if __name__ == "__main__":
    sys.exit(main())
