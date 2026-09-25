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

from common.access import find_secrets as _find_secrets  # noqa: E402
from common.access import load_access as _load_access  # noqa: E402
from common.emit import emit  # noqa: E402
from common.http import request as _http_request  # noqa: E402
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
    skip = {"app-map.json", _NOTE_FILE}   # app-map 은 bootstrap 시절 산출물
    out = [f for f in d.rglob("*.json")
           if f.name not in skip and not f.name.startswith("learned.broken-")]
    return sorted(out)


def _resolve_scenario(d: Path, name: str) -> Path | None:
    """이름으로 파일을 찾는다. `flows/auth/x` 처럼 경로를 줘도, `x` 만 줘도 된다."""
    direct = d / f"{name}.json"
    if direct.exists():
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
        # --group 을 주면 flows/{그룹}/ 아래, _shared 면 전제로 둔다
        if args.group == _SHARED_DIR:
            target_dir = d / _SHARED_DIR
        elif args.group:
            target_dir = d / _FLOWS_DIR / args.group
        else:
            target_dir = d
        target_dir.mkdir(parents=True, exist_ok=True)
        f = target_dir / f"{args.name}.json"
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

    return emit({
        "ok": not problems,
        "code": "ok" if not problems else "scenario_invalid",
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

_NOTE_FILE = "learned.json"

def _note_path(root: Path, create: bool = False) -> Path:
    return _scenario_dir(root, create) / _NOTE_FILE


# 이 파일이 담는 구조의 판. 필드를 없애는 변경을 할 때만 올린다.
_NOTE_SCHEMA = 2   # 2: screens 에 variants 축 추가 (#583)


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


def _load_notes(root: Path) -> tuple[dict, str | None]:
    """쌓인 기록을 읽는다. 읽지 못해도 **지우지 않는다.**

    반환: (내용, 경고). 경고가 있으면 호출부가 사용자에게 알려야 한다.

    깨진 파일을 빈 값으로 덮으면 그동안 쌓은 것이 조용히 사라진다. 편집 중 충돌이나
    부분 쓰기로 깨질 수 있으므로, 이때는 원본을 따로 보관하고 새로 시작한다.
    """
    import json
    from datetime import datetime

    empty = {"schema": _NOTE_SCHEMA, "constraints": [], "screens": {},
             "pitfalls": [], "runs": []}
    f = _note_path(root)
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
    return data, None


def _save_notes(f: Path, notes: dict) -> None:
    """원자적으로 쓴다 — 쓰는 도중 멈춰도 기존 파일이 깨지지 않는다."""
    import json
    import os
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(notes, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.replace(tmp, f)      # 같은 파일시스템 안에서는 원자적이다


def cmd_note(args) -> int:
    """밟으면서 알아낸 것을 프로젝트에 남긴다.

    같은 앱을 다음에 밟을 때 좌표를 처음부터 찾거나 같은 함정에 다시 빠지지 않게
    한다. skill은 어느 프로젝트에나 같지만, 이 파일은 프로젝트마다 다르게 자란다.
    """
    import json
    from datetime import date

    root = Path(args.root).resolve()
    notes, warning = _load_notes(root)

    if args.action == "show":
        return emit({
            "file": str(_note_path(root)),
            "schema": notes.get("schema", _NOTE_SCHEMA),
            "constraints": notes.get("constraints", []),
            "screens": {k: _promote_screen(v)
                        for k, v in (notes.get("screens") or {}).items()},
            "pitfalls": notes.get("pitfalls", []),
            "pitfalls_to_promote": [
                x for x in notes.get("pitfalls", [])
                if x.get("scope", "project") != "project"
            ],
            "runs": notes.get("runs", [])[-5:],
            "targets": notes.get("targets"),
            **({"warning": warning} if warning else {}),
            "summary": (f"제약 {len(notes.get('constraints', []))}개 · "
                        f"화면 {len(notes.get('screens', {}))}개 · "
                        f"함정 {len(notes.get('pitfalls', []))}건 · "
                        f"기록된 실행 {len(notes.get('runs', []))}회"),
        })

    if args.action == "screen":
        if not (args.name and args.anchor):
            return emit({"ok": False, "code": "args_required",
                         "error": "--name 과 --anchor 가 필요합니다"})
        entry = _promote_screen(notes.setdefault("screens", {}).setdefault(args.name, {}))
        entry["anchor"] = args.anchor          # 이 화면임을 알아보는 단서
        variant = entry["variants"].setdefault(
            _variant_key(args.role, args.screen_size), {})
        if args.taps:
            # "라벨=x,y" 형태를 그대로 보관한다. 해상도가 바뀌면 다시 재야 하므로
            # 절대 좌표가 아니라 기준 해상도와 함께 남긴다.
            variant["taps"] = dict(t.split("=", 1) for t in args.taps)
        if args.screen_size:
            variant["measured_on"] = args.screen_size
        if args.build:
            # 빌드가 바뀌면 화면도 바뀔 수 있다. 막지 않고 꺼낼 때 알려 준다.
            variant["build"] = args.build
        variant["updated"] = date.today().isoformat()
        entry["updated"] = variant["updated"]

    elif args.action == "pitfall":
        if not args.text:
            return emit({"ok": False, "code": "args_required", "error": "--text 가 필요합니다"})
        secrets = _find_secrets(args.text)
        if secrets:
            return emit({
                "ok": False, "code": "secret_detected",
                "error": f"기록하려는 내용에 {', '.join(secrets)}이(가) 들어 있습니다",
                "hint": ("이 파일은 평문으로 디스크에 남고 다음 실행마다 다시 읽힙니다. "
                         "구체적인 값 대신 '테스트 계정으로'처럼 바꿔 적으세요"),
            })
        entry = {"text": args.text, "scope": args.scope,
                 "added": date.today().isoformat()}
        notes.setdefault("pitfalls", []).append(entry)

        # 이 프로젝트 밖에서도 통하는 것은 여기 두면 다음 프로젝트에서 또 겪는다.
        # 파일에는 남기되(맥락이 사라지지 않게) skill로 올리라고 알린다.
        if args.scope != "project":
            f = _note_path(root, create=True)
            notes["schema"] = notes.get("schema", _NOTE_SCHEMA)
            _save_notes(f, notes)
            return emit({
                "file": str(f),
                **({"warning": warning} if warning else {}),
                "summary": f"기록했습니다 — 다만 scope={args.scope} 입니다",
                "next": ("이 프로젝트 밖에서도 통하는 내용입니다. "
                         "skill의 '자주 묻는 함정' 표에 올려야 다음 프로젝트에서 "
                         "같은 일을 겪지 않습니다"),
            })

    elif args.action == "constraint":
        if not args.text:
            return emit({"ok": False, "code": "args_required",
                         "error": "--text 에 지켜야 할 것을 적으세요"})
        secrets = _find_secrets(args.text)
        if secrets:
            return emit({"ok": False, "code": "secret_detected",
                         "error": f"{', '.join(secrets)}이(가) 들어 있습니다"})
        notes.setdefault("constraints", []).append({
            "text": args.text,
            "check": args.check,      # 밟으면서 무엇을 보면 위반을 알 수 있나
            "added": date.today().isoformat(),
        })

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
        notes["targets"] = {"value": vals, "why": args.why,
                            "added": date.today().isoformat()}

    elif args.action == "run":
        notes.setdefault("runs", []).append({
            "date": date.today().isoformat(),
            "scenario": args.name or "(지정 안 함)",
            "result": args.text or "(기록 없음)",
        })
        notes["runs"] = notes["runs"][-30:]   # 오래된 것은 버린다

    notes["schema"] = notes.get("schema", _NOTE_SCHEMA)
    f = _note_path(root, create=True)
    _save_notes(f, notes)
    return emit({
        "file": str(f),
        **({"warning": warning} if warning else {}),
        "summary": f"{args.action} 기록 완료 — {f.name}",
        "next": None,
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
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
                     choices=["show", "target", "constraint", "screen", "pitfall", "run"])
    p_n.add_argument("--root", default=".")
    p_n.add_argument("--name", help="screen: 화면 이름 / run: 시나리오 이름")
    p_n.add_argument("--anchor", help="screen: 이 화면임을 알아보는 단서(문구 등)")
    p_n.add_argument("--taps", nargs="*", help="screen: '라벨=x,y' 형태로 여러 개")
    p_n.add_argument("--screen-size", help="screen: 좌표를 잰 해상도. 예 1080x2400")
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
              "platform=기기·OS 차원. project가 아니면 skill로 올리라고 안내한다"))
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
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help(sys.stderr)
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
