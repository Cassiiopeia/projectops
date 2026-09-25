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
    get-output-path  이번 실행 자리 + env.sh

출력: MCP-style JSON (ok/code/summary/next 4필드 보장).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.access import access_path, find_secrets, load_access, save_access  # noqa: E402
from common.emit import emit  # noqa: E402
from common.image import (SHOT_MAX_SIDE, WEBP_QUALITY, has_pillow,  # noqa: E402
                          resize_tool, shrink, to_webp)
from common.proc import run, sdk_tool  # noqa: E402
from common.state import (launch_file, migrate_launch, repo_key,  # noqa: E402
                          state_dir, venv_dir, venv_python, venv_site_packages)

# 같은 스킬 안의 보조 모듈 — 스크립트로 불리든 테스트가 import 하든 찾게 한다
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))
import stealth  # noqa: E402


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
    return emit(payload)


def _root(args) -> Path:
    return Path(getattr(args, "root", ".") or ".").resolve()


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
    return out({
        "checks": checks,
        "browser": pw,
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


def cmd_detect(args) -> int:
    """무엇을 띄울 수 있는지. 마커 파일·기기·브라우저 준비 상태만 본다."""
    start = Path(args.path).resolve()
    git_root = run(["git", "-C", str(start), "rev-parse", "--show-toplevel"]).strip()
    root = Path(git_root) if git_root else start

    det = detect_kinds(root)
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
        return "android", cand, dev
    if cand in udids or cand == "booted":
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

                def restore():
                    _adb_shell(dev_id, *_ANDROID_DEMO_EXIT)
                    if prev in ("", "null"):
                        _adb_shell(dev_id, "settings", "delete", "global", "sysui_demo_allowed")
                    else:
                        _adb_shell(dev_id, "settings", "put", "global",
                                   "sysui_demo_allowed", prev)
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


def cmd_app(args) -> int:
    return _app_shot(args) if args.action == "shot" else _app_launch(args)


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
        proc.terminate()
        return out({"ok": False, "code": "browser_start_failed",
                    "error": "브라우저가 뜨지 않았습니다",
                    "hint": "web setup 으로 브라우저를 다시 받아 보세요"})

    # 뷰포트·바꿔치기 규칙은 브라우저를 다시 열어도 이어간다 — 설정한 사람이 끈 적이 없다
    prev = _read_web_state(state_f)
    state = {"cdp": cdp, "pid": proc.pid, "headed": bool(args.headed),
             "stealth": use_stealth, "profile": str(profile), "opened_at": time.strftime("%Y-%m-%d %H:%M:%S"),
             "viewport": prev.get("viewport"), "routes": prev.get("routes") or []}
    _write_web_state(state_f, state)

    hooked = False
    conn, cerr = _web_connect(state)
    if not cerr:
        _pw, _br, _pg = conn
        hooked = True
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
                "stealth": use_stealth,
                "summary": f"브라우저를 열었습니다 ({args.url or '빈 탭'})",
                "next": "web shot  # 화면을 먼저 봅니다"})


def _web_close(browser, state: dict, state_f: Path) -> int:
    browser.close()
    # CDP로 붙은 브라우저는 close()로 안 죽는 경우가 있다(우리가 띄운 독립 프로세스다)
    pid = state.get("pid")
    if pid:
        try:
            os.kill(int(pid), 15)
        except (ProcessLookupError, PermissionError, ValueError):
            pass
    alive = False
    if pid:
        for _ in range(10):
            try:
                os.kill(int(pid), 0)
            except (ProcessLookupError, ValueError):
                alive = False
                break
            except PermissionError:
                alive = True
                break
            alive = True
            time.sleep(0.2)
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
    body, ctype = "", "application/json"
    if args.body:
        bf = Path(args.body)
        if bf.is_file():
            body = bf.read_text(encoding="utf-8")
        else:
            body = args.body   # 짧은 본문은 그대로 받는다: --body '[]'
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
    # 비밀번호를 --text 에 적으면 세션 기록에 평문으로 남는다(#604) — --text-env 로 받는다
    secret_value = None
    if getattr(args, "text_env", None):
        if args.text_env not in os.environ:
            return out({"ok": False, "code": "env_not_set",
                        "error": f"환경변수 {args.text_env} 가 비어 있습니다",
                        "hint": f'{args.text_env}="..." 를 같은 명령 앞에 붙여 실행하세요'})
        secret_value = os.environ[args.text_env]
        args.text = secret_value

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
    conn, err = _web_connect(state)
    if err:
        if err.get("code") == "browser_gone":
            # 죽은 브라우저 정보만 지운다. 뷰포트·규칙은 사람이 정한 것이라 남긴다
            for k in ("cdp", "pid"):
                state.pop(k, None)
            _write_web_state(state_f, state)
        return out(err)
    pw, browser, page = conn

    try:
        if args.action == "close":
            return _web_close(browser, state, state_f)

        if args.action == "goto":
            if not args.url:
                return out({"ok": False, "code": "url_required", "error": "--url 이 필요합니다"})
            page.goto(args.url, wait_until="domcontentloaded")
            _settle(page, state, args.timeout)

        elif args.action == "click":
            if not args.selector:
                return out({"ok": False, "code": "selector_required",
                            "error": "--selector 가 필요합니다",
                            "hint": "text=로그인 · #submit · button:has-text('저장')"})
            page.click(args.selector, timeout=args.timeout * 1000)
            _settle(page, state, args.timeout)

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

        return out({"action": args.action, "url": page.url, "title": page.title(),
                    "summary": f"{args.action} 완료 — {page.url}",
                    "next": "web shot  # 결과를 눈으로 확인하세요"})
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

def http_call(method: str, url: str, headers: dict | None = None,
              data: bytes | None = None, timeout: int = 30) -> dict:
    """한 요청을 보낸다. 실패 응답(4xx·5xx)도 결과다 — 예외로 끝내지 않는다."""
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status, rh = resp.status, dict(resp.headers.items())
    except urllib.error.HTTPError as e:
        raw = e.fp.read() if e.fp else b""
        status, rh = e.code, dict(e.headers.items()) if e.headers else {}
    except Exception as e:  # 네트워크 자체가 안 될 때
        return {"ok": False, "code": "request_failed", "url": url, "error": str(e),
                "elapsed_ms": int((time.time() - started) * 1000)}
    text = raw.decode("utf-8", "replace")
    try:
        parsed = json.loads(text) if text.strip() else None
    except json.JSONDecodeError:
        parsed = None
    return {"ok": True, "url": url, "status": status, "headers": rh, "json": parsed,
            "text": None if parsed is not None else text[:4000], "raw": raw,
            "elapsed_ms": int((time.time() - started) * 1000)}


def cmd_http(args) -> int:
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

    headers = {"Accept": "application/json"}
    for h in args.header or []:
        if ":" not in h:
            return out({"ok": False, "code": "bad_header",
                        "error": f"헤더 '{h}' 는 '이름: 값' 형식이어야 합니다"})
        k, v = h.split(":", 1)
        headers[k.strip()] = v.strip()
    data = None
    if args.data is not None:
        text = Path(args.data[1:]).read_text(encoding="utf-8") if args.data.startswith("@") \
            else args.data
        data = text.encode("utf-8")
        try:
            json.loads(text)
            headers.setdefault("Content-Type", "application/json")
        except json.JSONDecodeError:
            pass

    r = http_call(args.method.upper(), url, headers, data, timeout=args.timeout)
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
        return out({"file": str(access_path(root)), "access": data,
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
                        "hint": '값 대신 읽을 곳을 적으세요. 예: {"password_env": "APP_DB_PASSWORD"}'})
        data[args.key] = value
        f = save_access(root, data)
        return out({"file": str(f), "key": args.key, "access": data,
                    "summary": f"{args.key} 기록 완료"})

    if args.action == "unset":
        if args.key in data:
            del data[args.key]
            save_access(root, data)
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
    sql = args.sql
    if not sql:
        return out({"ok": False, "code": "sql_required", "error": "--sql 이 필요합니다"})

    # 적어 둔 접근 방법을 쓴다. 인자로 직접 준 값이 언제나 이긴다 — 기록이 낡았을 때의 탈출구.
    if args.profile:
        root = _root(args)
        _home(root)
        saved = load_access(root).get(args.profile)
        if not saved:
            return out({"ok": False, "code": "profile_not_found",
                        "error": f"'{args.profile}' 기록이 없습니다",
                        "next": f"access show --root {args.root}"})
        if isinstance(saved, dict):
            for k in ("engine", "host", "port", "db", "user", "password",
                      "command", "ssh_host", "ssh_user", "ssh_port"):
                if getattr(args, k, None) in (None, "") and saved.get(k) is not None:
                    setattr(args, k, saved[k])
            if saved.get("how") in ("ssh", "direct") and args.via == "direct":
                args.via = saved["how"]
            if saved.get("append_sql"):
                args.append_sql = True
            env_key = saved.get("password_env")
            if env_key and not args.password:
                args.password = os.environ.get(env_key)
                if not args.password:
                    return out({"ok": False, "code": "password_env_empty",
                                "error": f"환경변수 {env_key} 가 비어 있습니다",
                                "hint": f"{env_key}=... 를 주고 다시 부르세요"})

    try:
        if args.command:
            argv = (["bash", "-lc", f"{args.command} {_shq(sql)}"] if args.append_sql
                    else ["bash", "-lc", args.command])
            stdin = None if args.append_sql else sql
            r = subprocess.run(argv, input=stdin, capture_output=True, text=True,
                               timeout=args.timeout)
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
    root = _root(args)
    _home(root)
    command = args.command
    if not command:
        saved = load_access(root).get(args.profile or "logs")
        command = saved.get("command") if isinstance(saved, dict) else saved
    if not command:
        return out({"ok": False, "code": "no_log_command",
                    "error": "로그를 어떻게 보는지 모릅니다",
                    "hint": ('코드를 읽어 알아낸 뒤 적어 두세요. 예: '
                             'access set --key logs --json \'{"command":"ssh u@h \\"docker logs --tail 200 app\\""}\'')})
    if args.tail:
        command = f"{command} | tail -n {int(args.tail)}"
    if args.grep:
        command = f"{command} | grep -i -- {_shq(args.grep)}"
    try:
        r = subprocess.run(["bash", "-lc", command], capture_output=True, text=True,
                           timeout=args.timeout)
    except subprocess.TimeoutExpired:
        return out({"ok": False, "code": "logs_timeout", "error": f"응답 없음 ({args.timeout}초)"})
    text = r.stdout or ""
    return out({"ok": r.returncode == 0, "code": "ok" if r.returncode == 0 else "logs_failed",
                "lines": text.splitlines()[-(args.tail or 200):],
                "error": (r.stderr or "").strip()[:500] or None,
                "summary": f"{len(text.splitlines())}줄" if r.returncode == 0 else "실행 실패"})


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="launch_cli",
                                     description="앱·웹·서버를 띄우고 조작하고 찍는다")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("doctor", help="도구 설치 여부 · 저장 위치")
    p.add_argument("--root", default=".")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("detect", help="무엇을 띄울 수 있는지 (마커 파일 · 기기 · 브라우저)")
    p.add_argument("--path", default=".", help="탐색 시작 경로")
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

    p = sub.add_parser("app", help="앱 화면을 찍고(shot) 띄운다(launch)")
    p.add_argument("action", choices=["shot", "launch"])
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
    p.add_argument("action", choices=["setup", "open", "goto", "click", "type", "shot",
                                      "assert", "console", "close", "viewport", "route"])
    p.add_argument("--force", action="store_true", help="setup: 이미 있어도 다시 만든다")
    p.add_argument("--root", default=".")
    p.add_argument("--url", default=None, help="주소 (open·goto·assert)")
    p.add_argument("--selector", default=None,
                   help="대상 (click·type·assert·shot). text=로그인 · #id · button:has-text('x')")
    p.add_argument("--text", default=None, help="입력할 값 또는 확인할 문구")
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
    p.add_argument("--delay", type=int, default=0, help="route: 응답 지연(ms) — 로딩 상태 연출")
    p.add_argument("--clear", action="store_true", help="viewport·route: 지정을 푼다")
    _shot_args(p)
    p.set_defaults(func=cmd_web)

    p = sub.add_parser("http", help="단건 HTTP 요청")
    p.add_argument("--method", default="GET")
    p.add_argument("--url", required=True, help="전체 주소 또는 경로(→ access 의 base_url 에 붙인다)")
    p.add_argument("--header", action="append", default=None, help="'이름: 값' — 여러 번")
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
    p.add_argument("--root", default=".")
    p.add_argument("--timeout", type=int, default=40)
    p.set_defaults(func=cmd_db)

    p = sub.add_parser("logs", help="서버 로그를 본다 (보는 방법은 access 에 적어 둔다)")
    p.add_argument("--root", default=".")
    p.add_argument("--profile", default=None, help="access 의 어느 키를 쓸지 (기본 logs)")
    p.add_argument("--command", default=None, help="즉석으로 실행할 명령")
    p.add_argument("--tail", type=int, default=200)
    p.add_argument("--grep", default=None)
    p.add_argument("--timeout", type=int, default=60)
    p.set_defaults(func=cmd_logs)

    p = sub.add_parser("shrink", help="이슈 첨부용으로 이미지 축소 · WebP")
    p.add_argument("paths", nargs="+")
    p.add_argument("--max-side", type=int, default=SHOT_MAX_SIDE,
                   help=f"긴 변 상한 (기본 {SHOT_MAX_SIDE}) — 캡처와 같은 기준")
    p.add_argument("--quality", type=int, default=WEBP_QUALITY,
                   help=f"WebP 품질 (기본 {WEBP_QUALITY})")
    p.add_argument("--keep-format", action="store_true", help="WebP 로 바꾸지 않는다")
    p.set_defaults(func=cmd_shrink)

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
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        if e.code in (0, None):
            raise
        return emit({"ok": False, "code": "bad_args",
                     "error": "인자가 올바르지 않습니다 (위 사용법 참고)",
                     "next": "launch_cli.py <서브커맨드> --help"})
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
