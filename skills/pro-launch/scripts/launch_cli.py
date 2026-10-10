#!/usr/bin/env python3
"""launch_cli — pro-launch 전용 CLI (projectops 3-layer 표준, Layer 2, #629).

앱·웹·서버를 **띄우고, 조작하고, 찍는** 능력만 담는다. 무엇을 왜 찍을지는 부르는
작업 스킬(pro-agent-test · pro-design-brief · pro-figma-verify)이 정한다.

원칙: **판단은 agent, 스크립트는 실행과 기록.** 프로젝트 구조를 알아맞히지 않는다.

서브커맨드:
    doctor           도구 설치 여부 · 저장 위치
    detect           무엇을 띄울 수 있는지 (마커 파일 · 기기 · 브라우저)
    devices          붙은 기기 · 부팅된 시뮬레이터 · AVD
    device           역할을 기기에 묶는다 (list · bind · unbind · show)
    app              앱 화면을 찍고(shot) 띄운다(launch)
    web              브라우저 조작 (setup · open · goto · click · type · shot · assert ·
                     console · close · viewport · route)
    http             단건 HTTP 요청
    access           붙는 법 기록 (show · set · unset)
    db               SQL 실행 (붙는 법은 access 에 적어 둔 대로)
    logs             서버 로그 (보는 법도 access 에 적어 둔 대로)
    shrink           이슈 첨부용 축소 · WebP
    recall · learn · forget   이 컴퓨터에서 먹힌 조작 방식을 기억한다 (쓸수록 정확해진다)
    get-output-path  이번 실행 자리 + env.sh

출력: MCP-style JSON (ok/code/summary/next 4필드 보장).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.access import (access_path, find_secrets, load_access, load_status,  # noqa: E402
                           needs_verify, record_result, reset_status, save_access)
from common.emit import emit  # noqa: E402
from common.http import request as http_request  # noqa: E402
from common.image import (SHOT_MAX_SIDE, WEBP_QUALITY, has_pillow,  # noqa: E402
                          resize_tool, shrink, to_webp)
from common.proc import run, sdk_tool  # noqa: E402
from common.state import (in_skill_path, launch_file, migrate_launch,  # noqa: E402
                          repo_key, repo_unknown, state_dir, venv_dir, venv_python,
                          venv_site_packages)

# 같은 스킬 안의 보조 모듈 — 스크립트로 불리든 테스트가 import 하든 찾게 한다
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))
import credentials  # noqa: E402
import knowledge  # noqa: E402
import stealth  # noqa: E402
import app_input  # noqa: E402


# =========================================================================
# 저장 자리 + 옛 자리에서 옮기기
# =========================================================================

# 이 프로세스에서 이미 옮겼는지. 한 번만 본다.
_MIGRATION: dict = {}


def _home(root: Path) -> Path:
    """launch 상태 폴더. 처음 부를 때 옛 agent-test 폴더의 launch 몫을 옮긴다."""
    key = str(root)
    if key not in _MIGRATION:
        _MIGRATION[key] = migrate_launch(root)
    return state_dir("launch", root)


def out(payload: dict) -> int:
    """emit 에 이전 결과를 덧붙인다. 옮긴 것이 있으면 사용자가 알아야 한다."""
    moved = [m for r in _MIGRATION.values() for m in r.get("moved", [])]
    warns = [w for r in _MIGRATION.values() for w in r.get("warnings", [])]
    if moved:
        payload["migrated"] = moved
    if warns:
        payload["migration_warnings"] = warns
    # summary 는 언제나 문자열이다 (#825) — None 이 섞이면 부르는 쪽 파싱이 깨진다(실측).
    if not payload.get("summary"):
        act = payload.get("action")
        payload["summary"] = payload.get("error") or (f"{act} 완료" if act else "완료")
    _root_warning(payload)
    _grade_access(payload)
    _memory_hooks(payload)
    return emit(payload)


# ── 레포를 알 수 없을 때 (#836) ──────────────────────────────────────────
#
# 스킬·플러그인 캐시 폴더에서 불렸고 git 원격도 없으면 어느 프로젝트인지 모른다. 이때 상태는
# 이 컴퓨터 공용 자리(_machine)에 쓰고(state.state_dir 이 정한다), 응답으로 --root 를 요구한다.

_ROOT_CTX: dict = {}


def _root_warning(payload: dict) -> None:
    if not _ROOT_CTX.get("unknown"):
        return
    payload["root_unknown"] = True
    payload["root_warning"] = (f"프로젝트를 알 수 없는 폴더({_ROOT_CTX.get('path')})에서 불렸다 — "
                               "상태는 이 컴퓨터 공용 자리에 쓰고, 레포 기억은 쓰지 않는다")
    fix = "--root <프로젝트 경로> 를 붙여 다시 부른다 (또는 PROJECT_ROOT 환경변수)"
    nxt = payload.get("next")
    if not nxt:
        payload["next"] = fix
    elif isinstance(nxt, str) and fix not in nxt:
        payload["next"] = f"{fix}. 그 다음: {nxt}"


# ── 적어 둔 접속 방법의 성적 (#836) ──────────────────────────────────────
#
# logs·db·http 가 access 기록으로 실행되면 결과를 도구가 직접 남긴다(기억 원칙 2).
# 미설치·환경변수 누락처럼 환경 탓인 실패는 방법의 실패가 아니므로 세지 않는다.

_ACCESS_CTX: dict = {}
_ACCESS_FAIL_CODES = {"db_query_failed", "db_timeout", "logs_failed", "logs_timeout",
                      "request_failed"}
# http 는 응답만 받으면 붙는 법은 맞다 — 기대 상태코드가 다른 것은 시나리오 판정이다
_ACCESS_OK_CODES = {"ok", "unexpected_status"}


def _use_access(root: Path, key: str) -> None:
    """이번 명령이 access 의 key 로 적힌 방법을 쓴다고 표시한다. out() 이 결과를 기록한다."""
    _ACCESS_CTX.update(root=root, key=key)


def _grade_access(payload: dict) -> None:
    key = _ACCESS_CTX.pop("key", None)
    root = _ACCESS_CTX.pop("root", None)
    if not key or root is None:
        return
    code = payload.get("code")
    ok = payload.get("ok", True) is not False and code in (None, *_ACCESS_OK_CODES)
    if not ok and code not in _ACCESS_FAIL_CODES:
        return
    try:
        prev = record_result(root, key, ok, code)
    except Exception:   # noqa: BLE001 — 성적은 보조다
        return
    if needs_verify(prev):
        lf = prev.get("last_fail") or {}
        payload["verify"] = True
        payload["verify_note"] = (f"access '{key}' 는 지난번({lf.get('date')}, {lf.get('code')}) 실패했던 방법이다 — "
                                  + ("이번에는 먹혔다" if ok else
                                     "이번에도 실패했다. 코드를 다시 읽어 access set 으로 고친다"))


# ── 기억을 응답에 싣는다 (#833) ──────────────────────────────────────────
#
# 읽기를 agent 의 recall 호출에 맡겼더니 한 번도 다시 읽히지 않았다(실측: 14건 전부 ok=1).
# 그래서 영역(ios·android·web·server) 명령의 응답에 기억을 직접 싣는다 — 하네스와 무관하게 보인다.
# 명령이 영역을 정하면 _MEMORY_CTX 에 적고, out() 이 마지막에 읽는다.

_MEMORY_CTX: dict = {}
_FIX_WINDOW_SEC = 30 * 60   # 실패 뒤 이 안에 같은 영역이 성공하면 '새로 알게 된 방식'일 수 있다


def _set_area(area: str | None, root: Path | None = None, key_prefix: str | None = None) -> None:
    """key_prefix: 이 접두사의 기억만 싣는다 (예: 서버 이름별 `server.<이름>.`)."""
    if area in knowledge.AREAS:
        _MEMORY_CTX.update(area=area, root=root or _MEMORY_CTX.get("root") or Path(".").resolve(),
                           key_prefix=key_prefix)


def _memory_hooks(payload: dict) -> None:
    """기억 싣기 · 실패 뒤 성공이면 learn_hint. 어떤 오류도 명령 결과를 망치지 않는다."""
    area = _MEMORY_CTX.get("area")
    # HOME 이 상대 경로면 작업 폴더 아래에 기록이 생긴다 — 쓰지 않는다 (테스트가 실제로 그렇게 만들었다)
    if not area or not knowledge.base_dir().is_absolute():
        return
    try:
        root = _MEMORY_CTX["root"]
        unknown = _repo_unknown(root)
        paths = {"machine": knowledge.store_path("machine", root)}
        if not unknown:
            paths["repo"] = knowledge.store_path("repo", root)
        seen_dir = knowledge.store_path("machine" if unknown else "repo", root).parent
        mem = knowledge.surface(paths, area, seen_dir / "memory_seen.json",
                                key_prefix=_MEMORY_CTX.get("key_prefix"))
        if mem:
            payload["memory"] = mem
            payload["memory_note"] = ("이 컴퓨터에서 먹혔던 방식이다. 쓴 것이 있으면 결과를 "
                                      f"learn --area {area} --key <key> --how <how> --result ok|fail 로 남긴다")
        hint = _track_attempt(seen_dir / "attempts.json", area, payload)
        if hint:
            payload["learn_hint"] = hint
    except Exception:   # noqa: BLE001 — 기억은 보조다. 실패해도 본 명령 결과는 그대로 낸다
        pass


def _track_attempt(f: Path, area: str, payload: dict) -> str | None:
    """같은 영역에서 실패한 뒤 성공하면 '새로 알게 된 방식이면 기록하라'고 알려 준다.

    agent 가 기억을 남길 가장 좋은 순간은 막혔다 풀린 직후다. 그 순간을 도구가 짚어 준다.
    """
    ok = payload.get("ok", True) is not False and payload.get("code") in (None, "ok")
    try:
        last = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        last = {}
    now = time.time()
    prev = last.get(area) or {}
    if ok:
        last.pop(area, None)
    else:
        last[area] = {"code": payload.get("code"), "at": now}
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(last), encoding="utf-8")
    except OSError:
        pass
    if ok and prev and now - prev.get("at", 0) < _FIX_WINDOW_SEC:
        return (f"방금 '{prev.get('code')}' 실패를 다른 방식으로 넘겼다. 다음에도 쓸 방식이면 "
                f"learn --area {area} --key <짧은키> --how '<무엇을 어떻게>' --result ok 로 남긴다 "
                "(미설치·일회성·비밀값은 남기지 않는다)")
    return None


def _root(args) -> Path:
    """작업 대상 프로젝트 루트.

    agent 가 스크립트 폴더로 `cd` 한 뒤 `--root .` 으로 부르면 그 폴더가 프로젝트로 잡힌다.
    플러그인 캐시는 git 레포가 아니라 폴더 이름 `scripts` 가 레포 키가 되어, 기억과 상태가
    엉뚱한 곳(~/.projectops/launch/scripts/)에 쌓였다(#833 실측). 그때는 $PROJECT_ROOT 를 쓴다.
    """
    r = Path(getattr(args, "root", ".") or ".").resolve()
    if _repo_unknown(r):
        if os.environ.get("PROJECT_ROOT"):
            return Path(os.environ["PROJECT_ROOT"]).resolve()
        # 상태는 state_dir 이 _machine 으로 돌린다. 응답에서 --root 를 요구하도록 표시만 한다
        _ROOT_CTX.update(unknown=True, path=str(r))
    return r


def _is_skill_dir(r: Path) -> bool:
    """r 이 스킬·플러그인 폴더(이 스킬 자신 포함) 안인가 — 사용자 프로젝트가 아닐 수 있다."""
    return r in (_HERE.parent, _HERE.parent.parent) or in_skill_path(r)


# =========================================================================
# 무엇을 띄울 수 있나 — 마커 파일만 본다. 구조를 알아맞히지 않는다
# =========================================================================

KINDS = ("app", "web", "server")

# projectops 프로젝트 타입 → 띄울 수 있는 것. 한 타입이 여럿을 줄 수 있다.
_TYPE_TO_KIND = {
    "flutter": ["app"],
    "react-native": ["app"],
    "react-native-expo": ["app"],
    "react": ["web"],
    "next": ["web"],
    "node": ["web", "server"],
    "spring": ["server"],
    "python": ["server"],
    "basic": [],
}


def _version_yml_types(root: Path) -> list[str]:
    """version.yml의 project_types. yaml 파서를 쓰지 않는다 — 표준 라이브러리만으로 돈다."""
    f = root / "version.yml"
    if not f.is_file():
        return []
    try:
        body = f.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    m = re.search(r"project_types:\s*\n((?:\s*-\s*\S+\n?)+)", body)
    if m:
        return re.findall(r"-\s*([A-Za-z0-9_-]+)", m.group(1))
    m = re.search(r"project_types:\s*\[([^\]]*)\]", body)
    if m:
        return [x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()]
    return []


def _marker_kinds(root: Path) -> dict:
    """파일로 추론한다. version.yml이 없는 레포(대부분의 남의 프로젝트)를 위한 길이다."""
    found: dict[str, list[str]] = {}

    def add(kind: str, why: str):
        found.setdefault(kind, []).append(why)

    for pub in list(root.rglob("pubspec.yaml"))[:20]:
        if "build" in pub.parts or ".dart_tool" in pub.parts:
            continue
        add("app", str(pub.relative_to(root)))
        break

    for pkg in list(root.rglob("package.json"))[:20]:
        if "node_modules" in pkg.parts:
            continue
        try:
            body = pkg.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(pkg.relative_to(root))
        if re.search(r'"(react|next|vue|svelte|@angular/core)"\s*:', body):
            add("web", rel)
        if re.search(r'"react-native"\s*:', body):
            add("app", rel)
        if re.search(r'"(express|fastify|@nestjs/core|koa)"\s*:', body):
            add("server", rel)

    for marker, why in (("build.gradle", "spring"), ("build.gradle.kts", "spring"),
                        ("pom.xml", "maven"), ("pyproject.toml", "python"),
                        ("requirements.txt", "python"), ("manage.py", "django")):
        for f in list(root.rglob(marker))[:10]:
            if "build" in f.parts or "node_modules" in f.parts or ".venv" in f.parts:
                continue
            # Flutter 앱의 android/build.gradle을 서버로 오해하면 안 된다
            if marker.startswith("build.gradle") and "android" in f.parts:
                continue
            add("server", f"{f.relative_to(root)} ({why})")
            break
    return found


def detect_kinds(root: Path) -> dict:
    """version.yml 선언 → 마커 파일 순. 선언은 '무엇인가'일 뿐이라 agent 가 확인한다."""
    types = _version_yml_types(root)
    if types:
        kinds: list[str] = []
        for ty in types:
            for k in _TYPE_TO_KIND.get(ty, []):
                if k not in kinds:
                    kinds.append(k)
        if kinds:
            return {"kinds": kinds, "source": "version.yml", "project_types": types}
    found = _marker_kinds(root)
    kinds = [k for k in KINDS if k in found]
    return {"kinds": kinds, "source": "marker" if kinds else "none", "evidence": found}


def _find_flutter_root(start: Path) -> Path | None:
    """pubspec.yaml에 flutter 의존성이 있는 디렉터리. 모노레포면 client/ 같은 하위에 있다."""
    for p in sorted(start.rglob("pubspec.yaml")):
        if "build" in p.parts or ".dart_tool" in p.parts:
            continue
        if len(p.relative_to(start).parts) > 4:
            continue
        try:
            if "flutter:" in p.read_text(encoding="utf-8", errors="ignore"):
                return p.parent
        except OSError:
            continue
    return None


def _android_package(root: Path) -> str | None:
    for name in ("build.gradle.kts", "build.gradle"):
        f = root / "android" / "app" / name
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'applicationId\s*=?\s*["\']([\w.]+)["\']', text)
        if m:
            return m.group(1)
    return None


def _ios_bundle_id(root: Path) -> str | None:
    f = root / "ios" / "Runner.xcodeproj" / "project.pbxproj"
    if not f.exists():
        return None
    text = f.read_text(encoding="utf-8", errors="ignore")
    # 변수 참조($(...))가 아닌 실제 값만 고른다
    for m in re.finditer(r'PRODUCT_BUNDLE_IDENTIFIER\s*=\s*([^;]+);', text):
        v = m.group(1).strip().strip('"')
        if "$" not in v and "RunnerTests" not in v:
            return v
    return None


def _app_base_urls(root: Path) -> list[str]:
    """**Flutter 앱 전용.** .env와 dart 설정에서 앱이 바라보는 주소를 모은다."""
    found: list[str] = []
    candidates = [root / ".env"]
    candidates += list((root / "lib" / "core").rglob("*config*.dart"))
    for f in candidates[:12]:
        if not f.exists() or not f.is_file():
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r'https?://[\w.\-]+(?::\d+)?[\w./\-]*', text):
            url = m.group(0).rstrip('/')
            if url not in found:
                found.append(url)
    return found[:8]


def _web_base_urls(root: Path) -> list[str]:
    """웹이 뜨는 주소 후보. 없으면 사용자에게 묻는 수밖에 없다."""
    urls: list[str] = []
    for f in list(root.rglob("package.json"))[:20]:
        if "node_modules" in f.parts:
            continue
        try:
            body = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in re.finditer(r"-p\s*(\d{4,5})|--port[= ](\d{4,5})", body):
            u = f"http://localhost:{m.group(1) or m.group(2)}"
            if u not in urls:
                urls.append(u)
    for env in (".env", ".env.local", ".env.development"):
        f = root / env
        if f.is_file():
            try:
                for m in re.finditer(r"^[A-Z_]*URL[A-Z_]*=(https?://\S+)",
                                     f.read_text(encoding="utf-8", errors="ignore"), re.M):
                    if m.group(1) not in urls:
                        urls.append(m.group(1))
            except OSError:
                pass
    # 흔한 기본값을 마지막에 둔다 — 못 찾았을 때의 출발점
    for u in ("http://localhost:3000", "http://localhost:5173"):
        if u not in urls:
            urls.append(u)
    return urls[:6]


# =========================================================================
# 기기
# =========================================================================

def _devices() -> dict:
    android: list[str] = []
    adb = sdk_tool("adb")
    if adb:
        for line in run([adb, "devices"]).splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                android.append(parts[0])
    ios: list[str] = []
    if shutil.which("xcrun"):
        for line in run(["xcrun", "simctl", "list", "devices", "booted"]).splitlines():
            m = re.match(r"\s+(.+?)\s+\(([\w-]{36})\)\s+\(Booted\)", line)
            if m:
                ios.append(f"{m.group(1)} [{m.group(2)}]")
    avds: list[str] = []
    emu = sdk_tool("emulator")
    if emu:
        avds = [l.strip() for l in run([emu, "-list-avds"]).splitlines()
                if l.strip() and not l.startswith("INFO")]
    return {"android": android, "ios_booted": ios, "android_avds": avds,
            "adb_path": adb, "emulator_path": emu}


def _ios_udids(dev: dict) -> list[str]:
    return [re.search(r"\[([\w-]{36})\]$", s).group(1)
            for s in dev.get("ios_booted", []) if re.search(r"\[([\w-]{36})\]$", s)]


def _sole_device() -> str | None:
    """붙어 있는 안드로이드 기기가 정확히 하나면 그 시리얼. 아니면 None."""
    try:
        found = _devices()["android"]
    except Exception:
        return None
    return found[0] if len(found) == 1 else None


_TOOLS = [
    ("adb", False, "Android 기기 제어",
     "Android Studio → SDK Manager → SDK Tools → Android SDK Platform-Tools"),
    ("emulator", False, "AVD 부팅 (이미 켜져 있으면 불필요)",
     "Android Studio → SDK Manager → SDK Tools → Android Emulator"),
    ("xcrun", False, "iOS 시뮬레이터 (macOS 전용)",
     "Xcode 설치 후 xcode-select --install"),
    ("cwebp", False, "캡처를 WebP 로 줄이기 (Pillow 가 없을 때)",
     "brew install webp / apt install webp"),
    ("ffmpeg", False, "녹화에서 프레임 추출 · 축소 폴백",
     "brew install ffmpeg / apt install ffmpeg / winget install ffmpeg"),
]


def cmd_doctor(args) -> int:
    """무엇이 되고 무엇이 안 되는지. 능력 스킬이라 필수 도구는 없다 — 쓰려는 것만 있으면 된다."""
    checks = []
    for name, required, why, how in _TOOLS:
        path = sdk_tool(name) if name in ("adb", "emulator") else shutil.which(name)
        checks.append({"tool": name, "found": bool(path), "path": path, "why": why,
                       **({} if path else {"install": how})})
    root = _root(args)
    home = _home(root)
    shrink_by = resize_tool()
    pw = _playwright_state()
    open_browser = _open_browser_status(_web_state_path(root))
    return out({
        "checks": checks,
        "browser": pw,
        "open_browser": open_browser,
        "image_resize": shrink_by or "없음 — 캡처가 원본 크기로 남아 토큰·전송량이 커진다",
        "image_hint": None if shrink_by else
            "web setup 을 돌리면 전용 venv 에 Pillow 가 함께 깔립니다 (시스템은 건드리지 않습니다)",
        "pillow": has_pillow(),
        "state_dir": str(home),
        "venv": str(venv_dir()),
        "platform": sys.platform,
        "summary": (f"{sys.platform}: "
                    + (", ".join(c["tool"] for c in checks if c["found"]) or "도구 없음"))
                   + f" · 브라우저 {'준비' if pw['ready'] else '없음'}"
                   + f" · 이미지 축소 {shrink_by or '불가'}",
    })


# 마지막으로 쓴 뒤 이만큼 지나면 "방치됐다"고 본다 — 다른 세션이 쓰는 중인지 가를 근거 (#825)
_STALE_BROWSER_HOURS = 6


def _open_browser_status(state_f: Path) -> dict | None:
    """이 레포에 떠 있는 브라우저가 있나, 언제 마지막으로 썼나. 없으면 None."""
    st = _read_web_state(state_f) if state_f.is_file() else {}
    pid = st.get("pid")
    if not pid:
        return None
    alive = _pid_alive(int(pid))
    used = st.get("last_used") or st.get("opened_at")
    idle_h = None
    try:
        idle_h = round((time.time() - time.mktime(time.strptime(used, "%Y-%m-%d %H:%M:%S"))) / 3600, 1)
    except (TypeError, ValueError):
        pass
    stale = alive and idle_h is not None and idle_h >= _STALE_BROWSER_HOURS
    return {"pid": pid, "alive": alive, "opened_at": st.get("opened_at"), "last_used": used,
            "idle_hours": idle_h, "readonly": bool(st.get("readonly")), "stale": stale,
            "hint": (f"{idle_h}시간째 안 쓴 브라우저다 — 다른 세션이 쓰는 중이 아니면 web close 로 정리하거나 web open 으로 다시 붙는다"
                     if stale else None)}


def cmd_detect(args) -> int:
    """무엇을 띄울 수 있는지. 마커 파일·기기·브라우저 준비 상태만 본다."""
    start = Path(args.path).resolve()
    git_root = run(["git", "-C", str(start), "rev-parse", "--show-toplevel"]).strip()
    root = Path(git_root) if git_root else start

    det = detect_kinds(root)
    # 부르는 쪽이 이미 안다면(확인해 적어 둔 타겟 등) 그 종류의 정보를 모은다 — 감지를 덮는다
    if getattr(args, "kinds", None):
        want = [k.strip() for k in args.kinds.split(",") if k.strip()]
        bad = [k for k in want if k not in KINDS]
        if bad:
            return out({"ok": False, "code": "unknown_kind",
                        "error": f"모르는 종류: {', '.join(bad)}", "hint": " · ".join(KINDS)})
        det = {**det, "kinds": want, "source": "given"}
    kinds = det["kinds"]
    payload: dict = {"root": str(root), "kinds": kinds, "source": det["source"],
                     "state_dir": str(_home(root))}
    for k in ("project_types", "evidence"):
        if det.get(k):
            payload[k] = det[k]

    if "app" in kinds:
        app_root = _find_flutter_root(root)
        payload["app"] = {
            "flutter_root": str(app_root) if app_root else None,
            "android_package": _android_package(app_root) if app_root else None,
            "ios_bundle_id": _ios_bundle_id(app_root) if app_root else None,
            "base_urls": _app_base_urls(app_root) if app_root else [],
            "devices": _devices(),
        }
    if "web" in kinds:
        payload["web"] = {"base_urls": _web_base_urls(root), "playwright": _playwright_state()}
    if "server" in kinds:
        # 설정이 어디 있고 어떻게 붙는지는 **여기서 맞히지 않는다** (#589).
        saved = load_access(root)
        bu = saved.get("base_url")
        payload["server"] = {
            "base_url": bu.get("url") if isinstance(bu, dict) else bu,
            "access_recorded": sorted(saved) or None,
        }

    if det["source"] == "version.yml":
        payload["confirm"] = ("이 kinds 는 version.yml 선언에서 나왔습니다 — 서버가 화면을 직접 "
                              "뿌리면 web 도 띄울 수 있습니다. 코드를 보고 판단하세요")

    nxt = None
    if not kinds:
        nxt = "무엇을 띄울지 알 수 없습니다 — 코드를 보고 app·web·server 중 무엇인지 판단하세요"
    elif "app" in kinds and not (payload["app"]["devices"]["android"]
                                 or payload["app"]["devices"]["ios_booted"]):
        nxt = "devices  # 기기가 없습니다. AVD 나 시뮬레이터를 부팅하세요"
    elif "web" in kinds and not payload["web"]["playwright"]["ready"]:
        nxt = "web setup  # 브라우저(약 100MB)를 받습니다. 먼저 사용자에게 물어보세요"
    payload["summary"] = f"{root.name}: {'·'.join(kinds) if kinds else '없음'} ({det['source']})"
    payload["next"] = nxt
    return out(payload)


def cmd_devices(args) -> int:
    dev = _devices()
    n = len(dev["android"]) + len(dev["ios_booted"])
    return out({**dev, "summary": f"사용 가능한 기기 {n}대",
                "next": None if n else "emulator -avd {AVD명} 으로 부팅하세요"})


# ── 역할 ↔ 기기 (#583) ─────────────────────────────────────────────────
#
# 여기서는 **묶고 대조만** 한다. adb 를 감싸지 않는다 — 표면이 너무 넓어 감싸면 adb
# 재구현이 되고, 탈출구를 만들면 거기로 `-s` 없는 명령이 다시 샌다.

_DEVICES_FILE = "devices.json"
_DEVICES_SCHEMA = 1


def _devices_path(root: Path) -> Path:
    _home(root)
    return launch_file(root, _DEVICES_FILE)


def _load_devices(root: Path) -> dict:
    """{package, bindings:[{role, serial, note?}]} — **목록 순서가 곧 DEV1·DEV2 번호다.**"""
    p = _devices_path(root)
    empty = {"package": None, "bindings": []}
    if not p.is_file():
        return empty
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty
    if not isinstance(data, dict):
        return empty
    rows = [r for r in (data.get("bindings") or [])
            if isinstance(r, dict) and r.get("role") and r.get("serial")]
    return {"package": data.get("package"), "bindings": rows}


def _save_devices(root: Path, package: str | None, bindings: list[dict]) -> Path:
    p = _devices_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"schema": _DEVICES_SCHEMA, "package": package,
                             "bindings": bindings},
                            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def _adb_shell(serial: str, *args: str, timeout: int = 20) -> str:
    adb = sdk_tool("adb")
    if not adb:
        return ""
    return run([adb, "-s", serial, "shell", *args], timeout=timeout).replace("\r", "")


def _build_info(serial: str, package: str | None) -> dict:
    """그 기기에 무엇이 깔려 있는지. **버전으로 재면 안 된다** — 컴파일타임 플래그만 바꾼
    재빌드는 버전이 같다 (#603). APK 해시로 재야 한쪽만 재설치된 것을 본다."""
    info: dict = {"screen": None, "package": package, "version": None,
                  "apk": None, "apk_by": None}
    m = re.search(r"Physical size:\s*(\d+x\d+)", _adb_shell(serial, "wm", "size"))
    if m:
        info["screen"] = m.group(1)
    if not package:
        return info
    dump = _adb_shell(serial, "dumpsys", "package", package, timeout=30)
    if "Unable to find package" in dump or not dump.strip():
        info["installed"] = False
        return info
    info["installed"] = True
    vn = re.search(r"versionName=(\S+)", dump)
    vc = re.search(r"versionCode=(\d+)", dump)
    if vn or vc:
        info["version"] = "%s+%s" % (vn.group(1) if vn else "?", vc.group(1) if vc else "?")
    apk = None
    for line in _adb_shell(serial, "pm", "path", package).splitlines():
        if line.startswith("package:"):
            apk = line.split(":", 1)[1].strip()
            break
    if apk:
        for tool in ("sha1sum", "md5sum"):
            head = _adb_shell(serial, tool, apk, timeout=60).split()
            if head and re.fullmatch(r"[0-9a-f]{32,40}", head[0]):
                info["apk"], info["apk_by"] = head[0], tool
                break
    if not info["apk"]:
        m2 = re.search(r"lastUpdateTime=(\S+\s+\S+)", dump)
        if m2:
            info["apk"], info["apk_by"] = m2.group(1), "lastUpdateTime"
    return info


def _build_mismatch(rows: list[dict]) -> list[dict]:
    """역할끼리 설치된 빌드가 다른지. 같은 버전인데 해시가 다르면 한쪽만 재설치된 것이다."""
    seen = [(r["role"], (r.get("build") or {}).get("apk"),
             (r.get("build") or {}).get("version")) for r in rows if r.get("role")]
    known = [(role, apk, ver) for role, apk, ver in seen if apk]
    if len(known) < 2 or len({apk for _, apk, _ in known}) == 1:
        return []
    vers = {ver for _, _, ver in known}
    detail = ("버전은 같은데 APK 가 다릅니다 — 한쪽만 다시 설치됐을 수 있습니다"
              if len(vers) == 1 else "설치된 버전 자체가 다릅니다")
    return [{"roles": [role for role, _, _ in known], "field": "apk", "detail": detail}]


def _resolve_run_dir(args) -> Path | None:
    """env.sh 를 어디에 쓸지. **추측하지 않는다** — 최근 폴더를 골라 주면 틀렸을 때 조용하다."""
    v = getattr(args, "run_dir", None) or os.environ.get("RUN_DIR")
    return Path(v).resolve() if v else None


def cmd_device(args) -> int:
    """역할을 기기에 묶고, 무엇이 깔려 있는지 대조한다."""
    root = _root(args)
    known = _load_devices(root)
    bindings = known["bindings"]
    package = args.package or known["package"]

    if args.action in ("bind", "unbind"):
        if not args.role:
            return out({"ok": False, "code": "args_required", "error": "--role 이 필요합니다",
                        "hint": "시나리오 roles 의 키와 같은 값을 쓰세요"})
        bindings = [b for b in bindings if b["role"] != args.role]
        if args.action == "bind":
            if not args.serial:
                return out({"ok": False, "code": "args_required",
                            "error": "--serial 이 필요합니다",
                            "hint": "device list 로 붙어 있는 기기를 먼저 보세요"})
            entry = {"role": args.role, "serial": args.serial}
            if args.note:
                entry["note"] = args.note
            bindings.append(entry)
        _save_devices(root, package, bindings)
        run_dir = _resolve_run_dir(args)
        env = _write_env_sh(run_dir, package, bindings) if (run_dir and run_dir.is_dir()) else None
        return out({
            "bindings": bindings, "file": str(_devices_path(root)),
            "env_file": str(env) if env else None,
            "summary": f"역할 {len(bindings)}개" + ("" if env else " (env.sh 는 아직 안 씀)"),
            "next": (None if env else
                     "get-output-path 로 실행 자리를 먼저 만들고 $RUN_DIR 을 세운 뒤 "
                     "다시 부르면 env.sh 에 반영됩니다"),
        })

    if args.action == "show":
        return out({"bindings": bindings, "package": package,
                    "file": str(_devices_path(root)), "summary": f"역할 {len(bindings)}개"})

    # list — 붙어 있는 기기 + 역할 + 설치된 빌드
    dev = _devices()
    by_role = {b["serial"]: b for b in bindings}
    rows = []
    for serial in dev["android"]:
        b = by_role.get(serial, {})
        rows.append({"serial": serial, "role": b.get("role"), "note": b.get("note"),
                     "build": _build_info(serial, package)})
    unbound = [r["serial"] for r in rows if not r["role"]]
    mismatch = _build_mismatch(rows)
    ios_ids = _ios_udids(dev)
    stale = [b["serial"] for b in bindings
             if b["serial"] not in dev["android"] and b["serial"] not in ios_ids]
    nxt = None
    if mismatch:
        nxt = "양쪽에 같은 빌드를 설치한 뒤 다시 확인하세요 — 한쪽만 재설치되면 밟는 화면이 달라집니다"
    elif stale:
        nxt = f"묶어 둔 기기가 붙어 있지 않습니다: {', '.join(stale)}"
    elif len(rows) > 1 and unbound:
        nxt = ("device bind --role {키} --serial {시리얼} 로 역할을 잡으세요 — "
               "안 잡으면 adb 가 어느 기기로 갈지 정해지지 않습니다")
    # 기기는 get-output-path 뒤에 부팅되기도 한다. 환경을 새로 고쳐 두지 않으면 DEV 가 빈다.
    run_dir = _resolve_run_dir(args)
    env = _write_env_sh(run_dir, package, bindings) if (run_dir and run_dir.is_dir()) else None
    return out({
        "devices": rows, "env_file": str(env) if env else None,
        "ios_booted": dev["ios_booted"], "package": package,
        "build_mismatch": mismatch, "stale_bindings": stale,
        "summary": (f"기기 {len(rows)}대 · 역할 {len(bindings)}개"
                    + (f" · 빌드 불일치 {len(mismatch)}건" if mismatch else "")),
        "next": nxt, "ok": not mismatch,
        "code": "build_mismatch" if mismatch else "ok",
    })


# =========================================================================
# 산출물 자리 + env.sh — 경로는 여기서 정해 준다. 에이전트가 지어내지 않는다 (#611)
# =========================================================================

def _sh_quote(value: str) -> str:
    """셸에서 값이 그대로 쓰이도록 감싼다. 큰따옴표면 `$` 가 전개되어 **다른 값**이 된다."""
    return "'" + value.replace("'", "'\\''") + "'"


def _run_var(skill: str) -> str:
    """실행 이름을 담는 변수. launch → LAUNCH_RUN, agent-test → AGENT_TEST_RUN.

    공통 변수(RUN_DIR·SHOT_DIR·DEV·PKG)는 어느 스킬이 만들어도 같은 이름이다 —
    문서 예시 수십 곳이 그 이름에 기대고 있다.
    """
    return re.sub(r"[^A-Z0-9]+", "_", skill.upper()).strip("_") + "_RUN"


def _write_env_sh(run_dir: Path, package: str | None,
                  bindings: list[dict] | None = None, skill: str | None = None) -> Path:
    """실행 환경을 쓴다. **이 파일을 쓰는 곳은 여기 하나뿐이다.**

    역할 이름을 **셸 변수명에 쓰지 않는다.** 한글·공백·하이픈이 든 이름은
    `export DEV_{이름}=...` 이 거부되고 `$DEV_{이름}` 은 조용히 엉뚱한 값이 된다.
    번호로 고정하고 이름은 값으로 담는다.
    """
    shots = run_dir / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    env = run_dir / "env.sh"
    # 스킬 이름을 모르면(device 가 나중에 다시 쓸 때) 처음 쓴 이름을 이어받는다
    if skill is None and env.is_file():
        m = re.search(r"^export ([A-Z0-9_]+_RUN)=", env.read_text(encoding="utf-8"), re.M)
        var = m.group(1) if m else _run_var("launch")
    else:
        var = _run_var(skill or "launch")

    lines = [
        "# 실행 환경 — `source env.sh` 로 불러 쓴다.",
        "# 경로를 손으로 짓지 않는다. 여기 없는 자리에는 아무것도 만들지 않는다.",
        "export %s=%s" % (var, _sh_quote(run_dir.name)),
        "export RUN_DIR=%s" % _sh_quote(str(run_dir)),
        "export SHOT_DIR=%s" % _sh_quote(str(shots)),
    ]
    if package:
        lines.append("export PKG=%s" % _sh_quote(package))

    bindings = bindings or []
    if bindings:
        lines += ["",
                  "# 역할 ↔ 기기. ROLE{n} 값은 시나리오 roles 의 키와 같은 문자열이다.",
                  "# 시나리오가 \"device\": \"B\" 라고 적으면 ROLE2==B 를 보고 $DEV2 를 쓴다.",
                  "export DEV_COUNT=%d" % len(bindings)]
        for n, b in enumerate(bindings, 1):
            note = b.get("note")
            tail = "   # %s" % note if note else ""
            lines.append("export ROLE%d=%s; export DEV%d=%s%s"
                         % (n, _sh_quote(b["role"]), n, _sh_quote(b["serial"]), tail))
        lines += ["", "# 역할을 쓰지 않는 명령의 기본 기기", 'export DEV="$DEV1"']
    else:
        # DEV 는 **반드시 정의한다.** 비어 있으면 `adb -s ` 가 되어 사용법 오류로 죽는다.
        one = _sole_device()
        lines += ["", "# 붙어 있는 기기가 한 대뿐이라 그것을 기본으로 둔다"
                      if one else
                      "# 기기를 고르지 않았다. device bind 로 역할을 잡으세요 —"
                      "\n# 비워 두면 adb 가 어느 기기로 갈지 정해지지 않는다",
                  "export DEV=%s" % _sh_quote(one or "")]
    lines.append("")
    env.write_text("\n".join(lines), encoding="utf-8")
    return env


def cmd_output_path(args) -> int:
    """이번 실행의 산출물 자리를 만들고 알려준다.

    부르는 작업 스킬이 자기 폴더에 받고 싶으면 --skill 로 자기 id 를 넘긴다
    (design-brief 는 --skill design-brief). **증거를 내는 스킬만 받는다** — 문서 스킬 폴더에
    캡처를 쌓으면 추적 제외가 없어 저장소에 커밋된다.
    """
    try:
        from common.paths import EVIDENCE_SKILLS, resolve_output_path
    except ImportError:
        return out({"ok": False, "code": "common_not_found",
                    "error": "scripts/common/paths.py 를 찾지 못했습니다",
                    "hint": "projectops 설치가 온전한지 확인하세요"})
    # --root 가 가리키는 저장소 기준으로 자리를 계산한다. 없는 경로는 조용히 무시하지 않는다 (#713)
    if args.root and args.root != ".":
        root_dir = Path(args.root).expanduser()
        if not root_dir.is_dir():
            return out({"ok": False, "code": "not_found",
                        "error": f"--root 경로가 없습니다: {root_dir}"})
        os.chdir(root_dir)
    skill = args.skill or "launch"
    if skill not in EVIDENCE_SKILLS:
        return out({"ok": False, "code": "not_evidence_skill",
                    "error": f"'{skill}' 은 증거 스킬로 등록돼 있지 않습니다",
                    "hint": ("scripts/common/paths.py 의 EVIDENCE_SKILLS 에 넣어야 폴더에 "
                             "추적 제외가 심깁니다. 등록된 것: " + ", ".join(sorted(EVIDENCE_SKILLS)))})

    r = resolve_output_path(skill, args.title)
    if r.get("ok") is False:
        return out(r)
    md = Path(r["path"])        # <우산>/<skill>/{날짜}_{번호}_{제목}.md
    run_dir = md.parent / md.stem
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return out({"ok": False, "code": "mkdir_failed", "error": str(e)})

    root = _root(args)
    known = _load_devices(root)
    package = args.package or known["package"]
    if package and package != known["package"]:
        _save_devices(root, package, known["bindings"])
    env = _write_env_sh(run_dir, package, known["bindings"], skill=skill)
    state = r.get("gitignore")
    return out({
        "skill": skill, "run": md.stem, "run_dir": str(run_dir),
        "screenshots": str(run_dir / "screenshots"), "env_file": str(env),
        "output_root": r.get("output_root"), "gitignore": state,
        "mismatch": r.get("mismatch"),
        "summary": f"산출물 자리 {run_dir} (추적 제외 {state})",
        "next": f'source "{env}" 로 SHOT_DIR 을 불러 쓰세요. 캡처·증거는 전부 그 아래에 둡니다',
    })


def _shot_dir(root: Path) -> Path:
    """캡처를 둘 곳. env.sh 를 source 했으면 그 실행 폴더, 아니면 상태 폴더의 shots."""
    env_shot = os.environ.get("SHOT_DIR")
    d = Path(env_shot) if env_shot else _home(root) / "shots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _shot_target(root: Path, name: str | None, ext: str = ".png") -> tuple[Path, bool]:
    """(저장 경로, 경로를 직접 줬는가). 이름만 주면 SHOT_DIR 아래에 둔다."""
    if name and (os.sep in name or "/" in name):
        p = Path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p, True
    stem = Path(name).stem if name else time.strftime("%Y%m%d-%H%M%S")
    return _shot_dir(root) / f"{stem}{ext}", False


def _finish_shot(raw: Path, explicit: bool, args) -> Path:
    """경로를 직접 줬거나 --keep-format 이면 그대로, 아니면 줄이고 WebP 로."""
    if explicit or getattr(args, "keep_format", False):
        return raw
    return to_webp(raw, quality=args.quality, max_side=args.max_side or None) or raw


# =========================================================================
# 앱 — 찍고(shot) 띄운다(launch)
# =========================================================================

# 상태바를 고정해 캡처끼리 시각·배터리가 달라 보이지 않게 한다. 찍은 뒤 되돌린다.
_ANDROID_DEMO = [
    ["settings", "put", "global", "sysui_demo_allowed", "1"],
    ["am", "broadcast", "-a", "com.android.systemui.demo", "-e", "command", "enter"],
    ["am", "broadcast", "-a", "com.android.systemui.demo", "-e", "command", "clock",
     "-e", "hhmm", "0941"],
    ["am", "broadcast", "-a", "com.android.systemui.demo", "-e", "command", "battery",
     "-e", "level", "100", "-e", "plugged", "false"],
    ["am", "broadcast", "-a", "com.android.systemui.demo", "-e", "command", "network",
     "-e", "wifi", "show", "-e", "level", "4"],
    ["am", "broadcast", "-a", "com.android.systemui.demo", "-e", "command", "notifications",
     "-e", "visible", "false"],
]
_ANDROID_DEMO_EXIT = ["am", "broadcast", "-a", "com.android.systemui.demo",
                      "-e", "command", "exit"]
_IOS_STATUS = ["--time", "9:41", "--batteryState", "charged", "--batteryLevel", "100",
               "--wifiBars", "3", "--cellularBars", "4"]


def _pick_device(want: str | None) -> tuple[str | None, str | None, dict]:
    """(플랫폼, id, 기기 목록). --device → $DEV → 붙은 게 한 대뿐이면 그것."""
    dev = _devices()
    udids = _ios_udids(dev)
    cand = want or os.environ.get("DEV") or None
    if not cand:
        every = dev["android"] + udids
        cand = every[0] if len(every) == 1 else None
    if not cand:
        return None, None, dev
    if cand in dev["android"]:
        _set_area("android")
        return "android", cand, dev
    if cand in udids or cand == "booted":
        _set_area("ios")
        return "ios", cand, dev
    return None, cand, dev


def _no_device(dev: dict, want: str | None) -> int:
    return out({
        "ok": False, "code": "no_device",
        "error": (f"'{want}' 기기를 찾지 못했습니다" if want
                  else "어느 기기인지 정할 수 없습니다 (붙은 기기가 없거나 여러 대)"),
        "android": dev["android"], "ios_booted": dev["ios_booted"],
        "android_avds": dev["android_avds"],
        "next": ("emulator -avd {AVD명}  또는  xcrun simctl boot {UDID}" if not
                 (dev["android"] or dev["ios_booted"]) else "--device 로 하나를 고르세요"),
    })


def _app_shot(args) -> int:
    root = _root(args)
    platform, dev_id, dev = _pick_device(args.device)
    if not platform:
        return _no_device(dev, args.device)
    raw, explicit = _shot_target(root, args.out)

    restore = None
    try:
        if platform == "android":
            adb = sdk_tool("adb")
            if args.clean_status:
                # 데모 모드 허용 설정도 찍기 전 값으로 되돌린다 — 남의 기기 설정을 바꿔 두지 않는다
                prev = _adb_shell(dev_id, "settings", "get", "global",
                                  "sysui_demo_allowed").strip()
                for c in _ANDROID_DEMO:
                    _adb_shell(dev_id, *c)

                def _undo_demo():
                    _adb_shell(dev_id, *_ANDROID_DEMO_EXIT)
                    if prev in ("", "null"):
                        _adb_shell(dev_id, "settings", "delete", "global", "sysui_demo_allowed")
                    else:
                        _adb_shell(dev_id, "settings", "put", "global",
                                   "sysui_demo_allowed", prev)
                restore = _undo_demo
                time.sleep(0.6)
            # exec-out 은 바이너리를 그대로 준다. shell 로 받으면 줄바꿈이 바뀌어 PNG 가 깨진다
            r = subprocess.run([adb, "-s", dev_id, "exec-out", "screencap", "-p"],
                               capture_output=True, timeout=30)
            data = r.stdout
            if not data.startswith(b"\x89PNG"):
                return out({"ok": False, "code": "capture_failed", "device": dev_id,
                            "error": (r.stderr or b"").decode("utf-8", "replace")[:300]
                                     or "PNG 가 아닌 응답",
                            "hint": "화면이 잠겨 있거나 보안 화면(FLAG_SECURE)일 수 있습니다"})
            raw.write_bytes(data)
        else:
            if args.clean_status:
                run(["xcrun", "simctl", "status_bar", dev_id, "override", *_IOS_STATUS])
                restore = lambda: run(["xcrun", "simctl", "status_bar", dev_id, "clear"])  # noqa: E731
                time.sleep(0.6)
            r = subprocess.run(["xcrun", "simctl", "io", dev_id, "screenshot", str(raw)],
                               capture_output=True, text=True, timeout=30)
            if r.returncode != 0 or not raw.exists():
                return out({"ok": False, "code": "capture_failed", "device": dev_id,
                            "error": (r.stderr or "").strip()[:300]})
    except (OSError, subprocess.SubprocessError) as e:
        return out({"ok": False, "code": "capture_failed", "device": dev_id, "error": str(e)})
    finally:
        if restore:
            restore()

    final = _finish_shot(raw, explicit, args)
    return out({"action": "shot", "platform": platform, "device": dev_id,
                "file": str(final), "clean_status": bool(args.clean_status),
                "summary": f"{platform} 화면을 찍었습니다: {final.name}",
                "next": "이미지를 읽어 다음 조작을 정하세요"})


def _app_launch(args) -> int:
    root = _root(args)
    platform, dev_id, dev = _pick_device(args.device)
    if not platform:
        return _no_device(dev, args.device)
    pkg = args.pkg or os.environ.get("PKG") or _load_devices(root)["package"]
    if not pkg:
        return out({"ok": False, "code": "package_required",
                    "error": "띄울 앱을 모릅니다",
                    "next": "--pkg <패키지명·번들ID>  (detect 가 찾은 값을 쓰세요)"})
    if platform == "android":
        # monkey 는 런처 액티비티 이름을 몰라도 띄운다 — am start 는 액티비티까지 알아야 한다
        text = _adb_shell(dev_id, "monkey", "-p", pkg, "-c",
                          "android.intent.category.LAUNCHER", "1")
        ok = "Events injected: 1" in text
        err = None if ok else (text.strip()[-300:] or "앱을 띄우지 못했습니다")
    else:
        r = subprocess.run(["xcrun", "simctl", "launch", dev_id, pkg],
                           capture_output=True, text=True, timeout=30)
        ok = r.returncode == 0
        err = None if ok else (r.stderr or "").strip()[:300]
    return out({"ok": ok, "code": "ok" if ok else "launch_failed",
                "platform": platform, "device": dev_id, "package": pkg, "error": err,
                "summary": f"{pkg} 실행" + ("" if ok else " 실패"),
                "next": "app shot  # 뜬 화면을 봅니다" if ok else
                        "설치돼 있는지 확인하세요 (device list 의 installed)"})


def _app_type(args) -> int:
    """기기 화면의 포커스된 입력창에 글자를 넣는다. 로그인 정보는 저장된 자격증명에서 꺼내 쓴다.

    값은 명령줄이 아니라 표준입력으로만 기기에 보낸다 (호스트 `ps` 에 남지 않는다).
    Android 만 된다 — iOS 는 시뮬레이터에 텍스트를 넣는 공식 명령이 없다.
    """
    if getattr(args, "cred", None):
        value, err = _cred_field(args.cred, getattr(args, "cred_field", None))
        if err:
            return out(err)
    elif getattr(args, "text_env", None):
        if args.text_env not in os.environ:
            return out({"ok": False, "code": "env_not_set", "error": f"환경변수 {args.text_env} 가 비어 있습니다"})
        value = os.environ[args.text_env]
    else:
        return out({"ok": False, "code": "text_required",
                    "error": "--cred 또는 --text-env 가 필요합니다 (값을 --text 로 적지 않는다 — 기록에 평문으로 남는다)",
                    "next": "cred list  # 저장된 로그인 정보"})
    platform, dev_id, dev = _pick_device(args.device)
    if not platform:
        return _no_device(dev, args.device)
    if platform != "android":
        return out({"ok": False, "code": "ios_text_unsupported",
                    "error": "iOS 시뮬레이터에는 텍스트를 넣는 공식 명령이 없다",
                    "next": "프로젝트의 E2E 도구(Maestro 등)를 쓰거나 사용자에게 직접 입력을 부탁한다"})
    if not value.isascii():
        return out({"ok": False, "code": "non_ascii_unsupported",
                    "error": "adb input text 는 ASCII 만 받는다 (한글 불가)",
                    "next": "영문·숫자 값으로 대체하거나 ADBKeyboard 같은 IME 를 설치한다"})
    adb = sdk_tool("adb")
    if not adb:
        return out({"ok": False, "code": "adb_missing", "error": "adb 를 찾지 못했습니다"})
    # 공백은 `%s`. 값은 표준입력으로 읽어 따옴표 안에서만 쓴다 (셸 메타문자가 해석되지 않는다)
    payload = value.replace(" ", "%s") + "\n"
    try:
        r = subprocess.run([adb, "-s", dev_id, "shell", 'IFS= read -r T; input text "$T"'],
                           input=payload, capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and getattr(args, "submit", False):
            subprocess.run([adb, "-s", dev_id, "shell", "input", "keyevent", "66"],
                           capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        return out({"ok": False, "code": "app_type_timeout", "error": "기기 응답 없음 (30초)"})
    entry = {"password": value, "token": value}
    ok = r.returncode == 0
    return out({"ok": ok, "code": "ok" if ok else "app_type_failed", "device": dev_id,
                "chars": len(value), "submitted": bool(getattr(args, "submit", False)) and ok,
                "error": credentials.mask((r.stderr or "").strip(), entry)[:300] or None,
                "summary": f"{len(value)}자 입력" + (" + Enter" if getattr(args, "submit", False) and ok else ""),
                "next": "app shot  # 입력됐는지 화면으로 확인한다 (비밀번호 칸은 가려져 보인다)"})


# ── 탭 · 스와이프 · 화면 구조 ─────────────────────────────────────────────
#
# 플랫폼 차이는 app_input.py 의 백엔드가 전부 맡는다. 여기는 인자 해석과 JSON 응답만 한다.
# 계약: 실패면 code + next(+ 못 찾았으면 candidates·locale), --shot 이면 shot·screen_changed.


def _backend_for(args):
    """(백엔드, 기기 id, 오류 응답). 기기를 못 고르거나 도구가 없으면 오류 응답을 채운다."""
    platform, dev_id, dev = _pick_device(args.device)
    if not platform:
        return None, None, _no_device(dev, args.device)
    be = app_input.get_backend(platform, getattr(args, "pkg", None) or os.environ.get("PKG"))
    if be is None:
        return None, None, out({"ok": False, "code": "platform_unsupported",
                                "error": f"{platform} 은 조작 백엔드가 없다",
                                "next": "references/extending.md 를 보고 백엔드를 추가한다"})
    if not be.available():
        return None, None, out({"ok": False, "code": f"{be.name}_tool_missing",
                                "error": f"{be.name} 조작 도구가 없다", "next": be.install_hint})
    return be, dev_id, None


def _before_shot(args, be, dev_id) -> bytes | None:
    """--shot 일 때만 동작 전 화면을 기억한다 — 나중에 '바뀐 뒤 멈춘 화면'을 고르는 기준."""
    return be.grab(dev_id) if getattr(args, "shot", None) else None


def _after_shot(args, be, dev_id, before: bytes | None) -> dict:
    """--shot 이면 동작 결과 화면을 찍는다 — 확인용 shot 호출 한 번을 아낀다.

    고정 대기는 실패한다(실측): Android 는 캡처가 느려 전환이 시작되기도 전에 같은 장면을 두 번
    찍고 '멈췄다'고 판단했다. 그래서 **동작 전 화면과 달라진 뒤, 연속 두 장이 같아질 때**를 고른다.
    끝내 안 바뀌면 screen_changed=false — '눌렀는데 반응 없음'을 agent 가 바로 안다.
    """
    if not getattr(args, "shot", None):
        return {}
    prev, data, changed, deadline = None, None, False, time.time() + 5.0
    while time.time() < deadline:
        data = be.grab(dev_id)
        if data is None:
            return {"shot": None}
        changed = changed or (before is not None and data != before)
        if changed and data == prev:
            break
        prev = data
        time.sleep(0.3)
    raw, explicit = _shot_target(_root(args), args.shot)
    raw.write_bytes(data)
    return {"shot": str(_finish_shot(raw, explicit, args)),
            "screen_changed": changed if before is not None else None}


def _gesture_result(args, be, dev_id, before, ok: bool, detail: str, fail_code: str,
                    summary: str, **extra) -> int:
    res = {"ok": ok, "code": "ok" if ok else fail_code, "device": dev_id, "via": be.name,
           **extra, "error": None if ok else (detail or "")[-400:] or None,
           "summary": summary if ok else f"실패 — {fail_code}",
           "next": "app shot  # 결과 화면 확인"}
    if ok:
        _auto_record_backend(be)
        res.update(_after_shot(args, be, dev_id, before))
        if res.get("shot"):
            res["next"] = ("shot 이미지를 읽어 결과를 확인한다" if res.get("screen_changed") is not False
                           else "화면이 그대로다 — 다른 요소를 고르거나 app tree 로 다시 본다")
    return out(res)


_BACKEND_HOW = {"android": "앱 누르기·밀기는 launch_cli app tap/swipe (uiautomator + adb input, 화면 요소 기준)로 된다",
                "ios": "앱 누르기·밀기는 launch_cli app tap/swipe (Maestro, 화면 요소 기준)로 된다"}


def _auto_record_backend(be) -> None:
    """실제로 성공한 조작 방식을 이 컴퓨터 범위에 남긴다 — 검증된 것만, 하루 한 번."""
    how = _BACKEND_HOW.get(be.name)
    if how:
        try:
            knowledge.auto_record(be.name, f"{be.name}.input", how)
        except Exception:   # noqa: BLE001 — 기록 실패가 조작 결과를 바꾸면 안 된다
            pass


def _not_found(be, dev_id, field: str, value: str, nodes: list[dict] | None) -> int:
    """못 찾았을 때 추측을 반복하지 않도록 화면 언어와 화면에 실제로 있는 값을 같이 준다."""
    if nodes is None:
        nodes = be.nodes(dev_id) or []
    cands = list(dict.fromkeys(n[field] for n in nodes if n[field]))[:25]
    return out({"ok": False, "code": "not_found", "device": dev_id,
                "error": f"{field}={value!r} 인 요소가 없다",
                "locale": be.locale(dev_id), "candidates": cands,
                "next": "candidates 의 값으로 다시 app tap (문구는 화면 언어 그대로)"})


def _app_tap(args) -> int:
    """화면 요소를 누른다. --text / --id / --desc 로 찾고, 요소가 없는 화면(캔버스·지도)만 --at 비율."""
    sel = next(((f, getattr(args, f"sel_{f}")) for f in app_input.SELECTOR_FIELDS
                if getattr(args, f"sel_{f}", None)), None)
    at = app_input.parse_ratio(getattr(args, "at", None))
    if getattr(args, "at", None) and not at:
        return out({"ok": False, "code": "bad_ratio",
                    "error": "--at 은 0~1 비율이다 (예: 0.5,0.8). 픽셀은 받지 않는다 — 캡처가 축소돼 있어 빗나간다"})
    if not sel and not at:
        return out({"ok": False, "code": "target_required",
                    "error": "--text · --id · --desc 중 하나, 또는 --at 비율 좌표가 필요하다",
                    "next": "app tree  # 누를 수 있는 요소와 화면 언어를 본다"})
    be, dev_id, err = _backend_for(args)
    if err is not None:
        return err
    before = _before_shot(args, be, dev_id)
    label = f"{sel[0]}={sel[1]!r}" if sel else f"at {args.at}"

    if not sel:
        ok, detail = be.tap_ratio(dev_id, *at)
        return _gesture_result(args, be, dev_id, before, ok, detail, "tap_failed", f"탭 ({label})")

    field, value = sel
    if be.selects_itself:
        ok, detail = be.tap_selector(dev_id, field, value)
        if not ok and "not found" in (detail or "").lower():
            return _not_found(be, dev_id, field, value, None)
        return _gesture_result(args, be, dev_id, before, ok, detail, "tap_failed", f"탭 ({label})")

    nodes = be.nodes(dev_id) or []
    if not nodes:
        return out({"ok": False, "code": "ui_dump_failed", "device": dev_id,
                    "error": "화면 구조를 읽지 못했다 (애니메이션 중이거나 보안 화면일 수 있다)",
                    "next": "잠시 뒤 다시 시도하거나 --at 비율 좌표를 쓴다"})
    found = app_input.match_nodes(nodes, field, value)
    if not found:
        return _not_found(be, dev_id, field, value, nodes)
    idx = getattr(args, "index", 0) or 0
    if idx >= len(found):
        return out({"ok": False, "code": "index_out_of_range", "matches": len(found)})
    target = found[idx]
    ok, detail = be.tap_xy(dev_id, *target["center"])
    return _gesture_result(args, be, dev_id, before, ok, detail, "tap_failed",
                           f"탭 {target['center']} ({label})",
                           element={k: v for k, v in target.items() if v not in ("", None)},
                           matches=len(found))


def _app_swipe(args) -> int:
    """스와이프. --dir up|down|left|right 또는 --from/--to 비율 좌표."""
    if getattr(args, "dir", None):
        start, end = app_input.SWIPE_DIRS[args.dir]
    else:
        start = app_input.parse_ratio(getattr(args, "frm", None))
        end = app_input.parse_ratio(getattr(args, "to", None))
        if not (start and end):
            return out({"ok": False, "code": "swipe_target_required",
                        "error": "--dir 또는 --from/--to (0~1 비율, 예: 0.5,0.8) 가 필요하다"})
    be, dev_id, err = _backend_for(args)
    if err is not None:
        return err
    before = _before_shot(args, be, dev_id)
    ms = getattr(args, "ms", 300) or 300
    ok, detail = be.swipe_ratio(dev_id, start, end, ms)
    return _gesture_result(args, be, dev_id, before, ok, detail, "swipe_failed",
                           f"스와이프 {args.dir or f'{start}→{end}'}")


def _app_tree(args) -> int:
    """누를 수 있는 요소와 화면 언어 — tap 의 --text/--id/--desc 를 고르는 용도."""
    be, dev_id, err = _backend_for(args)
    if err is not None:
        return err
    nodes = be.nodes(dev_id)
    if nodes is None:
        return out({"ok": False, "code": "tree_unsupported", "error": f"{be.name} 은 화면 구조를 읽지 못한다"})
    els = app_input.slim([n for n in nodes if n["text"] or n["desc"] or (n["clickable"] and n["id"])])
    return out({"ok": bool(els), "code": "ok" if els else "ui_dump_failed", "device": dev_id,
                "platform": be.name, "locale": be.locale(dev_id), "count": len(els), "elements": els,
                "summary": f"요소 {len(els)}개", "next": "app tap --text '<elements 의 text>'"})


def cmd_app(args) -> int:
    _MEMORY_CTX["root"] = _root(args)
    handlers = {"type": _app_type, "tap": _app_tap, "swipe": _app_swipe, "tree": _app_tree,
                "shot": _app_shot}
    return handlers.get(args.action, _app_launch)(args)


# =========================================================================
# 웹 — 브라우저를 직접 몬다 (#586)
# =========================================================================
#
# agent가 스크린샷을 보고 다음 수를 정하므로 조작이 여러 번의 CLI 호출로 쪼개진다.
# 상주 데몬을 만들지 않고 **CDP 재연결**로 푼다:
#   open  → --remote-debugging-port 로 띄우고 포트를 상태파일에 적는다
#   이후  → connect_over_cdp 로 그 브라우저에 붙었다 떨어진다 (세션·쿠키 유지)
#
# ⚠️ 붙어 있는 동안에만 사는 것이 있다 — 콘솔 훅·뷰포트·응답 바꿔치기. 연결이 끊기면
# 같이 사라진다(#625 실측). 그래서 상태 파일에 적어 두고 **붙을 때마다 다시 건다.**

_WEB_STATE = "browser.json"

# 콘솔 오류는 **페이지가 열리는 동안** 난다. 열린 뒤에 리스너를 달면 이미 늦다 (#625).
_CONSOLE_HOOK = r"""
(() => {
  if (window.__projectops_console) return;
  const buf = [];
  window.__projectops_console = buf;
  const push = (type, text) => {
    try { buf.push({ type, text: String(text).slice(0, 2000), at: Date.now() }); } catch (e) {}
    if (buf.length > 500) buf.splice(0, buf.length - 500);   // 무한히 쌓이지 않게
  };
  for (const level of ["log", "info", "warn", "error"]) {
    const orig = console[level];
    console[level] = function (...args) {
      push(level, args.map((a) => {
        try { return typeof a === "string" ? a : JSON.stringify(a); }
        catch (e) { return String(a); }
      }).join(" "));
      return orig.apply(console, args);
    };
  }
  // console.error 를 거치지 않는 것들 — 이쪽이 진짜 사고인 경우가 많다
  window.addEventListener("error", (e) => push("error", e.message || String(e.error || e)));
  window.addEventListener("unhandledrejection",
    (e) => push("error", "unhandled rejection: " + String(e.reason)));
})();
"""

# 폭을 바꿔 찍을 때 쓰는 이름. 숫자를 외우지 않게 한다.
VIEWPORT_PRESETS = {"mobile": (390, 844), "tablet": (820, 1180), "desktop": (1280, 800)}


def _install_console_hook(page) -> bool:
    try:
        page.add_init_script(_CONSOLE_HOOK)
        return True
    except Exception:
        return False


# ── agent 가 혼자 브라우저를 몰 수 있게 (#825) ───────────────────────────
#
# 스크린샷과 "있나 없나(assert)"만으로는 화면을 읽을 수 없어서 agent 가 선택자를 **추측**했다.
# 추측한 클릭은 엉뚱한 메뉴를 누르고도 ok 를 돌려줬다(Play Console 실측). 그래서 루프를 바꾼다.
#
#   web find  → 후보를 번호(ref)·글자·링크 주소와 함께 돌려준다 (요소에 data-pops-ref 를 단다)
#   web click --ref N --expect-url/--expect-text → 그 요소만 누르고, 결과가 안 오면 실패로 보고한다
#   web text  → 보이는 글자를 읽는다 (스크린샷보다 훨씬 싸다)
#
# 관리 콘솔(Play Console · App Store Connect)은 `web open --readonly` 로 연다.
# 읽기 전용 세션에서는 되돌릴 수 없는 일을 하는 버튼을 --confirm-mutating 없이 누르지 않는다.

_REF_ATTR = "data-pops-ref"

# 읽기 전용 세션에서 막는 버튼 문구. "취소·확인"은 대화상자를 닫는 데도 쓰여 넣지 않았다.
_MUTATING_RE = re.compile(
    r"(삭제|제거|출시|게시|제출|전송|보내기|저장|승인|결제|구매|업로드|배포|폐기|롤아웃|"
    r"\b(delete|remove|publish|release|roll ?out|submit|send|save|approve|pay|purchase|upload|deploy|discard)\b)",
    re.IGNORECASE)


def _is_mutating(label: str) -> bool:
    """버튼 문구가 되돌리기 어려운 동작인가. 읽기 전용 세션에서 클릭을 막는 기준이다."""
    return bool(_MUTATING_RE.search(label or ""))


# 화면 이동으로 보는 요소 — 문구에 "제출·게시"가 있어도 막지 않는다.
# Play Console 의 "제출 활동"·"게시 개요"는 기록을 보는 링크인데, 문구만 보면 위험 버튼으로 걸렸다(실측).
_NAV_ROLES = {"link", "tab", "row", "menuitem", "treeitem", "option"}


def _is_mutating_target(info: dict) -> bool:
    """요소 종류까지 보고 판단한다. 링크·탭·행은 이동이라 허용하고, 버튼류만 문구로 검사한다."""
    tag, role = (info.get("tag") or ""), (info.get("role") or "")
    if (tag == "a" and info.get("href")) or role in _NAV_ROLES:
        return False
    return _is_mutating(f"{info.get('text') or ''} {info.get('aria') or ''}")


# 클릭할 수 있는 것으로 보는 요소. 표의 행(role=row)도 넣는다 — 콘솔은 행 전체가 링크인 경우가 많다.
_CLICKABLE = ("a[href],button,[role=button],[role=link],[role=tab],[role=menuitem],[role=row],"
              "[role=option],[role=checkbox],[role=switch],[onclick],input[type=submit],"
              "input[type=button],input[type=checkbox],summary")

_FIND_JS = """(o) => {
  const ATTR = o.attr;
  document.querySelectorAll('[' + ATTR + ']').forEach(e => e.removeAttribute(ATTR));
  const visible = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const label = e => ((e.innerText || e.value || '') + ' ' + (e.getAttribute('aria-label') || '')).replace(/\\s+/g, ' ').trim();
  let els;
  if (o.selector) els = [...document.querySelectorAll(o.selector)];
  else if (o.role === 'link') els = [...document.querySelectorAll('a[href],[role=link]')];
  else if (o.role === 'button') els = [...document.querySelectorAll('button,[role=button],input[type=submit],input[type=button]')];
  else if (o.role) els = [...document.querySelectorAll('[role=' + o.role + ']')];
  else els = [...document.querySelectorAll(o.clickable)];
  let fallback = false;
  if (o.text) {
    const t = o.text.toLowerCase();
    let hit = els.filter(e => label(e).toLowerCase().includes(t));
    if (!hit.length && !o.selector && !o.role) {
      // 클릭 가능한 요소 안에 그 글자가 없으면, 글자를 가진 가장 안쪽 요소를 찾아 가장 가까운 클릭 대상으로 올린다
      const leaves = [...document.querySelectorAll('body *')].filter(e =>
        (e.innerText || '').toLowerCase().includes(t) &&
        ![...e.children].some(c => (c.innerText || '').toLowerCase().includes(t)));
      hit = [...new Set(leaves.map(e => e.closest(o.clickable) || e))];
      fallback = true;
    }
    els = hit;
  }
  // 구체적인 것부터 — 진짜 링크·버튼이 그것을 감싼 행보다 먼저 나와야 첫 후보를 눌러도 헛클릭이 안 된다.
  // (Play Console 실측: 행이 먼저 나와 눌렀더니 아무 일도 없었고, 실제 링크는 행 안의 화살표였다)
  const rank = e => (e.matches('a[href]') ? 0 : e.matches('button,input[type=submit],input[type=button]') ? 1
    : e.matches('[role=link],[role=button],[role=tab],[role=menuitem]') ? 2 : e.matches('[role=row]') ? 4 : 3);
  els = els.map((e, i) => [e, i]).sort((a, b) => rank(a[0]) - rank(b[0]) || a[1] - b[1]).map(x => x[0]);
  const items = [];
  for (const e of els) {
    if (items.length >= o.limit) break;
    if (!visible(e)) continue;
    const ref = items.length + 1;
    e.setAttribute(ATTR, String(ref));
    items.push({ ref, tag: e.tagName.toLowerCase(), role: e.getAttribute('role'),
      text: (e.innerText || e.value || '').replace(/\\s+/g, ' ').trim().slice(0, 120),
      aria: e.getAttribute('aria-label'), href: e.getAttribute('href'),
      clickable: e.matches(o.clickable),
      disabled: !!e.disabled || e.getAttribute('aria-disabled') === 'true' });
  }
  return { items, total: els.length, fallback };
}"""

_DESCRIBE_JS = """(e) => ({ tag: e.tagName.toLowerCase(), role: e.getAttribute('role'),
  text: (e.innerText || e.value || '').replace(/\\s+/g, ' ').trim().slice(0, 120),
  aria: e.getAttribute('aria-label'), href: e.getAttribute('href') })"""


def _web_find(page, args) -> dict:
    res = page.evaluate(_FIND_JS, {"attr": _REF_ATTR, "clickable": _CLICKABLE, "text": args.text,
                                   "role": args.role, "selector": args.selector, "limit": args.limit})
    items = res.get("items") or []
    for it in items:
        it["mutating"] = _is_mutating_target(it)
    if not items:
        return {"ok": False, "code": "nothing_found", "action": "find", "url": page.url, "title": page.title(),
                "error": "조건에 맞는 보이는 요소가 없습니다",
                "next": "web text  # 화면 글자를 먼저 읽고 --text 를 그 글자로 다시 찾는다"}
    return {"action": "find", "items": items, "total": res.get("total"), "shown": len(items),
            "fallback": res.get("fallback"), "url": page.url, "title": page.title(),
            "summary": f"후보 {len(items)}개 (전체 {res.get('total')})",
            "next": "web click --ref <번호> --expect-url <바뀔 주소 일부>  # 고른 것만 누른다"}


def _web_text(page, args) -> dict:
    loc = page.locator(args.selector).first if args.selector else page.locator("body")
    if args.selector and page.locator(args.selector).count() == 0:
        return {"ok": False, "code": "selector_not_found", "action": "text", "url": page.url,
                "error": f"{args.selector} 에 맞는 요소가 없습니다", "next": "web find --text <글자>"}
    raw = loc.inner_text(timeout=args.timeout * 1000)
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    text = "\n".join(lines)
    cut = len(text) > args.max_chars
    return {"action": "text", "text": text[:args.max_chars], "truncated": cut, "chars": len(text),
            "url": page.url, "title": page.title(),
            "summary": f"글자 {len(text)}자" + (f" (앞 {args.max_chars}자만)" if cut else ""),
            "next": "web find --text <누를 것의 글자>" + ("  # 잘렸으면 --selector 로 범위를 좁힌다" if cut else "")}


def _web_click(page, args, state: dict) -> dict:
    """고른 요소 하나만 누르고, 무엇을 눌렀고 무엇이 바뀌었는지 돌려준다."""
    if args.ref is None and not args.selector:
        return {"ok": False, "code": "target_required", "action": "click",
                "error": "--ref 나 --selector 가 필요합니다",
                "next": "web find --text <글자>  # 후보 번호를 받아 --ref 로 누른다"}
    target = f'[{_REF_ATTR}="{args.ref}"]' if args.ref is not None else args.selector
    loc = page.locator(target)
    if loc.count() == 0:
        if args.ref is not None:
            return {"ok": False, "code": "ref_stale", "action": "click", "url": page.url,
                    "error": f"ref {args.ref} 이 화면에 없습니다 (이동·다시 그리기로 사라졌다)",
                    "next": "web find  # 지금 화면에서 다시 고른다"}
        return {"ok": False, "code": "selector_not_found", "action": "click", "url": page.url,
                "error": f"{args.selector} 에 맞는 요소가 없습니다", "next": "web find --text <글자>"}
    el = loc.first
    info = el.evaluate(_DESCRIBE_JS)
    label = f"{info.get('text') or ''} {info.get('aria') or ''}"
    if state.get("readonly") and _is_mutating_target(info) and not args.confirm_mutating:
        return {"ok": False, "code": "mutating_blocked", "action": "click", "clicked": None,
                "target": info, "url": page.url,
                "error": f"읽기 전용 세션이라 '{label.strip()[:60]}' 을 누르지 않았습니다",
                "next": "정말 눌러야 하면 사용자에게 무엇이 바뀌는지 말하고 승인받은 뒤 --confirm-mutating 을 붙인다"}
    before_url, before_title = page.url, page.title()
    el.click(timeout=args.timeout * 1000)
    waited = None
    try:
        if args.expect_url:
            waited = "url"
            page.wait_for_url(lambda u: args.expect_url in u, timeout=args.timeout * 1000)
        elif args.expect_text:
            waited = "text"
            page.get_by_text(args.expect_text).first.wait_for(state="visible", timeout=args.timeout * 1000)
        else:
            # 기대를 안 줬으면 짧게만 기다린다 — SPA 는 주소가 늦게 바뀐다
            try:
                page.wait_for_load_state("domcontentloaded", timeout=3000)
            except Exception:
                pass
            page.wait_for_timeout(800)
    except Exception:
        return {"ok": False, "code": "expect_not_met", "action": "click", "clicked": info,
                "expected": args.expect_url or args.expect_text,
                "before": {"url": before_url, "title": before_title},
                "url": page.url, "title": page.title(),
                "error": f"눌렀지만 기대한 {'주소' if waited == 'url' else '글자'}가 {args.timeout}초 안에 나오지 않았습니다",
                "next": "web text  # 지금 화면을 읽고, 엉뚱한 것을 눌렀으면 web find 로 다시 고른다"}
    _settle(page, state, args.timeout)
    after_url, after_title = page.url, page.title()
    changed = after_url != before_url or after_title != before_title
    payload = {"action": "click", "clicked": info, "changed": changed,
               "before": {"url": before_url, "title": before_title},
               "url": after_url, "title": after_title,
               "summary": f"'{(info.get('text') or info.get('aria') or info.get('tag'))[:40]}' 클릭 → "
                          + ("주소·제목이 바뀌었다" if changed else "주소·제목 그대로")}
    if not changed and not (args.expect_url or args.expect_text):
        # 체크박스·펼치기처럼 제자리에서 바뀌는 것일 수도 있다 — 실패로 단정하지 않고 확인을 시킨다
        payload["next"] = "의도한 결과가 맞는지 web text / web assert 로 확인한다. 아니면 web find 로 다시 고른다"
    else:
        payload["next"] = "web text  # 바뀐 화면을 읽는다"
    return payload


def _profile_in_use(profile: Path) -> bool:
    """이 프로필로 떠 있는 브라우저 프로세스가 있나 — 잠금 파일을 지워도 되는지 가른다."""
    try:
        ps = subprocess.run(["ps", "-ax", "-o", "command="], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return True   # 확인 못 하면 쓰는 중으로 본다 — 남의 브라우저 잠금을 지우지 않는다
    return f"--user-data-dir={profile}" in ps


def _web_state_path(root: Path) -> Path:
    _home(root)
    return launch_file(root, _WEB_STATE)


def _read_web_state(f: Path) -> dict:
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_web_state(f: Path, state: dict) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def _require_playwright() -> tuple[object | None, dict | None]:
    """Playwright를 불러온다. 전용 가상환경 → 시스템 순으로 본다.

    함수 안에서 import하는 이유: 웹을 안 쓰는 프로젝트에서 이 스크립트가 통째로
    죽으면 안 된다. 앱·서버는 Playwright 없이 돌아가야 한다.
    """
    sp = venv_site_packages()
    if sp and str(sp) not in sys.path:
        sys.path.insert(0, str(sp))
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright, None
    except ImportError:
        vd = venv_dir()
        return None, {
            "ok": False, "code": "playwright_missing",
            "error": "웹을 띄우려면 Playwright가 필요합니다",
            "fix": "web setup  # 전용 환경을 만들고 브라우저까지 받습니다 (약 100MB)",
            "manual": f"{sys.executable} -m venv {vd} && "
                      f"{vd}/bin/pip install playwright pillow && "
                      f"{vd}/bin/python -m playwright install chromium",
            "why": ("별도 설치물에 기대지 않으려고 Playwright를 직접 씁니다. "
                    "시스템 파이썬을 건드리지 않도록 전용 환경에 깝니다"),
            "ask_user": "웹을 띄우려면 브라우저(약 100MB)를 받아야 합니다. 설치할까요?",
        }


def _playwright_state() -> dict:
    ok, err = _require_playwright()
    if err:
        return {"ready": False, "reason": err["error"], "fix": err["fix"],
                "ask_user": err["ask_user"]}
    return {"ready": True, "venv": str(venv_dir()) if venv_python() else "시스템"}


def _apply_routes(page, rules: list[dict]) -> int:
    """응답 바꿔치기 규칙을 건다. 이 연결이 붙어 있는 동안만 산다."""
    n = 0
    for rule in rules:
        # Playwright 는 handler(route, request) 로 부른다. 기본 인자로 rule 을 묶으면
        # 두 번째 인자(request)가 그 자리를 덮는다 — 실측으로 겪었다. 클로저로 묶는다.
        page_route = _route_handler(rule)
        try:
            page.route(rule["match"], page_route)
            n += 1
        except Exception:
            continue
    return n


def _route_handler(rule: dict):
    def handler(route, *_):
        if rule.get("delay_ms"):
            time.sleep(rule["delay_ms"] / 1000)
        if rule.get("status") is None:
            route.continue_()
            return
        route.fulfill(status=int(rule["status"]),
                      headers={"content-type": rule.get("content_type") or "application/json",
                               "access-control-allow-origin": "*"},
                      body=rule.get("body") or "")
    return handler


def _install_stealth(ctx, page) -> bool:
    """자동화 표식 가리기 스크립트를 건다. 컨텍스트에 걸어야 붙어 있는 동안 뜨는 팝업(로그인 창)도 덮는다."""
    ok = True
    for script in stealth.init_scripts():
        try:
            ctx.add_init_script(script)
        except Exception:
            try:
                page.add_init_script(script)
            except Exception:
                ok = False
    return ok


def _close_blank_tabs(ctx, keep) -> int:
    """작업 탭(keep) 외의 about:blank 탭을 닫는다.
    web open 마다 about:blank 로 띄우고 영속 프로필이 옛 탭을 복원해서 빈 탭이 쌓인다."""
    closed = 0
    for pg in list(ctx.pages):
        try:
            if pg != keep and pg.url == "about:blank":
                pg.close()
                closed += 1
        except Exception:
            pass
    return closed


def _web_connect(state: dict):
    """열려 있는 브라우저에 붙고, 붙어 있는 동안만 사는 설정(훅·stealth·뷰포트·규칙)을 다시 건다."""
    sync_playwright, err = _require_playwright()
    if err:
        return None, err
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(state["cdp"])
    except Exception as e:
        pw.stop()
        return None, {"ok": False, "code": "browser_gone",
                      "error": f"열린 브라우저에 붙지 못했습니다: {e}",
                      "next": "web open  # 다시 엽니다"}
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    # 마지막 탭을 본다. 프로필이 영속이라 Chromium 이 옛 탭을 되살리는데,
    # pages[0] 을 잡으면 방금 연 탭이 아니라 그 옛 탭을 몰게 된다(실측).
    page = ctx.pages[-1] if ctx.pages else ctx.new_page()
    # 옛 상태 파일(키 없음)은 켠 것으로 본다 — 끄는 것은 --no-stealth 로 명시할 때뿐이다
    if state.get("stealth", True):
        _install_stealth(ctx, page)
    _install_console_hook(page)
    vp = state.get("viewport")
    if vp:
        try:
            page.set_viewport_size({"width": int(vp[0]), "height": int(vp[1])})
        except Exception:
            pass
    _apply_routes(page, state.get("routes") or [])
    return (pw, browser, page), None


def _settle(page, state: dict, timeout: int) -> None:
    """바꿔치기 규칙이 있으면 요청이 다 끝날 때까지 기다린다.

    규칙은 이 연결이 끊기면 사라진다. 로드가 끝나기 전에 떨어지면 뒤늦은 API 요청은
    진짜 응답을 받는다 — 빈 목록을 연출했는데 목록이 채워지는 이유가 이것이다.
    """
    if not state.get("routes"):
        return
    try:
        page.wait_for_load_state("networkidle", timeout=min(timeout, 15) * 1000)
    except Exception:
        pass


def _web_setup(force: bool = False) -> dict:
    """전용 가상환경 + Playwright + Pillow + Chromium. 약 100MB 라 부르는 쪽이 먼저 묻는다."""
    vd = venv_dir()
    steps = []
    if not venv_python() or force:
        r = subprocess.run([sys.executable, "-m", "venv", str(vd)],
                           capture_output=True, text=True)
        steps.append({"step": "가상환경 생성", "ok": r.returncode == 0,
                      "error": (r.stderr or "")[-300:] or None})
        if r.returncode != 0:
            return {"ok": False, "code": "venv_failed", "steps": steps,
                    "error": "가상환경을 만들지 못했습니다"}
    vpy = venv_python()
    if vpy is None:
        return {"ok": False, "code": "venv_missing", "steps": steps,
                "error": "가상환경 파이썬을 찾지 못했습니다"}
    # Pillow 를 함께 깐다 — 캡처를 줄이는 수단을 시스템을 건드리지 않고 확보한다
    r = subprocess.run([str(vpy), "-m", "pip", "install", "-q", "playwright", "pillow"],
                       capture_output=True, text=True, timeout=900)
    steps.append({"step": "playwright · pillow 설치", "ok": r.returncode == 0,
                  "error": (r.stderr or "")[-300:] or None})
    if r.returncode != 0:
        return {"ok": False, "code": "pip_failed", "steps": steps,
                "error": "playwright를 설치하지 못했습니다"}
    r = subprocess.run([str(vpy), "-m", "playwright", "install", "chromium"],
                       capture_output=True, text=True, timeout=1800)
    steps.append({"step": "chromium 내려받기", "ok": r.returncode == 0,
                  "error": (r.stderr or "")[-300:] or None})
    if r.returncode != 0:
        return {"ok": False, "code": "browser_failed", "steps": steps,
                "error": "브라우저를 받지 못했습니다"}
    return {"ok": True, "steps": steps, "venv": str(vd),
            "summary": "웹을 띄울 준비가 됐습니다", "next": "web open --url <주소>"}


def _web_open(args, root: Path, state_f: Path) -> int:
    sync_playwright, err = _require_playwright()
    if err:
        return out(err)
    prev = _read_web_state(state_f)
    # 이미 떠 있으면 새로 띄우지 않고 붙는다 (#825). 예전엔 프로필 잠금 때문에 실패로 끝나
    # agent 가 "브라우저를 못 띄운다"로 읽었는데, 정작 떠 있던 브라우저는 멀쩡히 쓸 수 있었다.
    if prev.get("cdp") and prev.get("pid") and _pid_alive(int(prev["pid"])):
        conn, cerr = _web_connect(prev)
        if not cerr:
            _pw, _br, _pg = conn
            prev["readonly"] = bool(args.readonly)
            prev["last_used"] = time.strftime("%Y-%m-%d %H:%M:%S")
            _write_web_state(state_f, prev)
            try:
                if args.url:
                    _pg.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout * 1000)
                    _settle(_pg, prev, args.timeout)
                url, title = _pg.url, _pg.title()
            except Exception as e:
                _pw.stop()
                return out({"ok": False, "code": "goto_failed", "error": str(e)[:300],
                            "hint": "주소가 맞는지, 서버가 떠 있는지 확인하세요"})
            _pw.stop()
            warn = None
            if bool(args.headed) != bool(prev.get("headed")):
                warn = "headed 여부는 새로 띄울 때만 바뀐다 — 바꾸려면 web close 후 다시 open"
            return out({"action": "open", "reused": True, "pid": prev["pid"], "url": url, "title": title,
                        "readonly": prev["readonly"], "opened_at": prev.get("opened_at"), "warning": warn,
                        "summary": f"떠 있던 브라우저에 붙었습니다 ({prev.get('opened_at')}부터)",
                        "next": "web text  # 화면 글자를 먼저 읽는다"})
    # 죽은 브라우저가 남긴 잠금은 치운다 — 아무도 이 프로필을 안 쓰는 것을 확인한 뒤에만
    profile_dir = _home(root) / ".browser-profile"
    if not _profile_in_use(profile_dir):
        for n in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
            try:
                (profile_dir / n).unlink()
            except (FileNotFoundError, IsADirectoryError, PermissionError):
                pass
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    # ⚠️ Playwright의 launch()로 띄우면 **드라이버가 죽을 때 브라우저도 함께 죽는다.**
    # 호출이 여러 번으로 쪼개지므로 두 번째 명령이 붙을 곳이 없어진다(실측).
    # 그래서 브라우저를 Playwright 밖에서 독립 프로세스로 띄우고 CDP로 붙는다.
    with sync_playwright() as pw:
        exe = pw.chromium.executable_path
    # 패키지는 있는데 브라우저 파일을 안 받았거나 지워진 경우 — 예외로 죽지 않고 고칠 길을 준다
    if not exe or not Path(exe).exists():
        return out({"ok": False, "code": "browser_missing",
                    "error": "Chromium 이 설치돼 있지 않습니다",
                    "path": exe, "next": "web setup  # 브라우저(약 100MB)를 받습니다"})
    profile = _home(root) / ".browser-profile"
    profile.mkdir(parents=True, exist_ok=True)
    cmd = [exe, f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
           f"--window-size={args.width},{args.height}",
           "--no-first-run", "--no-default-browser-check"]
    # Google·Apple 로그인은 자동화 브라우저를 막는다. 실행 인자는 연결을 끊은 뒤 뜨는 팝업에도 걸린다
    use_stealth = not args.no_stealth
    if use_stealth:
        cmd += stealth.launch_args(exe)
    if not args.headed:
        cmd.append("--headless=new")
    # ⚠️ 목적지를 여기서 넘기면 **훅을 심기 전에 첫 로드가 끝난다** (#625).
    cmd.append("about:blank")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)   # 우리가 끝나도 살아 있어야 한다
    cdp = f"http://127.0.0.1:{port}"
    for _ in range(60):
        with socket.socket() as probe:
            probe.settimeout(0.3)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                break
        time.sleep(0.25)
    else:
        exit_code = proc.poll()
        proc.terminate()
        # 원인을 가려 준다 — 남은 프로세스·프로필 잠금이면 브라우저를 다시 받아도 소용없다 (#712)
        prev = _read_web_state(state_f)
        stale = prev.get("pid")
        stale_alive = bool(stale) and _pid_alive(int(stale))
        locked = any((profile / n).exists() for n in ("SingletonLock", "SingletonSocket"))
        causes = []
        if stale_alive:
            causes.append(f"이전 브라우저(pid {stale})가 아직 살아 있다 → web close 로 정리")
        if locked:
            causes.append("프로필 잠금(SingletonLock)이 남아 있다 → 떠 있는 브라우저가 없으면 잠금 파일을 지운다")
        if exit_code is not None:
            causes.append(f"브라우저가 바로 종료됐다 (종료코드 {exit_code})")
        return out({"ok": False, "code": "browser_start_failed",
                    "error": "브라우저가 뜨지 않았습니다",
                    "causes": causes or None, "stale_pid": stale if stale_alive else None,
                    "profile_locked": locked, "profile": str(profile),
                    "hint": ("; ".join(causes) if causes else
                             "남은 브라우저 프로세스·프로필 잠금을 먼저 확인하고, 그래도 안 되면 web setup 으로 브라우저를 다시 받아 보세요")})

    # 뷰포트·바꿔치기 규칙은 브라우저를 다시 열어도 이어간다 — 설정한 사람이 끈 적이 없다
    prev = _read_web_state(state_f)
    state = {"cdp": cdp, "pid": proc.pid, "headed": bool(args.headed),
             "stealth": use_stealth, "profile": str(profile), "opened_at": time.strftime("%Y-%m-%d %H:%M:%S"),
             "last_used": time.strftime("%Y-%m-%d %H:%M:%S"), "readonly": bool(args.readonly),
             "viewport": prev.get("viewport"), "routes": prev.get("routes") or []}
    _write_web_state(state_f, state)

    hooked = False
    conn, cerr = _web_connect(state)
    if not cerr:
        _pw, _br, _pg = conn
        hooked = True
        # 빈 탭 정리 — 이전 open 이 남긴 about:blank 가 누적되는 것을 막는다
        try:
            _close_blank_tabs(_pg.context, _pg)
        except Exception:
            pass
        if args.url:
            try:
                _pg.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout * 1000)
                _settle(_pg, state, args.timeout)
            except Exception as e:
                _br.close(); _pw.stop()
                return out({"ok": False, "code": "goto_failed", "error": str(e),
                            "hint": "주소가 맞는지, 서버가 떠 있는지 확인하세요"})
        _br.close()
        _pw.stop()
    return out({"action": "open", "url": args.url, "cdp": cdp, "pid": proc.pid,
                "state_file": str(state_f), "console_hook": hooked,
                "routes": len(state["routes"]), "viewport": state["viewport"],
                "stealth": use_stealth, "readonly": bool(args.readonly), "reused": False,
                "summary": f"브라우저를 열었습니다 ({args.url or '빈 탭'})"
                           + (" — 읽기 전용" if args.readonly else ""),
                "next": "web text  # 화면 글자를 먼저 읽는다 (모양을 봐야 할 때만 web shot)"})


def _pid_alive(pid: int) -> bool:
    """프로세스가 살아 있나. 우리가 띄운 자식이 좀비로 남은 경우는 거둬들이고 죽은 것으로 본다."""
    try:
        done, _ = os.waitpid(pid, os.WNOHANG)   # 자식이면 거둬들인다 (아니면 ChildProcessError)
        if done:
            return False
    except ChildProcessError:
        pass
    except OSError:
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _kill_browser(pid: int, grace: float = 5.0) -> bool:
    """브라우저를 직접 정리한다. 정상 종료를 기다리다 안 죽으면 강제 종료한다. 살아 있으면 True.

    CDP 로 붙어 close() 를 부르면 응답 없는 브라우저에서 제한 없이 멈춘다 (#712).
    독립 프로세스로 띄웠으니 신호로 끝내는 편이 확실하다.
    """
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 3.0)):
        try:
            # 새 세션으로 띄웠으므로 pid 가 프로세스 그룹 id 이기도 하다 — 자식 렌더러까지 함께 정리
            os.killpg(pid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                os.kill(pid, sig)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        end = time.time() + wait
        while time.time() < end:
            if not _pid_alive(pid):
                return False
            time.sleep(0.1)
    return _pid_alive(pid)


def _web_close(state: dict, state_f: Path) -> int:
    pid = state.get("pid")
    alive = False
    if pid:
        try:
            alive = _kill_browser(int(pid))
        except ValueError:
            pass
    # ⚠️ 살아 있으면 상태 파일을 남긴다. 지우면 떠 있는 브라우저에 다시 붙을 길이 사라진다(실측).
    if alive:
        return out({"ok": False, "code": "browser_still_alive", "pid": pid,
                    "error": f"브라우저(pid {pid})가 아직 살아 있습니다",
                    "next": f"kill -9 {pid}  # 직접 종료한 뒤 다시 여세요"})
    state_f.unlink(missing_ok=True)
    return out({"action": "close", "summary": "브라우저를 닫았습니다"})


def _web_viewport(args, state: dict, state_f: Path) -> int:
    """폭을 바꿔 찍는다. 값은 상태 파일에 남아 다음 연결에도 걸린다."""
    if args.clear:
        state["viewport"] = None
        _write_web_state(state_f, state)
        return out({"action": "viewport", "viewport": None,
                    "summary": "뷰포트 지정을 풀었습니다 (창 크기를 따른다)"})
    preset = args.preset or ""
    if preset in VIEWPORT_PRESETS:
        w, h = VIEWPORT_PRESETS[preset]
    else:
        m = re.fullmatch(r"(\d{2,5})x(\d{2,5})", preset)
        if not m:
            return out({"ok": False, "code": "bad_viewport",
                        "error": f"뷰포트 '{preset}' 을 모릅니다",
                        "hint": f"{' · '.join(VIEWPORT_PRESETS)} 또는 390x844 처럼 폭x높이"})
        w, h = int(m.group(1)), int(m.group(2))
    state["viewport"] = [w, h]
    _write_web_state(state_f, state)
    return out({"action": "viewport", "viewport": [w, h],
                "summary": f"뷰포트 {w}x{h}",
                "next": "web shot  # 이 폭으로 찍습니다 (필요하면 web goto 로 다시 그리게 하세요)"})


def _looks_like_path(text: str) -> bool:
    """JSON·문장이 아니라 파일 경로처럼 보이나. 공백·따옴표·괄호가 없고 슬래시나 확장자가 있으면 경로로 본다."""
    t = text.strip()
    if not t or re.search(r"[\s{}\[\]\"<>]", t):
        return False
    try:
        json.loads(t)    # 1.5 · true 같은 JSON 값은 파일명이 아니라 본문이다
        return False
    except json.JSONDecodeError:
        pass
    return "/" in t or "\\" in t or bool(re.search(r"\.[A-Za-z0-9]{1,5}$", t))


def _web_route(args, state: dict, state_f: Path) -> int:
    """응답 바꿔치기 — 빈 목록·실패·지연을 서버를 건드리지 않고 연출한다."""
    rules = list(state.get("routes") or [])
    if args.clear:
        state["routes"] = []
        _write_web_state(state_f, state)
        return out({"action": "route", "routes": [],
                    "summary": f"바꿔치기 규칙 {len(rules)}개를 지웠습니다",
                    "next": "web goto  # 진짜 응답으로 다시 그립니다"})
    if not args.match:
        return out({"action": "route", "routes": rules,
                    "summary": f"규칙 {len(rules)}개",
                    "hint": "--match '**/api/items*' --status 200 --body empty.json 처럼 겁니다"})
    if args.status is None and not args.delay:
        return out({"ok": False, "code": "missing_argument",
                    "error": "--status 나 --delay 중 하나는 있어야 합니다"})
    if args.status is not None and not 100 <= args.status <= 599:
        return out({"ok": False, "code": "bad_status",
                    "error": f"--status 는 100~599 여야 합니다 ({args.status})"})
    if args.delay is not None and args.delay < 0:
        return out({"ok": False, "code": "bad_delay", "error": f"--delay 는 0 이상이어야 합니다 ({args.delay})"})
    body, ctype = "", "application/json"
    if args.body_text is not None:
        body = args.body_text   # 경로 오타와 구분되도록 인라인 본문은 이 옵션으로 명시한다
    elif args.body:
        bf = Path(args.body)
        if bf.is_file():
            body = bf.read_text(encoding="utf-8")
        elif _looks_like_path(args.body):
            # 오타 경로가 조용히 가짜 응답 본문이 되면 연출 결과가 통째로 틀어진다 (#711)
            return out({"ok": False, "code": "body_not_found",
                        "error": f"--body 파일이 없습니다: {args.body}",
                        "next": "경로를 확인한다. 글자 그대로 본문으로 쓰려면 --body-text 를 쓴다"})
        else:
            body = args.body   # 짧은 JSON 본문은 그대로 받는다: --body '[]'
    if body:
        try:
            json.loads(body)
        except json.JSONDecodeError:
            ctype = "text/plain; charset=utf-8"
    rule = {"match": args.match, "status": args.status, "body": body,
            "content_type": ctype, "delay_ms": args.delay or 0}
    rules = [r for r in rules if r.get("match") != args.match] + [rule]
    state["routes"] = rules
    _write_web_state(state_f, state)
    return out({"action": "route", "rule": {k: v for k, v in rule.items() if k != "body"},
                "body_bytes": len(body.encode("utf-8")), "routes": len(rules),
                "summary": f"{args.match} → {args.status or '지연 ' + str(args.delay) + 'ms'}",
                "next": "web goto --url <그 화면>  # 규칙은 이동할 때 걸린다. 이미 열린 화면은 다시 불러야 한다"})


def cmd_web(args) -> int:
    """웹 화면을 조작한다. 한 번에 한 동작 — agent가 화면을 보고 다음을 정한다."""
    _set_area("web", _root(args))
    # 비밀번호를 --text 에 적으면 세션 기록에 평문으로 남는다(#604) — --text-env 로 받는다
    secret_value = None
    if getattr(args, "text_env", None):
        if args.text_env not in os.environ:
            return out({"ok": False, "code": "env_not_set",
                        "error": f"환경변수 {args.text_env} 가 비어 있습니다",
                        "hint": f'{args.text_env}="..." 를 같은 명령 앞에 붙여 실행하세요'})
        secret_value = os.environ[args.text_env]
        args.text = secret_value
    elif getattr(args, "cred", None):
        # 저장된 로그인 정보를 입력한다 — 명령줄·기록에 값이 남지 않는다
        value, err = _cred_field(args.cred, getattr(args, "cred_field", None))
        if err:
            return out(err)
        secret_value = value
        args.text = value

    if args.action == "setup":
        return out(_web_setup(force=args.force))

    root = _root(args)
    state_f = _web_state_path(root)
    if args.action == "open":
        return _web_open(args, root, state_f)

    state = _read_web_state(state_f) if state_f.is_file() else {}
    # 뷰포트·규칙은 브라우저 없이도 적어 둘 수 있다 — 다음 open 에서 걸린다
    if args.action == "viewport":
        return _web_viewport(args, state, state_f)
    if args.action == "route":
        return _web_route(args, state, state_f)

    if not state.get("cdp"):
        return out({"ok": False, "code": "browser_not_open", "error": "열린 브라우저가 없습니다",
                    "next": f"web open --root {root} --url <주소>"})
    if args.action == "close" and state.get("pid"):
        # 연결부터 맺지 않는다 — 응답 없는 브라우저에서는 연결·close 가 모두 멈춘다 (#712)
        return _web_close(state, state_f)
    conn, err = _web_connect(state)
    if err:
        if err.get("code") == "browser_gone":
            # 죽은 브라우저 정보만 지운다. 뷰포트·규칙은 사람이 정한 것이라 남긴다
            for k in ("cdp", "pid"):
                state.pop(k, None)
            _write_web_state(state_f, state)
        return out(err)
    pw, browser, page = conn
    # 마지막 사용 시각 — 오래 방치된 브라우저와 지금 쓰는 브라우저를 가른다 (#825)
    state["last_used"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _write_web_state(state_f, state)

    try:
        nav_status = None
        if args.action == "close":
            # pid 를 모르는 옛 상태 파일 — 연결해서 닫는 수밖에 없다
            browser.close()
            state_f.unlink(missing_ok=True)
            return out({"action": "close", "summary": "브라우저를 닫았습니다"})

        if args.action == "goto":
            if not args.url:
                return out({"ok": False, "code": "url_required", "error": "--url 이 필요합니다"})
            resp = page.goto(args.url, wait_until="domcontentloaded", timeout=max(args.timeout, 30) * 1000)
            nav_status = resp.status if resp is not None else None
            _settle(page, state, args.timeout)

        elif args.action == "click":
            return out(_web_click(page, args, state))

        elif args.action == "find":
            return out(_web_find(page, args))

        elif args.action == "text":
            return out(_web_text(page, args))

        elif args.action == "type":
            if not (args.selector and args.text is not None):
                return out({"ok": False, "code": "missing_argument",
                            "error": "--selector 와 --text 가 필요합니다"})
            page.fill(args.selector, args.text, timeout=args.timeout * 1000)

        elif args.action == "shot":
            # Playwright 는 webp 로 못 찍는다(png·jpeg 만) — png 로 찍고 바꾼다.
            raw, explicit = _shot_target(root, args.out)
            if args.selector:
                # 한 요소만 — 시안 대조·요청서에서 부분만 필요할 때
                page.locator(args.selector).first.screenshot(path=str(raw))
            else:
                page.screenshot(path=str(raw), full_page=args.full)
            final = _finish_shot(raw, explicit, args)
            return out({"action": "shot", "file": str(final), "url": page.url,
                        "title": page.title(), "viewport": state.get("viewport"),
                        "routes": len(state.get("routes") or []),
                        "summary": f"화면을 찍었습니다: {final.name}",
                        "next": "이미지를 읽어 다음 조작을 정하세요"})

        elif args.action == "assert":
            checks = []
            if args.url:
                checks.append({"expect_url": args.url, "got": page.url,
                               "ok": args.url in page.url})
            if args.text:
                checks.append({"expect_text": args.text,
                               "ok": page.get_by_text(args.text).count() > 0})
            if args.selector:
                checks.append({"expect_selector": args.selector,
                               "ok": page.locator(args.selector).count() > 0})
            if not checks:
                return out({"ok": False, "code": "nothing_to_assert",
                            "error": "--url · --text · --selector 중 하나는 있어야 합니다"})
            passed = all(c["ok"] for c in checks)
            return out({"action": "assert", "checks": checks, "ok": passed, "url": page.url,
                        "code": "ok" if passed else "assert_failed",
                        "summary": "확인 통과" if passed else "확인 실패"})

        elif args.action == "console":
            # 듣는 게 아니라 **쌓인 것을 읽는다** (#625)
            try:
                logs = page.evaluate("window.__projectops_console || null")
            except Exception:
                logs = None
            if logs is None:
                return out({"ok": False, "code": "console_hook_missing",
                            "error": "이 페이지에는 콘솔 기록이 없습니다",
                            "hint": "훅을 지금 심었습니다. `web goto` 로 다시 들어가면 "
                                    "그때부터 로드 오류까지 모입니다", "url": page.url})
            errs = [l for l in logs if l.get("type") == "error"]
            return out({"action": "console", "logs": logs[-50:], "error_count": len(errs),
                        "total": len(logs), "url": page.url,
                        "summary": f"콘솔 {len(logs)}줄 (오류 {len(errs)}) — 로드 시점부터",
                        "next": ("오류가 있으면 화면이 멀쩡해도 통과가 아닙니다"
                                 if errs else None)})

        payload = {"action": args.action, "url": page.url, "title": page.title(),
                   "summary": f"{args.action} 완료 — {page.url}",
                   "next": "web text  # 결과 화면의 글자를 읽는다"}
        if args.action == "goto":
            # 404·500 페이지로 가도 이동 자체는 성공이다 — 상태코드를 함께 줘서 호출한 쪽이 판단하게 한다 (#711)
            payload["status"] = nav_status
            if nav_status is not None and nav_status >= 400:
                payload["summary"] += f" (HTTP {nav_status} — 오류 응답)"
                payload["http_error"] = True
        return out(payload)
    except Exception as e:
        # 예외 문구에 입력값이 섞여 나올 수 있다 — 비밀값이면 가리고 내보낸다
        msg = str(e)
        if secret_value:
            msg = msg.replace(secret_value, "***")
        return out({"ok": False, "code": "web_action_failed", "action": args.action,
                    "error": msg[:400], "url": page.url if page else None,
                    "next": "web shot  # 지금 화면이 무엇인지 먼저 봅니다"})
    finally:
        # 연결만 끊는다. browser.close()를 부르면 다음 호출이 붙을 곳이 없어진다.
        pw.stop()


# =========================================================================
# http — 단건 요청. 시나리오 판정은 부르는 쪽(agent-test)이 한다
# =========================================================================

def cmd_http(args) -> int:
    """HTTP 한 건. 경로만 주면 access 의 base_url 에 붙인다 — 판정은 부르는 쪽이 한다."""
    _set_area("server", _root(args))
    root = _root(args)
    url = args.url
    if not re.match(r"https?://", url):
        # 경로만 주면 적어 둔 base_url 에 붙인다. 코드에서 짐작하지 않는다.
        bu = load_access(root).get("base_url")
        base = bu.get("url") if isinstance(bu, dict) else bu
        if not base:
            return out({"ok": False, "code": "base_url_required",
                        "error": f"'{url}' 는 전체 주소가 아니고, 적어 둔 base_url 도 없습니다",
                        "next": "access set --key base_url --json '{\"url\":\"http://...\"}'"})
        url = base.rstrip("/") + "/" + url.lstrip("/")
        _use_access(root, "base_url")

    headers = {"Accept": "application/json"}
    cred, err = _load_cred(getattr(args, "cred", None))
    if err:
        return out(err)
    if cred:
        # 저장된 토큰·계정으로 Authorization 을 만든다 (직접 준 --header 가 있으면 그것이 이긴다)
        if cred.get("token"):
            headers["Authorization"] = f"Bearer {cred['token']}"
        elif cred.get("username") and cred.get("password"):
            import base64
            headers["Authorization"] = "Basic " + base64.b64encode(
                f"{cred['username']}:{cred['password']}".encode()).decode()
    for h in args.header or []:
        if ":" not in h:
            return out({"ok": False, "code": "bad_header",
                        "error": f"헤더 '{h}' 는 '이름: 값' 형식이어야 합니다"})
        k, v = h.split(":", 1)
        headers[k.strip()] = v.strip()
    data = None
    if args.data is not None:
        if args.data.startswith("@"):
            data_f = Path(args.data[1:])
            if not data_f.is_file():
                return out({"ok": False, "code": "data_file_not_found",
                            "error": f"--data 파일이 없습니다: {data_f}",
                            "next": "@ 뒤 경로를 확인한다 (본문 자체가 @ 로 시작하면 파일에 담아 @파일 로 넘긴다)"})
            text = data_f.read_text(encoding="utf-8")
        else:
            text = args.data
        data = text.encode("utf-8")
        try:
            json.loads(text)
            headers.setdefault("Content-Type", "application/json")
        except json.JSONDecodeError:
            pass

    r = http_request(args.method.upper(), url, headers, data, timeout=args.timeout)
    raw = r.pop("raw", None)
    if not r["ok"]:
        return out(r)
    saved = None
    if args.save:
        run_dir = os.environ.get("RUN_DIR")
        target = Path(args.save) if (os.sep in args.save or "/" in args.save or not run_dir) \
            else Path(run_dir) / "http" / args.save
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw or b"")
        saved = str(target)
    ok = args.expect_status is None or r["status"] == args.expect_status
    return out({
        "ok": ok, "code": "ok" if ok else "unexpected_status",
        "method": args.method.upper(), "url": url, "status": r["status"],
        # 요청 헤더 값은 되돌려 주지 않는다 — Authorization 이 기록에 남는다
        "request_headers": sorted(headers),
        "headers": r["headers"], "json": r["json"], "text": r["text"],
        "elapsed_ms": r["elapsed_ms"], "saved": saved,
        "summary": f"{args.method.upper()} {url} → {r['status']} ({r['elapsed_ms']}ms)",
    })


# =========================================================================
# cred · ssh — 이름 붙은 자격증명을 저장해 두고 다음 실행에서 다시 쓴다
# =========================================================================
#
# pro-ssh · pro-github 가 config.json 에 서버·PAT 를 두고 쓰는 것과 같은 방식이다.
# 비밀은 사용자 홈의 config.json(launch.credentials) 한 곳에만 두고, access.json 에는 이름만 적는다.

def _load_cred(name: str | None):
    """(자격증명, None) 또는 (None, 오류 JSON 을 낼 payload)."""
    if not name:
        return None, None
    try:
        return credentials.resolve(name), None
    except credentials.CredError as e:
        return None, {"ok": False, "code": e.code, "error": e.message,
                      "next": "cred list  # 저장된 자격증명과 use_when 을 본다"}


def _cred_from_profile(args, saved) -> str | None:
    """--cred 가 없으면 access 기록에 적힌 cred 이름을 쓴다."""
    if getattr(args, "cred", None):
        return args.cred
    return saved.get("cred") if isinstance(saved, dict) else None


def _cred_field(name: str, field: str | None) -> tuple[str | None, dict | None]:
    """저장된 자격증명에서 입력할 값 하나를 꺼낸다 (기본 password). (값, None) 또는 (None, 오류)."""
    cred, err = _load_cred(name)
    if err:
        return None, err
    f = field or "password"
    v = cred.get(f)
    if v in (None, ""):
        keys = sorted(k for k, x in cred.items() if x not in (None, "") and k not in ("name", "kind"))
        return None, {"ok": False, "code": "cred_field_missing",
                      "error": f"'{name}' 에 '{f}' 값이 없습니다", "fields": keys,
                      "next": f"cred set --name {name} --json '{{\"{f}\": \"...\"}}'  # 또는 --cred-field 로 다른 필드를 고른다"}
    return str(v), None


def _prune_old_ssh(plan: list) -> dict:
    """가져온 서버를 옛 `ssh` 섹션에서 지운다. 값이 cred 에 실제로 있는 것만, 지우기 전에 백업한다.

    참조(`ssh_server`)로 만든 것은 옛 섹션이 아직 필요하므로 지우지 않는다.
    """
    import shutil
    moved = {p["name"] for p in plan if p["status"] in ("imported", "exists")
             and not p.get("_raw", {}).get("ssh_server")}
    data = credentials.cfg.load() or {}
    creds = credentials.load_all()
    servers = data.get("ssh")
    key = "instances" if isinstance(servers, dict) else None
    items = (servers.get("instances") if key else servers) or []
    safe = {n for n in moved if creds.get(n, {}).get("host") and not creds[n].get("ssh_server")}
    keep = [s for s in items if s.get("name") not in safe]
    removed = [s.get("name") for s in items if s.get("name") in safe]
    if not removed:
        return {"removed": [], "backup": None}
    path = credentials.cfg.config_path()
    backup = path.with_name(path.name + ".bak-ssh-prune")
    shutil.copy2(path, backup)
    os.chmod(backup, 0o600)
    if key:
        servers["instances"] = keep
        data["ssh"] = servers
    elif keep:
        data["ssh"] = keep
    else:
        data.pop("ssh", None)
    credentials._write_config(data)
    return {"removed": removed, "backup": str(backup)}


def _cred_import_ssh(args) -> int:
    """옛 pro-ssh `ssh` 섹션 서버를 launch 자격증명으로 옮긴다.

    **서버 정보는 cred 한 곳에 둔다** — 기본은 host·user·password 값까지 복사한다. 옛 섹션을 계속 쓰고
    싶으면 `--ref`(참조만 만든다, 비밀번호는 옛 섹션에 남는다). `--prune` 은 가져온 서버를 옛 섹션에서
    지운다(config 를 먼저 백업한다). 응답에는 비밀 값을 싣지 않는다.
    """
    existing = credentials.load_all()
    plan = []
    for srv in credentials.ssh_servers():
        name = srv.get("name")
        if not name or not credentials.NAME_RE.match(str(name)):
            plan.append({"name": name, "status": "skipped", "reason": "이름이 없거나 형식이 맞지 않음"})
            continue
        if name in existing:
            plan.append({"name": name, "status": "exists", "reason": "이미 같은 이름의 자격증명이 있음"})
            continue
        if getattr(args, "ref", False):
            fields = {"kind": "ssh", "ssh_server": name}
        else:
            fields = {"kind": "ssh", **{k: srv[k] for k in ("host", "port", "user", "auth", "key_path", "password")
                                        if srv.get(k) not in (None, "")}}
        plan.append({"name": name, "status": "would_import" if args.dry_run else "imported",
                     "fields": credentials.public_view(fields), "_raw": fields})
    if not args.dry_run:
        try:
            for p in plan:
                if p["status"] == "imported":
                    credentials.save_credential(p["name"], p["_raw"])
        except credentials.CredError as e:
            return out({"ok": False, "code": e.code, "error": e.message})
    pruned = None
    if getattr(args, "prune", False) and not args.dry_run:
        pruned = _prune_old_ssh(plan)
    for p in plan:
        p.pop("_raw", None)
    n = sum(1 for p in plan if p["status"] in ("would_import", "imported"))
    return out({"ok": True, "code": "ok", "dry_run": bool(args.dry_run), "servers": plan, "count": n,
                "pruned": pruned,
                "summary": (f"{n}개 가져올 수 있음 (dry-run, 아무것도 쓰지 않음)" if args.dry_run
                            else f"{n}개 가져옴") if plan else "옛 ssh 섹션에 서버가 없습니다",
                "next": ("실제로 옮기려면 --dry-run 을 빼고 다시 부른다. 그다음 cred set --name 이름 --json "
                         "'{\"use_when\":\"...\",\"scope\":\"...\"}' 로 허용 범위를 채운다" if args.dry_run and n
                         else "use_when · scope 를 cred set 으로 채운다. 옛 ssh 섹션은 지우지 않았다")})


def cmd_cred(args) -> int:
    """자격증명을 저장하고 꺼낸다. 값은 config.json 에만 남고 목록·조회에서는 가려진다."""
    if args.action == "list":
        allc = credentials.load_all()
        items = []
        for n, e in sorted(allc.items()):
            items.append({"name": n, "kind": e.get("kind"), "scope": e.get("scope"),
                          "use_when": e.get("use_when"), "has_secret": bool(credentials.secret_values(e))
                          or bool(e.get("ssh_server"))})
        return out({"credentials": items, "count": len(items),
                    "summary": (f"{len(items)}개 저장됨" if items else "저장된 자격증명이 없습니다"),
                    "next": ("use_when · scope 가 지금 하려는 일에 맞는 것만 쓴다. cred show --name 이름"
                             if items else "cred set --name 이름 --json '{\"kind\":\"ssh\",...}'")})

    if args.action == "import-ssh":
        return _cred_import_ssh(args)

    try:
        if args.action == "show":
            entry = credentials.resolve(args.name) if args.name else None
            if not entry:
                return out({"ok": False, "code": "name_required", "error": "--name 이 필요합니다"})
            return out({"name": args.name, "credential": credentials.public_view(entry, args.reveal),
                        "summary": f"{args.name} ({entry.get('kind') or 'kind 없음'})",
                        "notes": "값은 가려서 보여 준다. 실행에는 --cred 로 넘기면 된다" if not args.reveal else None})

        if args.action == "set":
            name = credentials.validate_name(args.name)
            try:
                fields = json.loads(args.json_value) if args.json_value else None
            except json.JSONDecodeError as e:
                return out({"ok": False, "code": "bad_json", "error": f"--json 이 올바르지 않습니다: {e}"})
            if args.prompt:
                # 이 맥의 sudo 비밀번호(#784). 채팅이나 파이프로 받지 않는다 — 세션 기록에 평문이 남기 때문이다.
                # 사용자가 터미널에서 직접 치게 하고(입력은 화면에 보이지 않는다) 그 값만 저장한다.
                if not sys.stdin.isatty():
                    return out({"ok": False, "code": "no_tty",
                                "error": "비밀번호는 터미널에서 직접 입력해야 합니다 (채팅·파이프로는 받지 않습니다)",
                                "next": f"사용자가 터미널에서: launch_cli.py cred set --name {name} --prompt"})
                import getpass
                pw = getpass.getpass("이 맥의 sudo 비밀번호: ")
                if not pw:
                    return out({"ok": False, "code": "empty_password", "error": "비밀번호가 비었습니다"})
                fields = {"kind": "local", "use_when": "이 맥에서 관리자 권한(sudo)이 필요할 때",
                          **(fields or {}), "sudo_password": pw}
            f = credentials.save_credential(name, fields or {}, replace=args.replace)
            saved = credentials.load_all().get(name, {})
            missing = [k for k in ("kind", "use_when") if not saved.get(k)]
            return out({"file": str(f), "name": name, "credential": credentials.public_view(saved),
                        "summary": f"{name} 저장 완료",
                        "hint": (f"{'·'.join(missing)} 를 채워 두면 agent 가 언제 써도 되는지 판단할 수 있다"
                                 if missing else None)})

        if args.action == "unset":
            ok = credentials.delete_credential(credentials.validate_name(args.name))
            return out({"name": args.name, "ok": ok, "code": "ok" if ok else "not_found",
                        "summary": f"{args.name} 지움" if ok else f"{args.name} 가 없습니다"})
    except credentials.CredError as e:
        return out({"ok": False, "code": e.code, "error": e.message})
    return out({"ok": False, "code": "unknown_action", "error": args.action})


def cmd_local(args) -> int:
    """저장된 자격증명으로 이 맥에서 sudo 명령을 실행한다 (#784).

    비밀번호는 `sudo -S` 의 표준입력으로만 넘긴다 — 명령줄(ps)·응답·로그에 남지 않는다.
    kind 가 local 인 자격증명만 쓴다: 서버 ssh 비밀번호로 이 맥에 sudo 를 시도하면 안 된다.
    """
    if not args.cred:
        return out({"ok": False, "code": "cred_required", "error": "--cred 가 필요합니다",
                    "next": "cred list  # kind 가 local 인 것을 고른다. 없으면 사용자가 터미널에서 cred set --name 이름 --prompt"})
    cred, err = _load_cred(args.cred)
    if err:
        return out(err)
    if cred.get("kind") != "local":
        return out({"ok": False, "code": "cred_not_local",
                    "error": f"'{args.cred}' 는 이 맥용(kind: local)이 아닙니다 — 서버 비밀번호로 이 맥에 sudo 를 쓰지 않습니다"})
    password = cred.get("sudo_password")
    if not password:
        return out({"ok": False, "code": "sudo_password_missing", "error": f"'{args.cred}' 에 sudo_password 가 없습니다",
                    "next": f"사용자가 터미널에서: launch_cli.py cred set --name {args.cred} --prompt"})
    command = list(args.command or [])
    if not command:
        return out({"ok": False, "code": "command_required", "error": "실행할 명령이 없습니다",
                    "next": f"local sudo --cred {args.cred} -- <명령> [인자...]"})
    if not shutil.which("sudo"):
        return out({"ok": False, "code": "sudo_missing", "error": "sudo 를 찾을 수 없습니다"})
    try:
        r = subprocess.run(["sudo", "-S", "-p", "", *command], input=str(password) + "\n",
                           capture_output=True, text=True, timeout=args.timeout)
    except subprocess.TimeoutExpired:
        return out({"ok": False, "code": "sudo_timeout", "error": f"응답 없음 ({args.timeout}초)"})
    stdout = credentials.mask(r.stdout, cred)
    stderr = credentials.mask(r.stderr, cred)
    ok = r.returncode == 0
    return out({"ok": ok, "code": "ok" if ok else "sudo_failed", "exit_code": r.returncode,
                "stdout": stdout[:args.max_output], "stderr": stderr.strip()[:1000] or None,
                "truncated": len(stdout) > args.max_output,
                "summary": f"{args.cred}: sudo {command[0]} " + ("완료" if ok else f"실패 (종료코드 {r.returncode})"),
                "next": None if ok else "stderr 를 보고 명령을 고친다. 비밀번호가 틀렸으면 사용자가 cred set --name 이름 --prompt 로 다시 저장"})


def _server_prefix(name: str) -> str:
    return f"server.{knowledge.norm_key(name)}."


# 서버 사실 탐침: 셸이 POSIX 이고 uname 이 있을 때만 의미가 있다 (Windows 는 조용히 건너뛴다).
_PROBE = ("uname -s 2>/dev/null; "
          "[ -x /var/packages/ContainerManager/target/usr/bin/docker ] && echo SYNO_DOCKER; true")
_SYNO_DOCKER = "/var/packages/ContainerManager/target/usr/bin/docker"
_KNOWN_OS = ("Linux", "Darwin", "FreeBSD")


def _record_server_facts(name: str, base_cmd: list[str], env: dict) -> None:
    """처음 접속 성공 때 확인된 사실(OS · 시놀로지 docker 절대경로)만 이 컴퓨터 범위에 남긴다.

    이미 OS 를 알고 있으면 추가 접속을 하지 않는다. 호스트·계정·비밀은 how 에 쓰지 않는다.
    어떤 실패도 본 명령 결과를 망치지 않는다.
    """
    try:
        if not knowledge.base_dir().is_absolute():
            return
        prefix = _server_prefix(name)
        if any(e["key"] == prefix + "os" for e in knowledge.load(knowledge.store_path("machine", Path(".")))
               if e["area"] == "server"):
            return
        r = subprocess.run(base_cmd + [_PROBE], env=env, capture_output=True, text=True, timeout=15)
        lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
        if r.returncode != 0 or not lines or lines[0] not in _KNOWN_OS:
            return
        knowledge.auto_record("server", prefix + "os", f"OS {lines[0]} (uname -s 로 확인)")
        if "SYNO_DOCKER" in lines:
            knowledge.auto_record("server", prefix + "docker",
                                  f"docker 는 PATH 에 없다 — 절대경로 {_SYNO_DOCKER} 로 부른다 "
                                  "(컨테이너 안 curl 이 없으면 wget)")
    except Exception:   # noqa: BLE001 — 기억은 보조다
        pass


def cmd_ssh(args) -> int:
    """원격 명령을 실행한다 — 저장된 서버(--cred)나, 저장 없이 직접 넘긴 접속 정보(--host …)로.

    --sudo 면 원격에서 `SUDO <명령>` 을 쓸 수 있다 (비밀번호가 필요한 sudo, PATH 에 /usr/local/bin 포함).
    직접 넘긴 값(--host · --port · --user · --password · --password-env · --key-path)은 저장하지 않고,
    --cred 와 함께 주면 그 값이 저장된 값보다 우선한다. 출력의 비밀번호는 가린다.
    """
    # 서버 기억은 이 서버 것만 싣는다 — key 는 server.<자격증명 이름>.* (기억 원칙 1). 저장 없는 접속은 기억하지 않는다
    if args.cred:
        _set_area("server", _root(args), key_prefix=_server_prefix(args.cred))
    cred, err = _load_cred(args.cred)
    if err:
        return out(err)
    adhoc = {k: v for k, v in (("host", args.host), ("port", args.port), ("user", args.user),
                                ("key_path", args.key_path)) if v not in (None, "")}
    if args.password_env:
        if args.password_env not in os.environ:
            return out({"ok": False, "code": "env_not_set",
                        "error": f"환경변수 {args.password_env} 가 비어 있습니다"})
        adhoc["password"] = os.environ[args.password_env]
    elif args.password:
        adhoc["password"] = args.password
    if adhoc:
        # 직접 넘긴 비밀번호면 저장된 key_path 가, 직접 넘긴 key 면 저장된 password 가 끼어들지 않게 한다
        base = dict(cred or {})
        if "password" in adhoc:
            base.pop("key_path", None)
        if "key_path" in adhoc:
            base.pop("password", None)
        cred = {**base, **adhoc, "name": (cred or {}).get("name") or "(저장 안 함)"}
    if not cred:
        return out({"ok": False, "code": "cred_required",
                    "error": "저장된 서버(--cred) 나 접속 정보(--host --user …)가 필요합니다",
                    "next": "cred list  # 또는 ssh --host <호스트> --port <포트> --user <계정> "
                            "--password-env <변수> | --key-path <키 파일> --command '…'"})
    if not args.command:
        return out({"ok": False, "code": "command_required", "error": "--command 가 필요합니다"})
    host, user = cred.get("host"), cred.get("user")
    label = args.cred or host or "(저장 안 함)"
    if not host:
        return out({"ok": False, "code": "host_missing",
                    "error": f"'{label}' 에 host 가 없습니다 (--host 를 주거나 cred set 으로 host·user 를 적는다)"})
    password = cred.get("password")
    key_path = cred.get("key_path")
    dest = f"{user}@{host}" if user else host
    ssh = ["ssh", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=20"]
    if cred.get("port"):
        ssh += ["-p", str(cred["port"])]
    env = dict(os.environ)
    if key_path:
        ssh += ["-i", os.path.expanduser(str(key_path)), "-o", "BatchMode=yes"]
        argv_prefix = []
    elif password:
        if not shutil.which("sshpass"):
            return out({"ok": False, "code": "sshpass_missing", "error": "비밀번호 접속에는 sshpass 가 필요합니다",
                        "install": "brew install hudochenkov/sshpass/sshpass  (또는 key_path 로 키 접속)"})
        env["SSHPASS"] = str(password)
        argv_prefix = ["sshpass", "-e"]
    else:
        argv_prefix = []                              # 에이전트 키·기본 키에 맡긴다

    remote = args.command
    stdin = None
    if args.sudo:
        if not password:
            return out({"ok": False, "code": "sudo_password_missing",
                        "error": "--sudo 에는 저장된 password 가 필요합니다"})
        # 비밀번호는 표준입력으로만 넘긴다 — 원격 명령줄(ps)에 남지 않는다
        remote = ('export PATH=$PATH:/usr/local/bin; IFS= read -r PW; '
                  'SUDO() { echo "$PW" | sudo -S -p "" "$@"; }; ' + args.command)
        stdin = str(password) + "\n"
    try:
        r = subprocess.run(argv_prefix + ssh + [dest, remote], input=stdin, env=env,
                           capture_output=True, text=True, timeout=args.timeout)
    except subprocess.TimeoutExpired:
        return out({"ok": False, "code": "ssh_timeout", "error": f"응답 없음 ({args.timeout}초)"})
    stdout = credentials.mask(r.stdout, cred)
    stderr = credentials.mask(r.stderr, cred)
    ok = r.returncode == 0
    if ok and args.cred and not adhoc:
        _record_server_facts(args.cred, argv_prefix + ssh + [dest], env)
    hint = ("stderr 를 보고 명령·접속 정보를 고친다" + (" (cred show --name)" if args.cred else ""))
    if ok and adhoc and not args.cred:
        hint = ("자주 쓰는 서버면 cred set --name <이름> --json "
                "'{\"kind\":\"ssh\",\"host\":…,\"port\":…,\"user\":…,\"use_when\":…}' 로 저장해 두면 다음부터 이름만 쓴다")
    return out({"ok": ok, "code": "ok" if ok else "ssh_failed", "exit_code": r.returncode,
                "stdout": stdout[:args.max_output], "stderr": stderr.strip()[:1000] or None,
                "truncated": len(stdout) > args.max_output,
                "summary": f"{label}: " + ("실행 완료" if ok else f"실패 (종료코드 {r.returncode})"),
                "next": hint if (not ok or adhoc) else None})


# =========================================================================
# 서버에 붙는 법 — access · db · logs (#589)
# =========================================================================
#
# **접속 방법은 agent가 정한다.** 설정이 사는 곳도 붙는 길도 제각각이다.
# 여기서는 적어 둔 것을 받은 대로 실행만 한다.

_DB_CLIENTS = {"postgres": "psql", "postgresql": "psql", "mysql": "mysql", "mariadb": "mysql"}


def _db_argv(engine: str, db: dict, sql: str) -> tuple[list[str], dict]:
    """엔진에 맞는 명령과 환경변수. 비밀번호는 argv가 아니라 env로 — argv는 다른 프로세스에서 보인다."""
    exe = _DB_CLIENTS[engine]
    env = {}
    if exe == "psql":
        argv = [exe, "-tAF", "\t", "-c", sql]
        env = {"PGHOST": db.get("host") or "", "PGPORT": str(db.get("port") or ""),
               "PGDATABASE": db.get("name") or "", "PGUSER": db.get("user") or "",
               "PGPASSWORD": db.get("password") or ""}
    else:
        argv = [exe, "-N", "-B"]
        if db.get("host"):
            argv += ["-h", db["host"]]
        if db.get("port"):
            argv += ["-P", str(db["port"])]
        if db.get("user"):
            argv += ["-u", db["user"]]
        if db.get("name"):
            argv += [db["name"]]
        argv += ["-e", sql]
        if db.get("password"):
            env = {"MYSQL_PWD": db["password"]}
    return argv, env


def _shq(s: str) -> str:
    """원격 셸에 넘길 값을 감싼다."""
    return "'" + str(s).replace("'", """'"'"'""") + "'"


def _db_rows(text: str) -> list[list[str]]:
    """탭으로 나뉜 출력을 행 목록으로. 판정은 agent가 한다."""
    return [line.split("\t") for line in (text or "").splitlines() if line.strip()][:200]


def cmd_access(args) -> int:
    """이 프로젝트에 어떻게 붙는지를 적어 두고 꺼내 쓴다. 비밀번호는 **값을 적지 않는다.**"""
    root = _root(args)
    _home(root)
    data = load_access(root)

    if args.action == "show":
        status = {k: v for k, v in load_status(root).items() if k in data}
        doubt = sorted(k for k, v in status.items() if needs_verify(v))
        return out({"file": str(access_path(root)), "access": data,
                    "status": status or None,
                    "verify": doubt or None,
                    "summary": (f"{', '.join(data)} 기록됨" if data else "아직 기록이 없습니다"),
                    "next": (None if data else
                             "코드를 읽어 붙는 법을 알아낸 뒤 access set --key db --json '{...}'")})

    if args.action == "set":
        if not args.key:
            return out({"ok": False, "code": "key_required",
                        "error": "--key 가 필요합니다 (db · logs · base_url 등)"})
        try:
            value = json.loads(args.json_value) if args.json_value else None
        except json.JSONDecodeError as e:
            return out({"ok": False, "code": "bad_json", "error": f"--json 이 올바르지 않습니다: {e}"})
        if value is None:
            return out({"ok": False, "code": "value_required", "error": "--json 이 필요합니다"})
        leaked = find_secrets(json.dumps(value, ensure_ascii=False))
        if leaked and not args.allow_secret:
            return out({"ok": False, "code": "secret_in_value",
                        "error": "비밀값으로 보이는 것이 들어 있습니다", "found": leaked[:5],
                        "hint": ('access 에는 비밀을 적지 않는다. 값은 cred set --name 이름 --json \'{...}\' 로 저장하고 '
                                 'access 에는 {"cred":"이름"} 만 적는다 (환경변수로 받으려면 {"password_env":"APP_DB_PASSWORD"})')})
        data[args.key] = value
        f = save_access(root, data)
        reset_status(root, args.key)   # 방법이 바뀌었으면 옛 성적은 의미가 없다
        return out({"file": str(f), "key": args.key, "access": data,
                    "summary": f"{args.key} 기록 완료"})

    if args.action == "unset":
        if not args.key:
            # set 과 같게 --key 를 요구한다. 없으면 "None 가 없습니다" 로 성공 처리돼 오해를 부른다 (#713)
            return out({"ok": False, "code": "key_required",
                        "error": "--key 가 필요합니다 (db · logs · base_url 등)"})
        if args.key in data:
            del data[args.key]
            save_access(root, data)
            reset_status(root, args.key)
            return out({"key": args.key, "access": data, "summary": f"{args.key} 지움"})
        return out({"key": args.key, "access": data, "code": "not_found",
                    "summary": f"{args.key} 가 없습니다"})
    return out({"ok": False, "code": "unknown_action", "error": args.action})


def _proc_result(r, via: str, engine: str | None = None) -> int:
    return out({
        "ok": r.returncode == 0, "via": via, "engine": engine,
        "code": "ok" if r.returncode == 0 else "db_query_failed",
        "rows": _db_rows(r.stdout), "raw": r.stdout[:4000],
        "error": (r.stderr or "").strip()[:500] or None,
        "summary": "실행 완료" if r.returncode == 0 else "실행 실패",
        "hint": ("비밀번호 없이 붙는 키가 있어야 합니다(BatchMode)"
                 if (via == "ssh" and r.returncode != 0) else None),
    })


def cmd_db(args) -> int:
    """SQL 한 줄을 실행한다. **어떻게 붙을지는 호출하는 쪽이 정한다.**

      --command  임의 명령 (docker exec 등). 가장 자유롭다
      --via ssh  원격에 들어가 그 안에서 클라이언트를 실행한다
      (기본)     여기서 직접 붙는다
    """
    _set_area("server", _root(args))
    sql = args.sql
    if not sql:
        return out({"ok": False, "code": "sql_required", "error": "--sql 이 필요합니다"})

    cred_env: dict = {}
    cred_entry = None
    # 적어 둔 접근 방법을 쓴다. 인자로 직접 준 값이 언제나 이긴다 — 기록이 낡았을 때의 탈출구.
    if args.profile:
        root = _root(args)
        _home(root)
        saved = load_access(root).get(args.profile)
        if not saved:
            return out({"ok": False, "code": "profile_not_found",
                        "error": f"'{args.profile}' 기록이 없습니다",
                        "next": f"access show --root {args.root}"})
        _use_access(root, args.profile)
        if isinstance(saved, dict):
            for k in ("engine", "host", "port", "db", "user", "password",
                      "command", "ssh_host", "ssh_user", "ssh_port"):
                if getattr(args, k, None) in (None, "") and saved.get(k) is not None:
                    setattr(args, k, saved[k])
            if saved.get("how") in ("ssh", "direct") and args.via == "direct":
                args.via = saved["how"]
            if saved.get("append_sql"):
                args.append_sql = True
            cred_name = _cred_from_profile(args, saved)
            if cred_name and not getattr(args, "cred", None):
                args.cred = cred_name
            env_key = saved.get("password_env")
            if env_key and not args.password:
                args.password = os.environ.get(env_key)
                if not args.password:
                    return out({"ok": False, "code": "password_env_empty",
                                "error": f"환경변수 {env_key} 가 비어 있습니다",
                                "hint": f"{env_key}=... 를 주고 다시 부르세요"})

    if getattr(args, "cred", None):
        cred_entry, err = _load_cred(args.cred)
        if err:
            return out(err)
        # 저장된 값은 비어 있는 인자만 채운다 — 직접 준 인자가 이긴다
        for src, dst in (("host", "host"), ("port", "port"), ("db", "db"), ("user", "user"),
                         ("password", "password"), ("engine", "engine")):
            if getattr(args, dst, None) in (None, "") and cred_entry.get(src) not in (None, ""):
                setattr(args, dst, cred_entry[src])
        cred_env = credentials.env_for(cred_entry)

    try:
        if args.command:
            argv = (["bash", "-lc", f"{args.command} {_shq(sql)}"] if args.append_sql
                    else ["bash", "-lc", args.command])
            stdin = None if args.append_sql else sql
            r = subprocess.run(argv, input=stdin, capture_output=True, text=True,
                               timeout=args.timeout, env=dict(os.environ, **cred_env))
            return _proc_result(r, "command")

        engine = (args.engine or "").lower()
        if engine not in _DB_CLIENTS:
            return out({"ok": False, "code": "unsupported_engine",
                        "error": f"engine '{args.engine}' 은 다루지 않습니다",
                        "supported": sorted(set(_DB_CLIENTS)),
                        "hint": "--command 로 직접 실행할 명령을 주면 어떤 DB든 됩니다"})
        db = {"host": args.host, "port": args.port, "name": args.db, "user": args.user,
              "password": args.password or os.environ.get("DB_PASSWORD")}
        argv, env = _db_argv(engine, db, sql)

        if args.via == "ssh":
            if not args.ssh_host:
                return out({"ok": False, "code": "ssh_host_required",
                            "error": "--ssh-host 가 필요합니다"})
            remote = " ".join(f"{k}={_shq(v)}" for k, v in env.items() if v)
            remote += " " + " ".join(_shq(a) for a in argv)
            dest = f"{args.ssh_user}@{args.ssh_host}" if args.ssh_user else args.ssh_host
            ssh = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
            if args.ssh_port:
                ssh += ["-p", str(args.ssh_port)]
            r = subprocess.run(ssh + [dest, remote], capture_output=True, text=True,
                               timeout=args.timeout)
            return _proc_result(r, "ssh", engine)

        exe = shutil.which(argv[0])
        if not exe:
            return out({"ok": False, "code": "client_missing",
                        "error": f"{argv[0]} 가 없습니다",
                        "install": ("brew install libpq" if argv[0] == "psql"
                                    else "brew install mysql-client"),
                        "hint": "--via ssh 로 서버 안에서 실행하거나 --command 로 직접 명령을 주세요"})
        r = subprocess.run([exe] + argv[1:], env=dict(os.environ, **env),
                           capture_output=True, text=True, timeout=args.timeout)
        return _proc_result(r, "direct", engine)
    except subprocess.TimeoutExpired:
        return out({"ok": False, "code": "db_timeout", "error": f"응답 없음 ({args.timeout}초)"})


def cmd_logs(args) -> int:
    """서버 로그를 본다. **보는 방법은 적어 둔 것을 쓴다** — 맞히려 들지 않는다."""
    _set_area("server", _root(args))
    root = _root(args)
    _home(root)
    command = args.command
    saved = None
    if not command:
        saved = load_access(root).get(args.profile or "logs")
        command = saved.get("command") if isinstance(saved, dict) else saved
        if command:
            _use_access(root, args.profile or "logs")
    cred, err = _load_cred(_cred_from_profile(args, saved))
    if err:
        return out(err)
    cred_env = credentials.env_for(cred) if cred else {}
    if not command:
        return out({"ok": False, "code": "no_log_command",
                    "error": "로그를 어떻게 보는지 모릅니다",
                    "hint": ('코드를 읽어 알아낸 뒤 적어 두세요. 예: '
                             'access set --key logs --json \'{"command":"ssh u@h \\"docker logs --tail 200 app\\""}\'')})
    # tail·grep 은 파이프로 잇지 않고 파이썬에서 건다 (#704). 파이프 끝 종료코드만 보면
    # 앞 명령의 실패(없는 명령·ssh 접속 거부)가 가려져 "로그 0줄 성공"으로 보고된다.
    try:
        r = subprocess.run(["bash", "-lc", command], capture_output=True, text=True,
                           timeout=args.timeout, env=dict(os.environ, **cred_env))
    except subprocess.TimeoutExpired:
        return out({"ok": False, "code": "logs_timeout", "error": f"응답 없음 ({args.timeout}초)"})
    if cred:                                  # 서버가 비밀번호를 되풀이해 찍어도 기록에 남지 않게
        r.stdout = credentials.mask(r.stdout, cred)
        r.stderr = credentials.mask(r.stderr, cred)
    err = (r.stderr or "").strip()
    # 저장된 명령 안에 grep 이 있으면 매치 0건이 종료코드 1 이다 — 출력·오류가 모두 비면 성공으로 본다
    failed = r.returncode != 0 and not (r.returncode == 1 and not err and not (r.stdout or "").strip())
    if failed:
        resp = {"ok": False, "code": "logs_failed", "exit_code": r.returncode,
                "lines": [], "error": err[:500] or f"종료코드 {r.returncode}",
                "summary": f"로그 명령 실패 (종료코드 {r.returncode}) — 로그가 없는 것이 아니다",
                "next": "error 를 보고 접속 방법·명령을 고친다 (access show --key logs)"}
        try:   # 같은 오류를 전에 풀어 둔 기록(pro-note)이 있으면 싣는다 — 없으면 필드가 생기지 않는다 (#840)
            from common.notes import attach_note_hits
            attach_note_hits(resp, err, project_root=_root(args))
        except Exception:   # noqa: BLE001 — 기록 검색이 오류 보고를 막으면 안 된다
            pass
        return out(resp)
    lines = (r.stdout or "").splitlines()
    if args.grep:
        try:
            pat = re.compile(args.grep, re.IGNORECASE)
        except re.error:
            pat = re.compile(re.escape(args.grep), re.IGNORECASE)   # 정규식이 아니면 글자 그대로
        lines = [l for l in lines if pat.search(l)]
    if args.tail:
        lines = lines[-int(args.tail):]
    return out({"ok": True, "code": "ok", "lines": lines,
                "error": err[:500] or None, "summary": f"{len(lines)}줄"})


# =========================================================================
# render — 렌더 명령을 돌리고, 나온 그림을 모으고, 흔적을 검사한다 (#632)
# =========================================================================
#
# 렌더 코드는 agent 가 references/render.md 레시피를 보고 대상 레포에 **임시로** 짠다.
# 상태 관리 방식(Riverpod · Bloc · Redux …)을 스크립트가 알아맞히지 않는다.
# 여기서는 실행 · 수집 · 청소 · 흔적 검사만 한다. 한 Flutter 앱에서 사람이 챙긴
# "파일을 치운 뒤 git status 로 확인"을 명령이 강제한다.

_RENDER_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def _git_status(root: Path) -> list[str] | None:
    """추적 여부와 상관없이 바뀐 경로. git 레포가 아니면 None — 흔적 검사를 못 한다."""
    try:
        r = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return sorted(line for line in r.stdout.splitlines() if line.strip())


def _inside(root: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _unique(dst: Path) -> Path:
    """같은 이름이 있으면 번호를 붙인다. 덮어쓰면 앞 상태의 캡처가 사라진다."""
    if not dst.exists():
        return dst
    n = 2
    while True:
        cand = dst.with_name(f"{dst.stem}-{n}{dst.suffix}")
        if not cand.exists():
            return cand
        n += 1


def _cleanup(root: Path, paths: list[str]) -> tuple[list[str], list[str]]:
    """지정한 경로만 지운다. **레포 밖은 거절한다** — 오타 하나로 남의 폴더가 날아간다."""
    removed, refused = [], []
    for raw in paths or []:
        t = (root / raw) if not Path(raw).is_absolute() else Path(raw)
        if not _inside(root, t) or t.resolve() == root.resolve():
            refused.append(raw)
            continue
        if t.is_dir():
            shutil.rmtree(t, ignore_errors=True)
            removed.append(raw)
        elif t.exists():
            t.unlink()
            removed.append(raw)
    return removed, refused


_RENDER_BASE = "render-baseline.json"


def _baseline_path(root: Path) -> Path:
    return _home(root) / _RENDER_BASE


def cmd_render(args) -> int:
    root = _root(args)
    if args.action == "snapshot":
        return _render_snapshot(root)
    if not args.cmd:
        return out({"ok": False, "code": "cmd_required", "error": "--cmd 가 필요합니다"})

    # 기준은 **임시 파일을 만들기 전**의 상태여야 한다. run 직전에 뜨면 이미 만든 임시
    # 파일이 기준에 들어가, --cleanup 에서 빠뜨린 것이 남아도 흔적으로 안 잡힌다 (실측으로 짜 보다 발견).
    base_f = _baseline_path(root)
    before, baseline_from = None, "run"
    if base_f.is_file():
        try:
            saved = json.loads(base_f.read_text(encoding="utf-8"))
            if saved.get("root") == str(root):
                before, baseline_from = saved.get("status"), "snapshot"
        except (OSError, json.JSONDecodeError):
            pass
    if before is None:
        before = _git_status(root)
    cwd = (root / args.cwd) if args.cwd else root
    if not cwd.is_dir():
        return out({"ok": False, "code": "cwd_not_found",
                    "error": f"--cwd 폴더가 없습니다: {cwd}",
                    "next": "--cwd 는 레포 루트(--root) 기준 상대 경로다"})
    try:
        r = subprocess.run(["bash", "-lc", args.cmd], cwd=str(cwd), capture_output=True,
                           text=True, timeout=args.timeout, stdin=subprocess.DEVNULL)
        rc, output = r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired as e:
        rc = -1
        output = ((e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes)
                  else (e.stdout or "")) + f"\n[제한 시간 {args.timeout}초 초과]"
    tail = "\n".join(output.splitlines()[-40:])

    collected: list[str] = []
    if rc == 0:
        shot_dir = _shot_dir(root)
        for pattern in args.collect or []:
            for f in sorted(root.glob(pattern)):
                if f.is_file() and f.suffix.lower() in _RENDER_EXT and _inside(root, f):
                    dst = _unique(shot_dir / f.name)
                    shutil.move(str(f), str(dst))
                    collected.append(str(dst))

    # 실패해도 청소는 한다 — 임시 테스트 파일이 남으면 그것이 곧 흔적이다
    removed, refused = _cleanup(root, args.cleanup)
    after = _git_status(root)
    residue = None
    if before is not None and after is not None:
        residue = [line for line in after if line not in before]
    if baseline_from == "snapshot":
        base_f.unlink(missing_ok=True)   # 한 번 쓰면 끝이다 — 낡은 기준으로 다음 렌더를 재지 않는다

    payload = {"exit_code": rc, "collected": collected, "removed": removed,
               "refused_cleanup": refused or None, "residue": residue,
               "git_checked": before is not None, "baseline": baseline_from}
    if rc != 0:
        payload.update({"ok": False, "code": "render_failed", "output_tail": tail,
                        "summary": f"렌더 명령 실패 (종료코드 {rc}) — 수집하지 않고 청소만 했다",
                        "next": "output_tail 을 읽고 렌더 코드를 고친다. 레시피의 함정 표를 먼저 본다"})
    elif residue:
        # 지우지 않는다 — 다른 세션의 변경일 수 있다
        payload.update({"ok": False, "code": "residue",
                        "summary": f"렌더 뒤 레포에 흔적 {len(residue)}건이 남았다",
                        "next": "남은 경로를 보고 네가 만든 것이면 --cleanup 에 넣어 다시 돌리거나 직접 지운다. "
                                "모르는 변경이면 건드리지 않는다"})
    elif not collected:
        payload.update({"ok": False, "code": "nothing_collected",
                        "summary": "명령은 성공했는데 모은 그림이 없다",
                        "next": "--collect 글롭이 렌더 결과 경로와 맞는지 본다 (레포 루트 기준)"})
    else:
        payload.update({"summary": f"{len(collected)}장 수집 · 흔적 없음"
                                   + ("" if before is not None else " (git 레포가 아니라 흔적 검사 못 함)"),
                        "next": "Read 로 열어 본다. 이슈에 붙일 거면 shrink 로 줄인다"})
    if refused:
        payload["warning"] = f"레포 밖이라 지우지 않은 경로: {', '.join(refused)}"
    return out(payload)


def _render_snapshot(root: Path) -> int:
    status = _git_status(root)
    if status is None:
        return out({"ok": False, "code": "not_git", "error": "git 레포가 아니라 흔적 검사 기준을 뜰 수 없습니다",
                    "hint": "그래도 render run 은 돈다 — 청소만 하고 흔적 검사는 건너뛴다"})
    f = _baseline_path(root)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"root": str(root), "status": status,
                             "at": time.strftime("%Y-%m-%d %H:%M:%S")}, ensure_ascii=False),
                 encoding="utf-8")
    return out({"baseline": str(f), "changed_now": len(status),
                "summary": f"기준을 떴다 (지금 바뀐 경로 {len(status)}건 — 이것들은 흔적으로 보지 않는다)",
                "next": "이제 임시 렌더 코드를 만들고 render run 을 부른다"})


def cmd_shrink(args) -> int:
    return out(shrink([Path(p) for p in args.paths], max_side=args.max_side,
                      quality=args.quality, keep_format=args.keep_format))


# =========================================================================
# 인자
# =========================================================================

def _shot_args(p) -> None:
    # 세션 토큰은 해상도에서만 줄어든다. 0 을 주면 원본 크기 그대로 둔다.
    p.add_argument("--max-side", type=int, default=SHOT_MAX_SIDE,
                   help=f"긴 변 상한 (기본 {SHOT_MAX_SIDE}, 0이면 원본)")
    p.add_argument("--quality", type=int, default=WEBP_QUALITY,
                   help=f"WebP 품질 (기본 {WEBP_QUALITY})")
    p.add_argument("--keep-format", action="store_true",
                   help="PNG 원본 그대로 둔다 — 픽셀 대조처럼 원본이 필요할 때")


# =========================================================================
# 컴퓨터별 학습 메모 — recall · learn · forget (설계: docs/superpowers/specs/2026-09-29-...)
# =========================================================================

def _repo_unknown(root: Path) -> bool:
    """프로젝트를 알 수 없다 — 스킬·플러그인 폴더에서 불렸고 git 원격도 없다 (판정은 state.repo_unknown)."""
    return repo_unknown(root)


def _knowledge_paths(args) -> dict:
    scope = getattr(args, "scope", "both")
    root = _root(args)
    want = ("repo", "machine") if scope == "both" else (scope,)
    if _repo_unknown(root):
        # 어느 레포인지 모르면 레포 범위를 만들지 않는다 — 'scripts' 같은 가짜 레포가 생긴다
        want = ("machine",)
    return {sc: knowledge.store_path(sc, root) for sc in want}


def _learn_scope(args) -> str:
    return "machine" if args.scope == "repo" and _repo_unknown(_root(args)) else args.scope


def cmd_recall(args) -> int:
    rows = knowledge.recall(_knowledge_paths(args), args.area, args.limit)
    if not rows:
        return out({"ok": True, "code": "empty", "entries": [],
                    "summary": "이 컴퓨터에서 쌓인 방법이 아직 없다",
                    "next": "작업이 끝나면 launch_cli.py learn 으로 먹힌 방법을 남긴다"})
    return out({"ok": True, "code": "ok", "entries": rows,
                "summary": f"{len(rows)}건 (verify:true 는 한 번 확인하고 쓴다)",
                "next": "먹혔는지 안 먹혔는지 learn --result ok|fail 로 알린다"})


def cmd_learn(args) -> int:
    args.scope = _learn_scope(args)
    repo_path = None if args.scope == "machine" else knowledge.store_path("repo", _root(args))
    r = knowledge.learn_smart(repo_path, args.area, args.key, args.how, args.result, args.scope)
    if "error" in r:
        return out({"ok": False, "code": r["error"], "error": r["message"],
                    "next": "내용을 고쳐 다시 부른다"})
    e = r["entry"]
    note = (f" — 다른 레포의 같은 지식 {r['promoted_from']}건과 합쳐 이 컴퓨터 범위로 올렸다"
            if r.get("promoted_from") else "")
    rel = r.get("related") or []
    return out({"ok": True, "code": "ok", "entry": e, "scope": r["scope"],
                "promoted_from": r.get("promoted_from", 0), "related": rel or None,
                "summary": f"{e['key']} ok={e['ok']} fail={e['fail']} ({r['scope']}){note}",
                # 비슷한 기억이 있으면 같은 지식인지 agent 가 판단한다 — 도구가 애매한 것을 멋대로 합치지 않는다
                "next": (f"related 중 같은 지식이 있으면 forget --key <방금 key> 후 "
                         f"learn --scope machine --key <그 key> 로 합친다" if rel else None)})


def cmd_tidy(args) -> int:
    """흩어진 기억을 정리한다 — 여러 레포에 걸친 것과 잘못된 버킷을 이 컴퓨터 범위로 합친다."""
    r = knowledge.tidy()
    return out({"ok": True, "code": "ok", **r,
                "summary": f"{r['moved_to_machine']}건을 이 컴퓨터 범위로 옮김 (합친 것 {r['merged']}건)",
                "next": "recall --scope machine  # 결과를 본다"})


def cmd_forget(args) -> int:
    args.scope = _learn_scope(args)
    path = knowledge.store_path(args.scope, _root(args))
    n = knowledge.forget(path, args.key, args.area)
    return out({"ok": True, "code": "ok" if n else "not_found", "removed": n,
                "summary": f"{n}건 지움" if n else "그런 항목이 없다", "next": None})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="launch_cli",
                                     description="앱·웹·서버를 띄우고 조작하고 찍는다")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("doctor", help="도구 설치 여부 · 저장 위치")
    p.add_argument("--root", default=".")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("detect", help="무엇을 띄울 수 있는지 (마커 파일 · 기기 · 브라우저)")
    p.add_argument("--path", default=".", help="탐색 시작 경로")
    p.add_argument("--kinds", default=None,
                   help="app,web,server 중 정보를 모을 것 (감지 대신 — 부르는 쪽이 이미 알 때)")
    p.set_defaults(func=cmd_detect)

    p = sub.add_parser("devices", help="붙은 기기 · 부팅된 시뮬레이터 · AVD")
    p.set_defaults(func=cmd_devices)

    p = sub.add_parser("device", help="역할을 기기에 묶는다 (참가자가 둘 이상일 때)")
    p.add_argument("action", choices=["list", "bind", "unbind", "show"])
    p.add_argument("--root", default=".")
    p.add_argument("--role", default=None, help="역할 키. 시나리오 roles 의 키와 같아야 한다")
    p.add_argument("--serial", default=None, help="기기 시리얼 (device list 에 나온다)")
    p.add_argument("--note", default=None, help="사람이 읽을 설명. env.sh 에 주석으로 붙는다")
    p.add_argument("--package", default=None, help="설치된 빌드를 대조할 패키지명")
    p.add_argument("--run-dir", default=None, help="env.sh 를 쓸 실행 폴더. 없으면 $RUN_DIR")
    p.set_defaults(func=cmd_device)

    p = sub.add_parser("app", help="앱 화면을 찍고(shot) 띄우고(launch) 글자를 넣고(type) 누르고(tap) 민다(swipe)")
    p.add_argument("action", choices=["shot", "launch", "type", "tap", "swipe", "tree"])
    p.add_argument("--text", dest="sel_text", default=None, help="tap: 보이는 문구로 찾는다")
    p.add_argument("--id", dest="sel_id", default=None, help="tap: resource-id(Android) · accessibilityIdentifier(iOS)")
    p.add_argument("--desc", dest="sel_desc", default=None, help="tap: 접근성 설명(content-desc)으로 찾는다")
    p.add_argument("--index", type=int, default=0, help="tap: 여러 개 맞으면 몇 번째 (0부터)")
    p.add_argument("--at", default=None, help="tap: 요소로 못 찾을 때만 — 0~1 비율 좌표 (예: 0.5,0.8)")
    p.add_argument("--dir", choices=sorted(app_input.SWIPE_DIRS), default=None, help="swipe: 방향")
    p.add_argument("--from", dest="frm", default=None, help="swipe: 시작 비율 좌표 (예: 0.5,0.8)")
    p.add_argument("--to", default=None, help="swipe: 끝 비율 좌표")
    p.add_argument("--ms", type=int, default=300, help="swipe: 걸리는 시간(ms)")
    p.add_argument("--shot", default=None, help="tap·swipe: 끝나면 바로 찍는다 (이름 또는 경로) — 확인용 shot 호출을 아낀다")
    p.add_argument("--cred", default=None, help="type: 저장된 로그인 정보 이름 (cred list)")
    p.add_argument("--cred-field", dest="cred_field", default=None, help="type: 넣을 필드 (기본 password, 예: account)")
    p.add_argument("--text-env", dest="text_env", default=None, help="type: 값을 읽을 환경변수 (일회용)")
    p.add_argument("--submit", action="store_true", help="type: 입력 뒤 Enter")
    p.add_argument("--root", default=".")
    p.add_argument("--device", default=None,
                   help="Android 시리얼 또는 iOS UDID. 없으면 $DEV → 붙은 기기가 한 대면 그것")
    p.add_argument("--out", default=None,
                   help="shot: 이름(→ $SHOT_DIR 아래) 또는 경로(그대로 저장)")
    p.add_argument("--clean-status", action="store_true",
                   help="shot: 상태바 시각·배터리를 고정해 찍고 되돌린다")
    p.add_argument("--pkg", default=None, help="launch: 패키지명·번들 ID (없으면 $PKG)")
    _shot_args(p)
    p.set_defaults(func=cmd_app)

    p = sub.add_parser("web", help="브라우저를 조작한다")
    p.add_argument("action", choices=["setup", "open", "goto", "find", "click", "type", "text", "shot",
                                      "assert", "console", "close", "viewport", "route"])
    p.add_argument("--force", action="store_true", help="setup: 이미 있어도 다시 만든다")
    p.add_argument("--root", default=".")
    p.add_argument("--url", default=None, help="주소 (open·goto·assert)")
    p.add_argument("--selector", default=None,
                   help="대상 (click·type·assert·shot). text=로그인 · #id · button:has-text('x')")
    p.add_argument("--text", default=None, help="입력할 값 또는 확인할 문구")
    p.add_argument("--cred", default=None, help="저장된 로그인 정보로 입력한다 (cred list). 값은 명령줄에 남지 않는다")
    p.add_argument("--cred-field", dest="cred_field", default=None, help="--cred 에서 넣을 필드 (기본 password, 예: account)")
    p.add_argument("--text-env", dest="text_env", default=None,
                   help="입력값을 환경변수에서 읽는다 — 비밀번호는 반드시 이쪽")
    p.add_argument("--out", default=None, help="shot: 이름(→ $SHOT_DIR 아래) 또는 경로")
    p.add_argument("--full", action="store_true", help="shot: 페이지 전체")
    p.add_argument("--headed", action="store_true",
                   help="open: 눈에 보이게 연다 — 소셜 로그인이 막히면 이것이 먼저다(#604 실측)")
    p.add_argument("--no-stealth", action="store_true",
                   help="open: 자동화 표식 가리기를 끈다 (사이트가 깨질 때 비교용)")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=800)
    p.add_argument("--timeout", type=int, default=10, help="대기 제한(초)")
    p.add_argument("--preset", default=None,
                   help="viewport: mobile · tablet · desktop 또는 390x844")
    p.add_argument("--match", default=None, help="route: 바꿔칠 요청 주소 glob. 예 **/api/items*")
    p.add_argument("--status", type=int, default=None, help="route: 돌려줄 상태 코드")
    p.add_argument("--body", default=None, help="route: 돌려줄 본문 (파일 경로 또는 짧은 문자열)")
    p.add_argument("--body-text", dest="body_text", default=None,
                   help="route: 글자 그대로 돌려줄 본문 (파일 경로로 읽지 않는다)")
    p.add_argument("--delay", type=int, default=0, help="route: 응답 지연(ms) — 로딩 상태 연출")
    p.add_argument("--clear", action="store_true", help="viewport·route: 지정을 푼다")
    p.add_argument("--ref", type=int, default=None, help="click: web find 가 준 번호. 선택자 추측 대신 이것을 쓴다")
    p.add_argument("--role", default=None, help="find: link · button · row · tab 처럼 역할로 좁힌다")
    p.add_argument("--limit", type=int, default=20, help="find: 돌려줄 후보 수")
    p.add_argument("--max-chars", dest="max_chars", type=int, default=3000, help="text: 돌려줄 최대 글자 수")
    p.add_argument("--expect-url", dest="expect_url", default=None,
                   help="click: 누른 뒤 주소에 이 글자가 들어올 때까지 기다린다. 안 오면 실패")
    p.add_argument("--expect-text", dest="expect_text", default=None,
                   help="click: 누른 뒤 이 글자가 보일 때까지 기다린다. 안 오면 실패")
    p.add_argument("--readonly", action="store_true",
                   help="open: 읽기 전용 세션 — 삭제·출시·제출 같은 버튼은 --confirm-mutating 없이 누르지 않는다")
    p.add_argument("--confirm-mutating", dest="confirm_mutating", action="store_true",
                   help="click: 읽기 전용 세션에서도 누른다 (사용자 승인을 받은 뒤에만)")
    _shot_args(p)
    p.set_defaults(func=cmd_web)

    p = sub.add_parser("render", help="렌더 명령을 돌리고 그림을 모으고 흔적을 검사한다")
    p.add_argument("action", choices=["snapshot", "run"],
                   help="snapshot: 임시 파일을 만들기 **전에** 흔적 검사 기준을 뜬다 · run: 돌리고 모은다")
    p.add_argument("--cmd", default=None, help="run: 렌더 명령 (agent 가 짠 임시 테스트를 돌리는 것)")
    p.add_argument("--collect", action="append", default=None,
                   help="모을 그림 글롭 (레포 루트 기준, 여러 번). 예 client/test/_launch_render/**/*.png")
    p.add_argument("--cleanup", action="append", default=None,
                   help="끝나고 지울 경로 (레포 안만, 여러 번). 임시 테스트 파일·폴더")
    p.add_argument("--cwd", default=None, help="명령을 돌릴 곳 (레포 루트 기준, 예 client)")
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--root", default=".", help="대상 레포 루트 — 흔적 검사 기준")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("http", help="단건 HTTP 요청")
    p.add_argument("--method", default="GET")
    p.add_argument("--url", required=True, help="전체 주소 또는 경로(→ access 의 base_url 에 붙인다)")
    p.add_argument("--header", action="append", default=None, help="'이름: 값' — 여러 번")
    p.add_argument("--cred", default=None, help="저장된 토큰·계정으로 Authorization 을 만든다 (cred list)")
    p.add_argument("--data", default=None, help="본문. @파일 로 파일을 읽는다")
    p.add_argument("--save", default=None, help="응답 본문을 저장 (이름이면 $RUN_DIR/http/ 아래)")
    p.add_argument("--expect-status", type=int, default=None, help="다르면 ok:false")
    p.add_argument("--timeout", type=int, default=30)
    p.add_argument("--root", default=".")
    p.set_defaults(func=cmd_http)

    p = sub.add_parser("access", help="붙는 법을 적어 두고 꺼내 쓴다")
    p.add_argument("action", choices=["show", "set", "unset"])
    p.add_argument("--root", default=".")
    p.add_argument("--key", default=None, help="db · logs · base_url 등")
    p.add_argument("--json", dest="json_value", default=None,
                   help='적을 내용(JSON). 예: {"how":"ssh","engine":"postgres",...}')
    p.add_argument("--allow-secret", dest="allow_secret", action="store_true",
                   help="비밀값 경고를 무시한다 (권장하지 않음)")
    p.set_defaults(func=cmd_access)

    p = sub.add_parser("db", help="SQL을 실행한다 (접속 방법은 호출하는 쪽이 정한다)")
    p.add_argument("--sql", required=True)
    p.add_argument("--engine", default=None, help="postgres · mysql (--command 면 불필요)")
    p.add_argument("--host", default=None)
    p.add_argument("--port", default=None)
    p.add_argument("--db", default=None, help="데이터베이스 이름")
    p.add_argument("--user", default=None)
    p.add_argument("--password", default=None, help="생략하면 DB_PASSWORD 환경변수 (권장)")
    p.add_argument("--via", choices=["direct", "ssh"], default="direct")
    p.add_argument("--ssh-host", dest="ssh_host", default=None)
    p.add_argument("--ssh-user", dest="ssh_user", default=None)
    p.add_argument("--ssh-port", dest="ssh_port", default=None)
    p.add_argument("--command", default=None,
                   help="접속을 통째로 지정한다. 예: \"docker exec -i pg psql -U root -d appdb -c\"")
    p.add_argument("--append-sql", dest="append_sql", action="store_true",
                   help="--command 뒤에 SQL을 인자로 붙인다 (기본은 표준입력)")
    p.add_argument("--profile", default=None, help="access 에 적어 둔 기록을 쓴다 (예: db)")
    p.add_argument("--cred", default=None, help="저장된 자격증명으로 host·user·password 를 채운다 (cred list)")
    p.add_argument("--root", default=".")
    p.add_argument("--timeout", type=int, default=40)
    p.set_defaults(func=cmd_db)

    p = sub.add_parser("logs", help="서버 로그를 본다 (보는 방법은 access 에 적어 둔다)")
    p.add_argument("--root", default=".")
    p.add_argument("--profile", default=None, help="access 의 어느 키를 쓸지 (기본 logs)")
    p.add_argument("--command", default=None, help="즉석으로 실행할 명령")
    p.add_argument("--cred", default=None,
                   help="저장된 자격증명을 CRED_HOST · CRED_USER · SSHPASS 등 환경변수로 넘긴다 (cred list)")
    p.add_argument("--tail", type=int, default=200)
    p.add_argument("--grep", default=None)
    p.add_argument("--timeout", type=int, default=60)
    p.set_defaults(func=cmd_logs)

    p = sub.add_parser("cred", help="이름 붙은 자격증명을 저장하고 꺼낸다 (다음 실행에서 다시 묻지 않는다)")
    p.add_argument("action", choices=["list", "show", "set", "unset", "import-ssh"])
    p.add_argument("--name", default=None)
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="import-ssh 때 아무것도 쓰지 않고 옮길 목록만 보여 준다 (비밀 값은 가려서)")
    p.add_argument("--inline", action="store_true",
                   help="(기본 동작) import-ssh 때 host·user·password 값까지 복사한다")
    p.add_argument("--ref", action="store_true",
                   help="import-ssh 때 값을 복사하지 않고 옛 ssh 섹션을 참조만 한다 (비밀번호가 두 곳에 남는다)")
    p.add_argument("--prune", action="store_true",
                   help="import-ssh 뒤에 가져온 서버를 옛 ssh 섹션에서 지운다 (config 를 먼저 백업)")
    p.add_argument("--json", dest="json_value", default=None,
                   help='저장할 내용(JSON). 예: {"kind":"ssh","host":"h","port":22,"user":"u","use_when":"..."}')
    p.add_argument("--replace", action="store_true", help="set 때 기존 항목을 합치지 않고 통째로 바꾼다")
    p.add_argument("--reveal", action="store_true", help="show 때 비밀 값도 그대로 보여 준다 (꼭 필요할 때만)")
    p.add_argument("--prompt", action="store_true",
                   help="set 때 이 맥의 sudo 비밀번호를 터미널에서 직접 입력받아 저장한다 (화면에 안 보임, TTY 필요)")
    p.set_defaults(func=cmd_cred)

    p = sub.add_parser("local", help="저장된 자격증명으로 이 맥에서 sudo 명령을 실행한다")
    p.add_argument("action", choices=["sudo"])
    p.add_argument("--cred", default=None, help="kind 가 local 인 자격증명 이름 (cred list)")
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--max-output", dest="max_output", type=int, default=20000)
    # 실행할 명령은 `--` 뒤에 둔다. main() 이 파서 전에 잘라 args.command 로 넣는다.
    p.set_defaults(func=cmd_local, command=[])

    p = sub.add_parser("ssh", help="원격 명령을 실행한다 (저장된 서버 --cred, 또는 저장 없이 --host 로 직접)")
    p.add_argument("--cred", default=None, help="저장된 서버 자격증명 이름 (cred list)")
    p.add_argument("--host", default=None, help="저장 없이 직접 접속: 호스트 (--cred 와 함께 주면 그 값을 덮어쓴다)")
    p.add_argument("--port", type=int, default=None, help="SSH 포트")
    p.add_argument("--user", default=None, help="계정")
    p.add_argument("--password", default=None, help="비밀번호 (기록에 남아도 되는 환경일 때. 아니면 --password-env)")
    p.add_argument("--password-env", dest="password_env", default=None, help="비밀번호를 읽을 환경변수 이름")
    p.add_argument("--key-path", dest="key_path", default=None, help="개인키(PEM) 파일 경로 — 비밀번호 대신")
    p.add_argument("--command", default=None, help="원격에서 실행할 명령")
    p.add_argument("--sudo", action="store_true", help="원격에서 SUDO <명령> 을 쓸 수 있게 한다 (비밀번호 sudo)")
    p.add_argument("--timeout", type=int, default=60)
    p.add_argument("--max-output", dest="max_output", type=int, default=20000)
    p.set_defaults(func=cmd_ssh)

    p = sub.add_parser("shrink", help="이슈 첨부용으로 이미지 축소 · WebP")
    p.add_argument("paths", nargs="+")
    p.add_argument("--max-side", type=int, default=SHOT_MAX_SIDE,
                   help=f"긴 변 상한 (기본 {SHOT_MAX_SIDE}) — 캡처와 같은 기준")
    p.add_argument("--quality", type=int, default=WEBP_QUALITY,
                   help=f"WebP 품질 (기본 {WEBP_QUALITY})")
    p.add_argument("--keep-format", action="store_true", help="WebP 로 바꾸지 않는다")
    p.set_defaults(func=cmd_shrink)

    p = sub.add_parser("recall", help="이 컴퓨터에서 먹힌 조작 방식을 꺼낸다 (작업 시작 때 한 번)")
    p.add_argument("--area", choices=list(knowledge.AREAS), default=None)
    p.add_argument("--limit", type=int, default=knowledge.DEFAULT_LIMIT)
    p.add_argument("--scope", choices=["both", "repo", "machine"], default="both")
    p.add_argument("--root", default=".")
    p.set_defaults(func=cmd_recall)

    p = sub.add_parser("learn", help="먹힌·안 먹힌 방식을 남긴다 (쓸수록 정확해진다)")
    p.add_argument("--area", required=True, choices=list(knowledge.AREAS))
    p.add_argument("--key", required=True, help="한 줄 이름 (예: ios.tap)")
    p.add_argument("--how", required=True, help=f"방법 ({knowledge.MAX_HOW}자 이내, 비밀값 금지)")
    p.add_argument("--result", required=True, choices=["ok", "fail"])
    p.add_argument("--scope", choices=list(knowledge.SCOPES), default="repo")
    p.add_argument("--root", default=".")
    p.set_defaults(func=cmd_learn)

    p = sub.add_parser("tidy", help="흩어진 기억을 정리한다 (여러 레포에 걸친 것 → 이 컴퓨터 범위)")
    p.add_argument("--root", default=".")
    p.set_defaults(func=cmd_tidy)

    p = sub.add_parser("forget", help="잘못 배운 방식을 지운다")
    p.add_argument("--key", required=True)
    p.add_argument("--area", choices=list(knowledge.AREAS), default=None)
    p.add_argument("--scope", choices=list(knowledge.SCOPES), default="repo")
    p.add_argument("--root", default=".")
    p.set_defaults(func=cmd_forget)

    p = sub.add_parser("get-output-path", help="이번 실행의 산출물 자리 + env.sh")
    p.add_argument("--skill", default=None,
                   help="자리를 받을 작업 스킬 id (기본 launch). 증거 스킬만 된다")
    p.add_argument("--title", default=None, help="제목. 없으면 워크트리 경로·브랜치명에서 뽑는다")
    p.add_argument("--package", default=None, help="앱 패키지명 — env.sh 에 PKG 로 넣는다")
    p.add_argument("--root", default=".")
    p.set_defaults(func=cmd_output_path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    raw = list(sys.argv[1:] if argv is None else argv)
    # local sudo: `--` 뒤는 실행할 명령이라 파서에 넘기지 않는다. argparse 의 REMAINDER 는 앞의
    # --cred 같은 옵션까지 삼키므로, 미리 잘라 두었다가 args.command 로 되돌려 준다 (#784).
    tail: list[str] = []
    if raw[:1] == ["local"] and "--" in raw:
        i = raw.index("--")
        raw, tail = raw[:i], raw[i + 1:]
    try:
        args = parser.parse_args(raw)
        if getattr(args, "func", None) is cmd_local:
            args.command = tail
    except SystemExit as e:
        if e.code in (0, None):
            raise
        return emit({"ok": False, "code": "bad_args",
                     "error": "인자가 올바르지 않습니다 (위 사용법 참고)",
                     "next": "launch_cli.py <서브커맨드> --help"})
    # 한 프로세스에서 main 을 여러 번 부르는 경우(테스트) 이전 호출의 표시가 새지 않게 한다
    _ROOT_CTX.clear()
    _ACCESS_CTX.clear()
    try:
        return args.func(args)
    except Exception as e:   # 예상 못 한 입력이 트레이스백으로 끝나지 않게 — 에이전트는 JSON 만 읽는다 (#705)
        return emit({"ok": False, "code": "handler_error",
                     "error": f"{type(e).__name__}: {e}",
                     "next": "입력(경로·값)을 확인하고 다시 부른다"})


if __name__ == "__main__":
    sys.exit(main())
