#!/usr/bin/env python3
"""e2e_cli — pro-agent-test 전용 CLI (projectops 3-layer 표준, Layer 2).

Flutter 프로젝트를 실기기에서 밟기 전에 필요한 값들을 한 번에 찾아낸다.
매 호출마다 agent가 grep 조합을 다시 짜지 않도록 여기에 모아 둔다.

서브커맨드:
    detect   프로젝트 루트·패키지명·번들ID·API URL·연결된 기기를 한 번에 조사
    devices  연결/부팅된 기기만 조회
    backend  서버 로그·DB 고아 행 대조 (화면만 봐서는 못 잡는 것)

출력: MCP-style JSON (ok/code/summary/next 4필드 보장).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import time
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.emit import emit as _emit_raw  # noqa: E402


def emit(payload: dict) -> int:
    """공통 emit에 "지식을 옮겼다"는 알림을 얹는다.

    이전은 어느 명령에서든 일어날 수 있다(note·scenario·bootstrap...). 호출부마다
    챙기면 반드시 빠뜨리는 자리가 생기므로 출력 길목 한 곳에서 처리한다.
    한 번 실어 보내면 비운다 — 같은 실행에서 두 번 알릴 이유가 없다.
    """
    if _MIGRATION_NOTES:
        payload = {**payload, "migrated": list(_MIGRATION_NOTES)}
        _MIGRATION_NOTES.clear()
    return _emit_raw(payload)


def _sdk_tool(name: str) -> str | None:
    """Android SDK 도구 경로. PATH에 없으면 표준 설치 위치를 본다.

    adb·emulator는 SDK를 설치해도 PATH에 자동 등록되지 않는 경우가 많다.
    여기서 찾아주지 않으면 기기가 있는데도 "없음"으로 보고하게 된다.
    """
    found = shutil.which(name)
    if found:
        return found

    # Windows 실행 파일은 확장자가 붙는다. Git Bash에서도 마찬가지다.
    exe = f"{name}.exe" if sys.platform == "win32" else name

    roots = [Path.home() / "Library" / "Android" / "sdk",   # macOS 기본
             Path.home() / "Android" / "Sdk"]               # Linux 기본
    for env in ("ANDROID_HOME", "ANDROID_SDK_ROOT", "LOCALAPPDATA"):
        v = os.environ.get(env)
        if not v:
            continue
        base = Path(v)
        roots.append(base / "Android" / "Sdk" if env == "LOCALAPPDATA" else base)

    for root in roots:
        for sub in ("platform-tools", "emulator", "cmdline-tools/latest/bin"):
            cand = root / sub / exe
            if cand.exists():
                return str(cand)
    return None


def _run(cmd: list[str], timeout: int = 15) -> str:
    """외부 명령 실행. 실패해도 예외를 올리지 않는다 —
    기기가 없거나 도구가 미설치인 상황이 정상 경로이기 때문이다."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _find_flutter_root(start: Path) -> Path | None:
    """pubspec.yaml에 flutter 의존성이 있는 디렉터리를 찾는다.

    모노레포에서는 앱이 client/ 같은 하위에 있다. build/ 안의 사본은 제외한다.
    """
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


# ── 타겟 감지 (이슈 #586) ────────────────────────────────────────────────
#
# 예전에는 pubspec.yaml을 못 찾으면 첫 명령부터 실패했다. 웹·서버 레포에서는
# 아무것도 시작할 수 없었다는 뜻이다. 이제 무엇을 밟을 수 있는지부터 판정한다.

# projectops가 쓰는 프로젝트 타입 → 이 스킬의 타겟.
# 한 타입이 여러 타겟을 줄 수 있다(node는 웹일 수도 서버일 수도 있다).
_TYPE_TO_TARGET = {
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
    """version.yml의 project_types. projectops가 통합된 레포면 이미 있다.

    yaml 파서를 쓰지 않는다 — 이 스크립트는 표준 라이브러리만으로 돌아야 한다.
    """
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


def _marker_targets(root: Path) -> dict:
    """파일로 추론한다. version.yml이 없는 레포(대부분의 남의 프로젝트)를 위한 길이다."""
    found: dict[str, list[str]] = {}

    def add(target: str, why: str):
        found.setdefault(target, []).append(why)

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
        # 웹 프레임워크가 보이면 화면이 있다는 뜻이다
        if re.search(r'"(react|next|vue|svelte|@angular/core)"\s*:', body):
            add("web", rel)
        # 서버 프레임워크는 화면 없이 API만 있을 수 있다
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


def detect_targets(root: Path) -> dict:
    """무엇을 밟을 수 있는지. 앞에서 정해지면 뒤는 보지 않는다."""
    types = _version_yml_types(root)
    if types:
        targets: list[str] = []
        for ty in types:
            for tg in _TYPE_TO_TARGET.get(ty, []):
                if tg not in targets:
                    targets.append(tg)
        if targets:
            return {"targets": targets, "source": "version.yml", "project_types": types}

    found = _marker_targets(root)
    targets = [tg for tg in TARGETS if tg in found]
    return {"targets": targets, "source": "marker" if targets else "none",
            "evidence": {k: v for k, v in found.items()}}


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


def _api_base_urls(root: Path) -> list[str]:
    """.env와 dart 설정에서 http(s) 주소를 모은다. 기기가 어느 서버를 보는지
    모르면 DB 대조 대상을 못 정한다."""
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


def _devices() -> dict:
    android: list[str] = []
    adb = _sdk_tool("adb")
    if adb:
        for line in _run([adb, "devices"]).splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                android.append(parts[0])
    ios: list[str] = []
    if shutil.which("xcrun"):
        for line in _run(["xcrun", "simctl", "list", "devices", "booted"]).splitlines():
            m = re.match(r"\s+(.+?)\s+\(([\w-]{36})\)\s+\(Booted\)", line)
            if m:
                ios.append(f"{m.group(1)} [{m.group(2)}]")
    avds: list[str] = []
    emu = _sdk_tool("emulator")
    if emu:
        avds = [l.strip() for l in _run([emu, "-list-avds"]).splitlines()
                if l.strip() and not l.startswith("INFO")]
    return {"android": android, "ios_booted": ios, "android_avds": avds,
            "adb_path": adb, "emulator_path": emu}


# 이 skill이 쓰는 도구들. required=없으면 아무것도 못 한다.
_TOOLS = [
    ("adb", True, "Android 기기 제어",
     "Android Studio → SDK Manager → SDK Tools → Android SDK Platform-Tools"),
    ("emulator", False, "AVD 부팅 (이미 켜져 있으면 불필요)",
     "Android Studio → SDK Manager → SDK Tools → Android Emulator"),
    ("xcrun", False, "iOS 시뮬레이터 (macOS 전용)",
     "Xcode 설치 후 xcode-select --install"),
    ("ffmpeg", False, "녹화에서 프레임 추출 — 애니메이션을 수치로 검증할 때만",
     "brew install ffmpeg / apt install ffmpeg / winget install ffmpeg"),
]


def _has_pillow() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


def cmd_doctor(args) -> int:
    """실행 전에 무엇이 되고 무엇이 안 되는지 알려준다.

    없는 도구를 모른 채 시작하면 중간에 멈춘다. 특히 이미지 축소·녹화 분석은
    플랫폼마다 사정이 달라 미리 확인해야 한다.
    """
    checks = []
    missing_required = []
    for name, required, why, how in _TOOLS:
        path = _sdk_tool(name) if name in ("adb", "emulator") else shutil.which(name)
        ok = bool(path)
        if required and not ok:
            missing_required.append(name)
        checks.append({
            "tool": name, "found": ok, "path": path,
            "required": required, "why": why,
            **({} if ok else {"install": how}),
        })

    # 이미지 축소 수단 — 이슈에 첨부할 때 원본은 너무 크다
    if _has_pillow():
        shrink = "pillow"
    elif shutil.which("sips"):
        shrink = "sips (macOS)"
    elif shutil.which("ffmpeg"):
        shrink = "ffmpeg"
    else:
        shrink = None

    # 산출물 보호 상태 — 로그·스크린샷이 쌓이는 폴더에 방어가 있는지
    root = Path(args.root).resolve()
    guarded, unguarded = [], []
    for rel in list(_SCENARIO_DIRS) + ["docs/testing/screenshots"]:
        d = root / rel
        if not d.is_dir():
            continue
        made = _ensure_gitignore(d)
        (guarded if (d / ".gitignore").exists() else unguarded).append(
            f"{rel}{' (방금 생성)' if made else ''}")

    return emit({
        "ok": not missing_required,
        "code": "ok" if not missing_required else "missing_required_tool",
        "checks": checks,
        "output_guard": {"protected": guarded, "unprotected": unguarded},
        "image_resize": shrink or "없음 — 원본 크기로 커밋하게 된다",
        "pillow": _has_pillow(),
        "platform": sys.platform,
        "summary": (
            f"{sys.platform}: 필수 {'충족' if not missing_required else '부족(' + ','.join(missing_required) + ')'}"
            f" · 이미지 축소 {shrink or '불가'}"
        ),
        "next": None if not missing_required else "위 install 안내를 따라 설치한 뒤 다시 실행하세요",
    })


def cmd_shrink(args) -> int:
    """이슈 첨부용으로 이미지 긴 변을 줄인다.

    Pillow → sips(macOS) → ffmpeg 순으로 쓸 수 있는 것을 고른다. 세 가지 중
    하나만 있으면 되므로 특정 OS에 묶이지 않는다.
    """
    targets = [Path(p) for p in args.paths]
    missing = [str(p) for p in targets if not p.exists()]
    if missing:
        return emit({"ok": False, "code": "file_not_found", "error": f"없는 파일: {missing}"})

    done, method = [], None
    if _has_pillow():
        from PIL import Image
        method = "pillow"
        for f in targets:
            im = Image.open(f)
            im.thumbnail((args.max_side, args.max_side), Image.LANCZOS)
            im.save(f)
            done.append(str(f))
    elif shutil.which("sips"):
        method = "sips"
        for f in targets:
            _run(["sips", "-Z", str(args.max_side), str(f)])
            done.append(str(f))
    elif shutil.which("ffmpeg"):
        method = "ffmpeg"
        for f in targets:
            tmp = f.with_suffix(".shrink.png")
            _run(["ffmpeg", "-y", "-i", str(f), "-vf",
                  f"scale='min({args.max_side},iw)':-1", str(tmp)])
            if tmp.exists():
                tmp.replace(f)
                done.append(str(f))
    else:
        return emit({
            "ok": False, "code": "no_resize_tool",
            "error": "이미지를 줄일 수단이 없습니다",
            "hint": "pip install pillow (권장) 또는 ffmpeg 설치",
        })

    return emit({"files": done, "method": method,
                 "summary": f"{len(done)}장 축소 ({method}, 긴 변 {args.max_side}px)"})


def cmd_detect(args) -> int:
    """무엇을 밟을 수 있는지부터 판정하고, 타겟에 맞는 정보를 모아 돌려준다.

    예전에는 pubspec.yaml을 못 찾으면 여기서 실패해 웹·서버 레포에서는 아무것도
    시작할 수 없었다 (이슈 #586). 이제 Flutter가 없어도 계속 간다.
    """
    start = Path(args.path).resolve()
    # 레포 전체를 기준으로 본다 — 모노레포는 client/ · server/ 가 형제로 있다
    git_root = _run(["git", "-C", str(start), "rev-parse", "--show-toplevel"]).strip()
    root = Path(git_root) if git_root else start

    det = detect_targets(root)
    targets = det["targets"]

    # 사용자가 지정했으면 그것만 본다
    if getattr(args, "target", None):
        if args.target not in TARGETS:
            return emit({"ok": False, "code": "unknown_target",
                         "error": f"target '{args.target}' 을 모릅니다",
                         "hint": f"{'·'.join(TARGETS)} 중 하나"})
        targets = [args.target]

    payload: dict = {
        "root": str(root),
        "targets": targets,
        "target_source": det["source"],
        "knowledge_dir": str(_home_dir(root)),
    }
    if det.get("project_types"):
        payload["project_types"] = det["project_types"]
    if det.get("evidence"):
        payload["evidence"] = det["evidence"]

    # ── 앱: 기기와 패키지 정보가 있어야 밟을 수 있다
    if "app" in targets:
        app_root = _find_flutter_root(root)
        dev = _devices()
        payload["app"] = {
            "flutter_root": str(app_root) if app_root else None,
            "android_package": _android_package(app_root) if app_root else None,
            "ios_bundle_id": _ios_bundle_id(app_root) if app_root else None,
            "devices": dev,
        }
        payload["api_base_urls"] = _api_base_urls(app_root) if app_root else []
        # 기존 호출부가 쓰던 자리를 그대로 남긴다 — 문서·스킬이 이 키를 가리킨다
        payload["flutter_root"] = payload["app"]["flutter_root"]
        payload["android_package"] = payload["app"]["android_package"]
        payload["ios_bundle_id"] = payload["app"]["ios_bundle_id"]
        payload["devices"] = dev

    # ── 웹: 어디로 들어가는지와 브라우저가 준비됐는지
    if "web" in targets:
        payload["web"] = {
            "base_urls": _web_base_urls(root),
            "playwright": _playwright_state(),
        }

    # ── 서버: API 주소와 DB 접속 경로
    if "server" in targets:
        conf = _backend_conf(root)
        payload["server"] = {
            "config_file": conf.get("file"),
            "base_urls": _api_base_urls(root),
            "db": {k: v for k, v in (conf.get("db") or {}).items() if k != "password"},
        }

    payload["summary"] = (
        f"{root.name}: 타겟={'·'.join(targets) if targets else '없음'} ({det['source']})")
    payload["next"] = _detect_next(targets, payload)
    return emit(payload)


def _detect_next(targets: list[str], payload: dict) -> str | None:
    """다음에 무엇을 해야 하는지. 막힌 곳을 먼저 알려준다."""
    if not targets:
        return ("무엇을 밟을지 알 수 없습니다 — --target app|web|server 로 직접 알려주세요")
    if "app" in targets:
        dev = payload.get("devices") or {}
        if not (dev.get("android") or dev.get("ios_booted")):
            return "devices  # 기기가 없습니다. AVD를 부팅하세요"
    if "web" in targets and not (payload.get("web", {}).get("playwright", {}).get("ready")):
        return "web 타겟을 밟으려면 Playwright가 필요합니다 — references/target-web.md 참조"
    return None


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
        # dev 스크립트의 포트 지정에서 끌어온다
        for m in re.finditer(r"-p\s*(\d{4,5})|--port[= ](\d{4,5})", body):
            port = m.group(1) or m.group(2)
            u = f"http://localhost:{port}"
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


def _playwright_state() -> dict:
    """웹을 밟을 준비가 됐는지. 없으면 무엇을 하면 되는지까지 알려준다."""
    ok, err = _require_playwright()
    if err:
        return {"ready": False, "reason": err["error"], "fix": err["fix"],
                "ask_user": err["ask_user"]}
    return {"ready": True, "venv": str(_VENV_DIR) if _venv_python() else "시스템"}


def cmd_devices(args) -> int:
    dev = _devices()
    n = len(dev["android"]) + len(dev["ios_booted"])
    return emit({
        **dev,
        "summary": f"사용 가능한 기기 {n}대",
        "next": None if n else "emulator -avd {AVD명} 으로 부팅하세요",
    })


# =========================================================================
# 부트스트랩 — 이 앱이 어떻게 생겼는지 코드에서 읽어낸다
# =========================================================================

_APP_MAP_FILE = "app-map.json"
_SHARED_DIR = "_shared"
_FLOWS_DIR = "flows"


def _scan_routes(lib: Path) -> list[dict]:
    """라우트 상수와 GoRoute 경로를 모은다.

    경로 자체가 기능 계층을 담고 있는 경우가 많다(`/guardian/routine/input`).
    첫 세그먼트를 그룹 후보로 삼아 어느 폴더에 시나리오를 둘지 정하는 데 쓴다.
    """
    routes: list[dict] = []
    seen = set()
    for f in lib.rglob("*.dart"):
        if ".g.dart" in f.name or ".freezed.dart" in f.name:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in re.finditer(r"static const (\w+)\s*=\s*'(/[^']*)'", text):
            name, path = m.group(1), m.group(2)
            if path in seen:
                continue
            seen.add(path)
            seg = [x for x in path.split("/") if x]
            routes.append({"const": name, "path": path,
                           "group": seg[0] if seg else "root"})
    return sorted(routes, key=lambda r: r["path"])


def _scan_feature_groups(lib: Path) -> list[str]:
    d = lib / "features"
    if not d.is_dir():
        return []
    return sorted(x.name for x in d.iterdir()
                  if x.is_dir() and not x.name.startswith("."))


def _scan_screens(lib: Path) -> list[dict]:
    out = []
    for f in sorted(lib.rglob("*_screen.dart")):
        rel = f.relative_to(lib)
        parts = rel.parts
        group = parts[1] if len(parts) > 2 and parts[0] == "features" else "core"
        out.append({"file": str(rel), "group": group,
                    "name": f.stem.replace("_screen", "")})
    return out


def _scan_auth(lib: Path) -> dict:
    """로그인 방식을 추정한다. 앱마다 다르므로 단정하지 않고 근거를 함께 남긴다."""
    providers, evidence = [], []
    for f in lib.rglob("*.dart"):
        if ".g.dart" in f.name:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        m = re.search(r"enum\s+\w*(?:OAuth|Social|Login)\w*Provider\s*\{([^}]*)\}",
                      text, re.S)
        if m:
            body = m.group(1)
            providers = [x.strip() for x in re.findall(r"^\s*(\w+)[,;]", body, re.M)]
            evidence.append(str(f.relative_to(lib)))
            break
    kind = "social" if providers else ("unknown" if not evidence else "custom")
    return {"kind": kind, "providers": providers, "evidence": evidence}


def _scan_web(root: Path) -> dict:
    """웹의 페이지·라우트를 훑는다.

    프레임워크마다 규칙이 달라 완벽할 수 없다. 시나리오를 쓸 때 "어디가 있더라"를
    줄여 주는 것이 목적이고, 판단은 사람이 한다.
    """
    pages, routes = [], []
    skip = ("node_modules", "build", "dist", ".next", ".git")
    for d in ("app", "pages", "src"):
        base = root / d
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*")):
            if not f.is_file() or any(x in f.parts for x in skip):
                continue
            if f.suffix not in (".tsx", ".jsx", ".ts", ".js", ".vue", ".svelte"):
                continue
            rel = str(f.relative_to(root))
            # Next.js app/pages 규칙: 파일 위치가 곧 경로다
            if d in ("app", "pages") and f.stem in ("page", "index", "route"):
                seg = f.parent.relative_to(base)
                routes.append({"path": "/" + str(seg).replace(".", "").strip("/"), "file": rel})
            elif "page" in f.stem.lower() or "screen" in f.stem.lower() or "view" in f.stem.lower():
                pages.append({"name": f.stem, "file": rel})
            # 라우터 정의에서 경로를 뽑는다
            try:
                body = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for m in re.finditer(r"""path:\s*['"]([^'"]+)['"]""", body):
                routes.append({"path": m.group(1), "file": rel})
    # 같은 경로가 여러 번 잡히므로 정리한다
    seen, uniq = set(), []
    for r in routes:
        if r["path"] in seen:
            continue
        seen.add(r["path"])
        uniq.append(r)
    return {"routes": uniq[:80], "pages": pages[:80]}


def _scan_server(root: Path) -> dict:
    """서버의 엔드포인트를 훑는다. 서버 시나리오는 이 목록에서 시작한다."""
    eps = []
    skip = ("node_modules", "build", "dist", ".venv", ".git", "target")
    rules = [
        # Spring
        (r'@(Get|Post|Put|Delete|Patch)Mapping\(\s*(?:value\s*=\s*)?"([^"]*)"', "spring"),
        (r'@RequestMapping\(\s*(?:value\s*=\s*)?"([^"]*)"', "spring"),
        # Express·Nest
        (r"""\b(?:app|router)\.(get|post|put|delete|patch)\(\s*['"]([^'"]+)['"]""", "node"),
        # FastAPI·Flask
        (r"""@(?:app|router)\.(get|post|put|delete|patch)\(\s*['"]([^'"]+)['"]""", "python"),
    ]
    for d in ("src", "app", "api", "."):
        base = root / d if d != "." else root
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*")):
            if not f.is_file() or any(x in f.parts for x in skip):
                continue
            if f.suffix not in (".java", ".kt", ".py", ".ts", ".js"):
                continue
            try:
                body = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            rel = str(f.relative_to(root))
            for pat, kind in rules:
                for m in re.finditer(pat, body):
                    g = m.groups()
                    method = g[0].upper() if len(g) > 1 else "ANY"
                    path = g[-1]
                    eps.append({"method": method, "path": path, "file": rel, "kind": kind})
            if len(eps) > 300:
                break
        if d == ".":
            break
    seen, uniq = set(), []
    for e in eps:
        key = (e["method"], e["path"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)
    return {"endpoints": uniq[:120]}


def cmd_bootstrap(args) -> int:
    """앱 구조를 스캔해 app-map.json에 적고 기능별 폴더를 만든다.

    매번 코드를 뒤져 라우트를 찾지 않도록 한 번 읽어 둔다. 폴더를 미리 만들어 두면
    새 기능의 시나리오를 어디에 넣을지 고민할 일이 없다 — 코드와 같은 이름이다.
    """
    import json
    from datetime import date

    root = Path(args.path).resolve()
    target = getattr(args, "target", None) or (detect_targets(root)["targets"] or ["app"])[0]

    groups: list[str] = []
    extra: dict = {}
    flutter_root = None
    if target == "app":
        flutter_root = _find_flutter_root(root)
        if flutter_root is None:
            return emit({"ok": False, "code": "flutter_project_not_found",
                         "error": f"{root} 아래에서 Flutter 프로젝트를 찾지 못했습니다",
                         "hint": "--target web|server 로 대상을 알려주세요"})
        lib = flutter_root / "lib"
        groups = _scan_feature_groups(lib)
        extra = {"routes": _scan_routes(lib), "screens": _scan_screens(lib),
                 "auth": _scan_auth(lib)}
    elif target == "web":
        extra = _scan_web(root)
        # 경로 첫 조각을 기능 그룹으로 삼는다 — 앱의 lib/features 와 같은 역할이다
        for r in extra.get("routes", []):
            seg = r["path"].strip("/").split("/")[0]
            if seg and not seg.startswith((":", "*", "[")) and seg not in groups:
                groups.append(seg)
    else:  # server
        extra = _scan_server(root)
        for e in extra.get("endpoints", []):
            parts = [x for x in e["path"].strip("/").split("/") if x and not x.startswith(("{", ":"))]
            seg = parts[1] if len(parts) > 1 and parts[0] == "api" else (parts[0] if parts else "")
            if seg and seg not in groups:
                groups.append(seg)
    groups = groups[:20]

    d = _scenario_dir(root, create=True)
    (d / _SHARED_DIR).mkdir(exist_ok=True)
    flows = d / _FLOWS_DIR
    flows.mkdir(exist_ok=True)
    made = []
    for g in groups:
        sub = flows / g
        if not sub.exists():
            sub.mkdir()
            made.append(g)
        keep = sub / ".gitkeep"
        if not any(sub.iterdir()):
            keep.touch()

    app_map = {
        "scanned": date.today().isoformat(),
        "target": target,
        "flutter_root": (str(flutter_root.relative_to(root))
                         if flutter_root and flutter_root != root else
                         ("." if flutter_root else None)),
        "feature_groups": groups,
        # 타겟마다 담기는 것이 다르다 — app은 라우트·화면·인증, web은 라우트·페이지,
        # server는 엔드포인트. 없는 키를 억지로 만들지 않는다.
        **extra,
    }
    (d / _APP_MAP_FILE).write_text(
        json.dumps(app_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 로그인 전제 템플릿을 제안한다 — 방식이 프로젝트마다 다르므로 만들지는 않는다
    auth = extra.get("auth") or {}
    if auth.get("kind") == "social" and auth.get("providers"):
        hint = (f"_shared/login-{auth['providers'][0]}.json 부터 만드세요 "
                f"(감지된 방식: {', '.join(auth['providers'])})")
    else:
        hint = "_shared/login.json 을 만들어 로그인 단계를 한 곳에 두세요"

    # 타겟마다 셀 것이 다르다. 없는 것을 0으로 적으면 "못 찾았다"와 구분되지 않는다.
    counts = {}
    for key in ("routes", "screens", "pages", "endpoints"):
        if key in extra:
            counts[f"{key}_count"] = len(extra[key])
    made_summary = " · ".join(f"{k.replace('_count','')} {v}개" for k, v in counts.items())

    # 무엇을 근거로 찾았는지 함께 준다. 이것이 없으면 빈손일 때 "이 프로젝트엔 화면이 없다"로
    # 오해한다 — 실제로는 구조가 달라서 못 찾은 것이다 (이슈 #589).
    _LOOKED_FOR = {
        "app": ["lib/features/ 폴더", "*_screen.dart 파일명",
                "static const x = '/...' 형태의 라우트"],
        "web": ["app/·pages/·src/ 폴더", "Next.js 파일 규칙(page·index·route)",
                "path: '...' 형태의 라우트"],
        "server": ["@GetMapping 등 Spring 애너테이션", "app/router.get(...) 형태",
                   "@app.get(...) 형태"],
    }
    empty = not groups and not any(extra.get(k) for k in
                                   ("routes", "screens", "pages", "endpoints"))

    return emit({
        "target": target,
        "app_map": str((d / _APP_MAP_FILE).relative_to(root))
                   if str(d).startswith(str(root)) else str(d / _APP_MAP_FILE),
        "feature_groups": groups,
        "created_folders": made,
        # 정답이 아니라 후보다. 판단은 이것을 받는 쪽이 한다.
        "looked_for": _LOOKED_FOR.get(target, []),
        "is_guess": True,
        **({"empty_hint": (
            "흔한 규칙으로 찾아봤지만 아무것도 없습니다. 이 프로젝트가 다른 구조를 쓸 수 "
            "있으니 코드를 직접 읽어 확인하세요 — 화면이 없다는 뜻이 아닙니다")} if empty else {}),
        **({"auth": auth} if auth else {}),
        **counts,
        "summary": (f"[{target}] 기능 {len(groups)}개"
                    + (f" · {made_summary}" if made_summary else "")
                    + (f" · 인증 {auth['kind']}({len(auth.get('providers') or [])}종)"
                       if auth else "")),
        "next": hint,
    })


# =========================================================================
# 시나리오 — 프로젝트마다 다른 "무엇을 어떻게 밟을지"를 파일로 둔다
# =========================================================================

# 예전 위치. 이제 쓰지 않지만, 여기 있던 것을 홈으로 옮겨 오기 위해 남겨 둔다.
_SCENARIO_DIRS = ("docs/testing/e2e", ".projectops/e2e")

# 이전이 일어났을 때 사용자에게 알릴 말. 명령 결과에 실어 보낸다.
_MIGRATION_NOTES: list[str] = []

def _template_for(target: str) -> dict:
    """타겟에 맞는 시나리오 본보기. 타겟마다 밟는 단위와 판정 근거가 다르다."""
    base = {
        "name": "{무엇을 밟는지 한 줄}",
        "description": "{왜 이 경로가 중요한지}",
        "target": target,
        "mode": "e2e",
        "precondition": None,   # 예: "_shared/login-kakao" — 앞에 붙일 흐름
        "steps": [dict(_STEP_TEMPLATES[target])],
    }
    if target == "app":
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
        "expect_device": ["{로그에서 확인할 키. 예: elum.refreshToken}"],
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

# ── 두 개의 독립 축 (이슈 #586) ──────────────────────────────────────────
#
# target = 무엇으로 조작하나. mode = 무슨 종류의 테스트인가.
# 둘을 한 축으로 묶으면 "웹에서 밟으며 서버 DB를 확인"하는 조합이 표현되지 않는다.
# target이 정하는 것은 `do`를 누가 실행하느냐뿐이고, expect_*는 타겟과 무관하게 붙는다.
TARGETS = ("app", "web", "server")
MODES = ("e2e", "load")

# 값이 없는 예전 시나리오는 여기로 떨어진다 — 기존 파일을 한 글자도 고치지 않기 위해서다.
DEFAULT_TARGET = "app"
DEFAULT_MODE = "e2e"

# 타겟별로 인정하는 기대 결과. 하나도 없으면 "화면이 떴으니 통과"로 끝나므로 막는다.
_EXPECT_KEYS = {
    "app": ("expect_screen", "expect_device", "expect_server"),
    "web": ("expect_screen", "expect_url", "expect_text", "expect_server"),
    "server": ("expect_status", "expect_json", "expect_server"),
}


def scenario_target(data: dict) -> str:
    """시나리오의 조작 대상. 모르는 값이면 기본값으로 떨어뜨리지 않고 그대로 돌려준다
    — _validate가 잡아서 사용자에게 알려야 조용히 엉뚱한 것을 밟지 않는다."""
    return data.get("target") or DEFAULT_TARGET


def scenario_mode(data: dict) -> str:
    return data.get("mode") or DEFAULT_MODE


def _ensure_gitignore(d: Path) -> bool:
    """산출물 폴더에 .gitignore를 보장한다. 새로 만들었으면 True.

    폴더를 처음 만들 때만 넣으면, **이미 폴더가 있는 프로젝트에는 영원히 생기지
    않는다.** 실제로 그래서 한 프로젝트가 방어 없이 쓰이고 있었다. 폴더를 건드리는
    모든 경로에서 확인한다 — 파일이 이미 있으면 덮지 않으므로 손으로 고친 내용은 남는다.
    """
    if not d.is_dir():
        return False
    gi = d / ".gitignore"
    if gi.exists():
        # 예전 판은 `!*.json` 으로 새 파일까지 전부 추적하게 만들었다. 이미 깔린
        # 프로젝트를 그대로 두면 그 구멍이 영영 남으므로, **이 스킬이 쓴 파일일 때만**
        # 갈아끼운다. 손으로 쓴 .gitignore 는 건드리지 않는다.
        try:
            body = gi.read_text(encoding="utf-8")
        except OSError:
            return False
        if _GITIGNORE_UNSAFE in body and ("pro-agent-test" in body or "pro-flutter-e2e" in body):
            gi.write_text(_GITIGNORE, encoding="utf-8")
            return True
        return False
    gi.write_text(_GITIGNORE, encoding="utf-8")
    return True


def _repo_key(root: Path) -> str:
    """프로젝트를 가리키는 키. git remote의 owner/repo를 쓴다.

    **경로를 키로 쓰면 안 된다.** 워크트리마다 경로가 달라 같은 프로젝트가 여러 개로
    갈라지고, 그러면 쌓은 지식이 워크트리 수만큼 쪼개진다 — 옮기려는 이유가 그것이다.
    remote가 없는(로컬 전용) 저장소는 폴더명으로 떨어진다.
    """
    url = _run(["git", "-C", str(root), "remote", "get-url", "origin"]).strip()
    m = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?$", url) if url else None
    if m:
        return f"{m.group(1)}__{m.group(2)}"
    return re.sub(r"[^A-Za-z0-9._-]+", "-", root.name).strip("-") or "unknown"


def _home_dir(root: Path) -> Path:
    """쌓은 것을 두는 곳. 프로젝트 밖(홈)이라 워크트리를 만들어도 살아남는다."""
    return Path.home() / ".projectops" / "agent-test" / _repo_key(root)


def _migrate_from_project(root: Path, home: Path) -> str | None:
    """예전 위치(프로젝트 안)에 있던 것을 홈으로 한 번 옮긴다.

    **복사가 아니라 이동이다.** 두 곳에 남으면 어느 쪽이 최신인지 알 수 없어진다.
    옮겼다는 사실은 호출부가 사용자에게 알린다 — 프로젝트 폴더에서 파일을 찾다가
    없어서 당황하지 않게.
    """
    for rel in _SCENARIO_DIRS:
        old_dir = root / rel
        if not old_dir.is_dir():
            continue
        moved = []
        home.mkdir(parents=True, exist_ok=True)
        for item in old_dir.iterdir():
            if item.name == ".gitignore":
                continue        # 예전 위치를 막던 규칙은 따라갈 이유가 없다
            dest = home / item.name
            if dest.exists():
                continue        # 홈이 이미 갖고 있으면 그쪽이 최신이다
            shutil.move(str(item), str(dest))
            moved.append(item.name)
        if moved:
            note = f"{old_dir} → {home} ({', '.join(sorted(moved))})"
            # 남은 것이 우리가 쓴 .gitignore뿐이면 알려준다. **지우지는 않는다** —
            # 사용자 저장소의 파일을 묻지 않고 없애지 않는다는 규칙이 우선이다.
            rest = [f.name for f in old_dir.iterdir()]
            if rest == [".gitignore"]:
                body = (old_dir / ".gitignore").read_text(encoding="utf-8", errors="replace")
                if _GITIGNORE_MARK in body or _GITIGNORE_MARK_LEGACY in body:
                    note += f" · 빈 폴더가 남았습니다: {old_dir} (지워도 됩니다)"
            return note
    return None


def _scenario_dir(root: Path, create: bool = False) -> Path:
    """시나리오·지식을 둘 곳.

    예전에는 프로젝트 안(`docs/testing/e2e`)이었는데, 그 폴더는 .gitignore로 추적에서
    빠져 있어 **새 워크트리에 복사되지 않았다.** 이슈마다 워크트리를 만드는 흐름에서는
    이슈 하나가 끝날 때마다 쌓은 지식이 통째로 사라졌다 (이슈 #586).

    이제 홈에 두고 git remote로 프로젝트를 구분한다. 예전 위치에 있던 것은 처음 한 번
    자동으로 옮겨 온다.
    """
    home = _home_dir(root)
    if home.is_dir():
        return home
    note = _migrate_from_project(root, home)
    if note:
        _MIGRATION_NOTES.append(note)
        return home
    if create:
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
    mode = scenario_mode(data)
    if mode not in MODES:
        problems.append(f"mode '{mode}' 를 모릅니다 — {'·'.join(MODES)} 중 하나여야 합니다")
    elif mode == "load":
        # 축만 예약해 둔 상태다. 밟겠다고 나섰다가 중간에 멈추는 것보다 먼저 말해 준다.
        problems.append("mode 'load'(부하)는 아직 구현되지 않았습니다 — 다음 작업입니다")
    if mode == "load" and target != "server":
        problems.append("부하는 server 타겟에서만 의미가 있습니다 — UI로는 부하를 걸 수 없습니다")
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
        if not any(st.get(k) for k in expect_keys):
            problems.append(
                f"{i}번째 step({st.get('screen','?')})에 기대 결과가 없습니다 — "
                f"{'·'.join(k.replace('expect_', '') for k in expect_keys)} 중 하나는 "
                "있어야 통과 판정을 할 수 있습니다")
    return problems


def _scenario_files(d: Path) -> list[Path]:
    """시나리오 파일 목록. flows/ 하위와 _shared/ 를 함께 본다.

    app-map·learned 는 시나리오가 아니므로 제외한다.
    """
    if not d.is_dir():
        return []
    skip = {_APP_MAP_FILE, _NOTE_FILE}
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
            "summary": f"템플릿 생성: {f.relative_to(root)}",
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

# 기록에 들어가면 안 되는 것들. 테스트 산출물은 레포에 커밋되므로 한 번 들어가면
# 지워도 히스토리에 남는다 — 쓰기 전에 막는 편이 유일하게 확실하다.
_SECRET_PATTERNS = [
    (r'[\w.+-]+@[\w-]+\.[\w.]{2,}', "이메일 주소"),
    (r'01[016-9][-\s]?\d{3,4}[-\s]?\d{4}', "전화번호"),
    (r'eyJ[\w-]{10,}\.[\w-]{10,}', "JWT 토큰"),
    (r'(?i)\b(password|passwd|비밀번호|비번)\b\s*[:=]?\s*\S{4,}', "비밀번호"),
    (r'(?i)\b(secret|api[_-]?key|access[_-]?token)\b\s*[:=]\s*\S{8,}', "비밀 값"),
]


def _find_secrets(text: str) -> list[str]:
    import re as _re
    found = []
    for pattern, label in _SECRET_PATTERNS:
        m = _re.search(pattern, text)
        if m:
            sample = m.group(0)
            masked = sample[:3] + "***" if len(sample) > 3 else "***"
            found.append(f"{label}({masked})")
    return found


# 산출물 폴더에 함께 두는 .gitignore.
#
# **기본을 "올리지 않는다"로 둔다.** 예전에는 부산물만 골라 막고 `!*.json` 으로 나머지를
# 되살렸는데, 그 한 줄이 새로 생기는 파일까지 전부 추적 대상으로 만들었다. 실제로
# 서버 주소가 적힌 파일이 공개 레포에 올라갈 뻔했다. 무엇이 생길지 미리 다 알 수 없으므로
# 막는 쪽을 기본값으로 둔다 — 올리고 싶은 것이 생기면 그때 한 줄씩 예외를 적는다.
_GITIGNORE_MARK = "# pro-agent-test — 산출물 폴더"
# 옛 이름으로 깔린 프로젝트가 이미 있다. 마커를 갈아끼우면 우리가 쓴 파일을 남의 것으로
# 오해해 손대지 않게 되므로, 알아보기만은 계속 한다 (이슈 #586 개명).
_GITIGNORE_MARK_LEGACY = "# pro-flutter-e2e — 산출물 폴더"

_GITIGNORE = f"""{_GITIGNORE_MARK}
#
# 이 폴더에서 나오는 것들에는 테스트 계정·토큰·서버 주소·로그인 화면 캡처가 섞인다.
# 그래서 **기본은 올리지 않는다.** 팀과 나눠야 할 파일이 생기면 아래에 한 줄씩 적는다.
#
#   !flows/auth/social-signup.json
#
# 적기 전에 그 파일을 열어 계정·토큰·주소가 없는지 눈으로 본다.

*
# 폴더 자체는 막지 않는다. 이 줄이 없으면 `!하위폴더/파일` 예외가 통하지 않는다 —
# git은 제외된 폴더 안을 아예 들여다보지 않기 때문이다. (폴더 안 파일은 위 `*`가 계속 막는다)
!*/

!.gitignore
!README.md
"""

# 예전 판(`!*.json` 으로 전부 되살리던 것)을 알아보는 흔적.
_GITIGNORE_UNSAFE = "!*.json"


def _note_path(root: Path, create: bool = False) -> Path:
    return _scenario_dir(root, create) / _NOTE_FILE


# 이 파일이 담는 구조의 판. 필드를 없애는 변경을 할 때만 올린다.
_NOTE_SCHEMA = 1


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
            "screens": notes.get("screens", {}),
            "pitfalls": notes.get("pitfalls", []),
            "pitfalls_to_promote": [
                x for x in notes.get("pitfalls", [])
                if x.get("scope", "project") != "project"
            ],
            "runs": notes.get("runs", [])[-5:],
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
        entry = notes.setdefault("screens", {}).setdefault(args.name, {})
        entry["anchor"] = args.anchor          # 이 화면임을 알아보는 단서
        if args.taps:
            # "라벨=x,y" 형태를 그대로 보관한다. 해상도가 바뀌면 다시 재야 하므로
            # 절대 좌표가 아니라 기준 해상도와 함께 남긴다.
            entry["taps"] = dict(t.split("=", 1) for t in args.taps)
        if args.screen_size:
            entry["measured_on"] = args.screen_size
        entry["updated"] = date.today().isoformat()

    elif args.action == "pitfall":
        if not args.text:
            return emit({"ok": False, "code": "args_required", "error": "--text 가 필요합니다"})
        secrets = _find_secrets(args.text)
        if secrets:
            return emit({
                "ok": False, "code": "secret_detected",
                "error": f"기록하려는 내용에 {', '.join(secrets)}이(가) 들어 있습니다",
                "hint": ("이 파일은 레포에 커밋되므로 한 번 들어가면 히스토리에 남습니다. "
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
        "summary": f"{args.action} 기록 완료 — {f.relative_to(root)}",
        "next": "커밋해야 다음 사람도 씁니다",
    })


# =========================================================================
# 엣지케이스 — 코드에서 "밟아야 할 실패 경로"를 뽑아낸다
# =========================================================================

# (정규식, 무엇을 밟아야 하는가, 어떻게 만드는가)
_EDGE_RULES = [
    (r'catch\s*\(|on\s+\w*Exception', "예외 경로",
     "이 예외를 실제로 일으켜 화면이 무엇을 보여주는지 본다"),
    (r'DioException|SocketException|TimeoutException|HttpException', "네트워크 실패",
     "svc wifi disable && svc data disable 로 끊고 밟는다"),
    (r'\.isEmpty|length\s*==\s*0|\bemptyState\b|비어', "빈 목록",
     "데이터가 0건인 계정으로 들어가 로딩과 구분되는 화면이 있는지 본다"),
    (r'Permission\.|requestPermission|permission_handler', "권한 거부",
     "pm revoke 로 권한을 뺏고 앱이 죽지 않는지, 우회 경로를 주는지 본다"),
    (r'\bnull\b\s*\?\?|\?\?\s|\bfallback\b|폴백', "폴백 값",
     "폴백이 실제로 쓰이는 상황을 만들어 그 값이 맞는지 본다"),
    (r'errorCode|error_code|에러\s*코드|E-\d{3,}', "에러 코드 노출",
     "실패를 일으켜 화면에 식별자가 보이는지 본다 — 제보 추적에 필요하다"),
    (r'expire|만료|refreshToken|재발급', "토큰 만료",
     "서버에서 토큰을 폐기하고 앱이 갱신 또는 재로그인으로 가는지 본다"),
    (r'retry|재시도|다시\s*시도', "재시도",
     "실패 상태에서 재시도가 실제로 동작하는지 본다"),
]


def cmd_edges(args) -> int:
    """코드를 훑어 밟아야 할 실패 경로를 제안한다.

    해피 패스는 개발자가 이미 수십 번 밟는다. 버그는 catch 블록과 폴백 안에 있는데,
    그 코드는 대개 한 번도 실행되지 않은 채 배포된다. 여기서 목록을 뽑아 Phase 1의
    단계 목록에 넣는다.

    판단은 하지 않는다 — 후보를 모아 줄 뿐이고, 무엇을 밟을지는 사람이 고른다.
    """
    root = Path(args.path).resolve()
    target = getattr(args, "target", None) or (detect_targets(root)["targets"] or ["app"])[0]

    # 타겟마다 코드가 사는 곳과 확장자가 다르다. 앱만 훑으면 웹·서버에서는 아무것도 못 준다.
    scan_dirs: list[Path] = []
    exts: tuple[str, ...] = ()
    if target == "app":
        lib = root / "lib"
        if not lib.is_dir():
            found = _find_flutter_root(root)
            lib = (found / "lib") if found else None
        if not lib or not lib.is_dir():
            return emit({"ok": False, "code": "lib_not_found",
                         "error": f"{root} 아래에서 lib/ 를 찾지 못했습니다",
                         "hint": "--target web|server 로 대상을 알려주세요"})
        scan_dirs, exts = [lib], (".dart",)
    elif target == "web":
        for name in ("src", "app", "pages", "components", "lib"):
            d = root / name
            if d.is_dir():
                scan_dirs.append(d)
        exts = (".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte")
    else:  # server
        for name in ("src", "app", "api"):
            d = root / name
            if d.is_dir():
                scan_dirs.append(d)
        exts = (".java", ".kt", ".py", ".ts", ".js")

    if not scan_dirs:
        return emit({"ok": False, "code": "source_dir_not_found",
                     "error": f"{root} 아래에서 훑을 소스 폴더를 찾지 못했습니다",
                     "hint": "코드가 있는 경로를 --path 로 지정하세요"})

    hits: dict[str, list[dict]] = {}
    scanned = 0
    # 정규식으로 흔한 모양을 찾을 뿐이다. 여기 없다고 없는 것이 아니다.
    files = [f for d in scan_dirs for f in sorted(d.rglob("*"))
             if f.is_file() and f.suffix in exts
             and not any(x in f.parts for x in ("node_modules", "build", ".venv", "dist"))]
    for f in files[:4000]:      # 큰 저장소에서 끝없이 도는 것을 막는다
        if ".g.dart" in f.name or ".freezed.dart" in f.name:
            continue        # 생성 파일은 사람이 밟을 경로가 아니다
        scanned += 1
        try:
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            for pattern, label, how in _EDGE_RULES:
                if re.search(pattern, line):
                    hits.setdefault(label, []).append({
                        "file": str(f.relative_to(root)),
                        "line": i,
                        "code": line.strip()[:100],
                        "how": how,
                    })
                    break

    summary_rows = sorted(((k, len(v)) for k, v in hits.items()),
                          key=lambda x: -x[1])
    return emit({
        "scanned_files": scanned,
        "categories": [
            {"edge": k, "count": len(v), "how": v[0]["how"],
             "samples": v[:args.samples]}
            for k, v in sorted(hits.items(), key=lambda x: -len(x[1]))
        ],
        "summary": f"{scanned}개 파일 · " + ", ".join(f"{k} {n}" for k, n in summary_rows[:5]),
        "next": "밟을 것을 골라 시나리오의 steps 에 넣으세요 — 전부 밟을 필요는 없습니다",
    })


# =========================================================================
# 백엔드 대조 — 화면만 봐서는 못 잡는 것들
# =========================================================================
#
# 앱을 밟는 것만으로는 "서버에 무엇이 남았는가"와 "앱이 무엇을 보냈는가"를 알 수 없다.
# 실제로 이 두 가지를 봐야만 드러난 버그들이 있었다.
#   - 탈퇴가 서버에서 실패했는데 앱은 성공처럼 굴었다 (DB에 계정이 남아 있어 알았다)
#   - 화면에 없던 선택 동의가 true로 전송됐다 (요청 본문 로그에서 드러났다)
#   - 탈퇴 후 참조가 끊긴 행이 남았다 (고아 행을 훑어야 보인다)
#
# 매번 psql·curl을 조립하지 않도록 여기에 둔다. 접속 정보는 **파일에서 읽기만** 하고
# 출력·기록 어디에도 남기지 않는다.

_SECRET_KEYS = ("password", "secret", "token", "key")


def _mask(v: str) -> str:
    return "***" if v else ""


def _read_spring_config(yml: Path) -> dict:
    """Spring application-*.yml 에서 DB 접속 정보와 관리자 계정을 읽는다.

    yaml 모듈에 의존하지 않는다 — 표준 라이브러리만으로 돌아야 어느 환경에서든 뜬다.
    필요한 건 몇 줄뿐이라 정규식으로 충분하다.
    """
    text = yml.read_text(encoding="utf-8", errors="replace")
    out: dict = {"db": None, "admin": None, "base_url": None}

    m = re.search(r"jdbc:(postgresql|mysql)://([^:/\s]+):(\d+)/(\S+?)\s*$",
                  text, re.M)
    if m:
        ds = re.search(r"datasource:(.{0,400})", text, re.S)
        blk = ds.group(1) if ds else text
        user = re.search(r"username:\s*(\S+)", blk)
        pw = re.search(r"password:\s*(\S+)", blk)
        out["db"] = {
            "engine": m.group(1),
            "host": m.group(2),
            "port": m.group(3),
            "name": m.group(4).strip("\"'"),
            "user": user.group(1).strip("\"'") if user else None,
            "password": pw.group(1).strip("\"'") if pw else None,
        }

    am = re.search(r"admin:\s*\n\s*accounts:\s*\n\s*-\s*username:\s*(\S+)\s*\n\s*password:\s*(\S+)",
                   text)
    if am:
        out["admin"] = {"username": am.group(1).strip("\"'"),
                        "password": am.group(2).strip("\"'")}

    bu = re.search(r"servers:\s*\n\s*-\s*url:\s*(\S+)", text)
    if bu:
        out["base_url"] = bu.group(1).strip("\"'")
    return out


def _find_spring_config(root: Path) -> Path | None:
    """운영 프로필을 먼저 찾는다 — 실제로 대조해야 하는 곳은 거기다."""
    for pat in ("application-prod.yml", "application-prod.yaml",
                "application.yml", "application.yaml"):
        hits = sorted(root.glob(f"**/src/main/resources/{pat}"))
        if hits:
            return hits[0]
    return None


def _psql(db: dict, sql: str, timeout: int = 40) -> tuple[bool, str]:
    exe = shutil.which("psql")
    if not exe:
        return False, "psql 이 없습니다 (brew install libpq 또는 postgresql-client)"
    env = dict(os.environ,
               PGHOST=db["host"], PGPORT=str(db["port"]), PGDATABASE=db["name"],
               PGUSER=db["user"] or "", PGPASSWORD=db["password"] or "")
    try:
        r = subprocess.run([exe, "-tAF", "\t", "-c", sql],
                           env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"psql 응답 없음 ({timeout}초)"
    if r.returncode != 0:
        return False, (r.stderr or "").strip()[:300]
    return True, r.stdout


_ORPHAN_SQL_TABLES = """
select c.table_name, c.column_name
from information_schema.columns c
join information_schema.tables t
  on t.table_name = c.table_name and t.table_schema = c.table_schema
where c.table_schema = 'public' and t.table_type = 'BASE TABLE'
  and c.column_name like '%\\_id'
"""

_ORPHAN_SQL_FK = """
select kcu.table_name, kcu.column_name, ccu.table_name, rc.delete_rule
from information_schema.table_constraints tc
join information_schema.key_column_usage kcu
  on tc.constraint_name = kcu.constraint_name
join information_schema.constraint_column_usage ccu
  on tc.constraint_name = ccu.constraint_name
join information_schema.referential_constraints rc
  on tc.constraint_name = rc.constraint_name
where tc.constraint_type = 'FOREIGN KEY' and tc.table_schema = 'public'
"""


def _orphan_scan(db: dict) -> dict:
    """참조가 끊긴 행을 찾는다.

    외래키가 **없는** `*_id` 컬럼이 진짜 위험한 곳이다. DB가 대신 지워 주지 않으므로
    삭제 코드에서 빠뜨리면 조용히 남는다. 실제로 그렇게 남은 표가 있었다.
    부모 표 이름은 `member_id -> member` 처럼 접미사를 떼어 추측한다.
    """
    ok, out = _psql(db, _ORPHAN_SQL_FK)
    if not ok:
        return {"error": out}
    fk = {}
    for line in out.strip().splitlines():
        parts = line.split("\t")
        if len(parts) == 4:
            fk[(parts[0], parts[1])] = {"refs": parts[2], "delete_rule": parts[3]}

    ok, out = _psql(db, _ORPHAN_SQL_TABLES)
    if not ok:
        return {"error": out}
    cols = [tuple(l.split("\t")) for l in out.strip().splitlines() if "\t" in l]

    ok, out = _psql(db, "select table_name from information_schema.tables "
                        "where table_schema='public' and table_type='BASE TABLE'")
    if not ok:
        return {"error": out}
    tables = {l.strip() for l in out.strip().splitlines() if l.strip()}

    checked, skipped = [], []
    for table, col in cols:
        parent = col[:-3]                       # member_id -> member
        if parent not in tables:
            parent_alt = parent + "s"
            if parent_alt in tables:
                parent = parent_alt
            else:
                skipped.append({"table": table, "column": col,
                                "why": "부모 표를 이름으로 찾지 못함"})
                continue
        rel = fk.get((table, col))
        sql = (f'select count(*) from "{table}" x '
               f'where x."{col}" is not null and not exists '
               f'(select 1 from "{parent}" p where p.id = x."{col}")')
        ok, out = _psql(db, sql)
        if not ok:
            skipped.append({"table": table, "column": col, "why": out[:120]})
            continue
        n = int(out.strip() or 0)
        checked.append({
            "table": table, "column": col, "parent": parent, "orphans": n,
            "fk": rel["delete_rule"] if rel else None,
        })
    return {"checked": checked, "skipped": skipped}


def _admin_log_tail(base: str, admin: dict, paths: dict, lines: int) -> tuple[bool, str]:
    """관리자 폼 로그인을 거쳐 로그를 받아온다.

    폼 로그인은 CSRF 토큰을 먼저 받아야 한다. 이걸 모르면 403만 보고 "로그를 못 본다"로
    끝난다 — 실제로 한 번 그렇게 막혔다. 순서를 여기에 고정해 둔다.
    """
    import http.cookiejar
    import json as _json
    import urllib.error
    import urllib.parse
    import urllib.request

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    login_url = base.rstrip("/") + paths["login"]
    try:
        with opener.open(login_url, timeout=20) as r:
            html = r.read().decode("utf-8", "replace")
    except Exception as e:                      # noqa: BLE001
        return False, f"로그인 화면을 열지 못했습니다: {e}"

    m = re.search(r'name="_csrf"[^>]*value="([^"]+)"', html)
    data = {"username": admin["username"], "password": admin["password"]}
    if m:
        data["_csrf"] = m.group(1)
    body = urllib.parse.urlencode(data).encode()
    try:
        opener.open(urllib.request.Request(login_url, data=body), timeout=20).read()
    except urllib.error.HTTPError as e:
        hint = " (CSRF 토큰을 찾지 못했습니다)" if not m else ""
        return False, f"관리자 로그인 실패 HTTP {e.code}{hint}"
    except Exception as e:                      # noqa: BLE001
        return False, f"관리자 로그인 실패: {e}"

    tail_url = f"{base.rstrip('/')}{paths['tail']}?lines={lines}"
    try:
        with opener.open(tail_url, timeout=30) as r:
            raw = r.read().decode("utf-8", "replace")
    except Exception as e:                      # noqa: BLE001
        return False, f"로그를 받지 못했습니다: {e}"

    try:
        return True, _json.loads(raw).get("content", "")
    except ValueError:
        # JSON이 아니면 로그인 화면으로 밀린 것이다 — 세션이 안 붙었다는 뜻.
        return False, "로그 대신 HTML이 왔습니다 — 관리자 세션이 유지되지 않았습니다"


_ADMIN_DEFAULTS = {"login": "/admin/login", "tail": "/admin/logs/api/tail"}


def _backend_conf(root: Path) -> dict:
    """app-map.json 의 backend 섹션. 없으면 그 자리에서 찾아 본다."""
    import json
    d = _scenario_dir(root, create=False)
    if d:
        f = d / _APP_MAP_FILE
        if f.exists():
            try:
                got = json.loads(f.read_text(encoding="utf-8")).get("backend")
                if got:
                    return got
            except ValueError:
                pass
    yml = _find_spring_config(root)
    return {"kind": "spring" if yml else "unknown",
            "db_config": str(yml.relative_to(root)) if yml else None,
            "admin": dict(_ADMIN_DEFAULTS)}


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
    """한 요청을 보낸다. 실패해도 예외로 끝내지 않고 무슨 일이 있었는지 돌려준다 —
    실패 응답 자체가 검증 대상인 경우가 많다(권한 없음·토큰 만료 등)."""
    import urllib.error
    import urllib.request

    url = path if path.startswith("http") else base.rstrip("/") + "/" + path.lstrip("/")
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json", "Accept": "application/json", **headers}
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = (e.fp.read().decode("utf-8", "replace") if e.fp else "")
        status = e.code
    except Exception as e:  # 네트워크 자체가 안 될 때
        return {"ok": False, "url": url, "error": str(e),
                "elapsed_ms": int((time.time() - started) * 1000)}
    try:
        parsed = json.loads(raw) if raw.strip() else None
    except json.JSONDecodeError:
        parsed = None
    return {"ok": True, "url": url, "status": status, "json": parsed,
            "text": None if parsed is not None else raw[:2000],
            "elapsed_ms": int((time.time() - started) * 1000)}


# ── 웹 타겟: 브라우저를 직접 몬다 (이슈 #586) ────────────────────────────
#
# agent가 스크린샷을 보고 다음 수를 정하므로 조작이 여러 번의 CLI 호출로 쪼개진다.
# Playwright를 호출마다 새로 띄우면 **매번 브라우저가 새로 뜨고 로그인이 풀린다**(기동 ~3초).
#
# 상주 데몬을 직접 만들지 않고 **CDP 재연결**로 푼다:
#   open  → --remote-debugging-port 로 띄우고 포트를 상태파일에 적는다
#   이후  → connect_over_cdp 로 그 브라우저에 붙었다 떨어진다 (세션·쿠키 유지)
# 브라우저가 죽으면 상태파일만 지우면 복구된다.

_WEB_STATE = "browser.json"


def _web_state_path(root: Path) -> Path:
    return _home_dir(root) / _WEB_STATE


# 웹용 전용 가상환경. 시스템 파이썬에 깔지 않는 이유:
# macOS의 Homebrew 파이썬은 PEP 668로 `pip install`을 막는다(externally-managed).
# 안내만 하고 사용자를 거기에 세워 두면 스킬이 제 역할을 못 한다.
_VENV_DIR = Path.home() / ".projectops" / "agent-test" / ".venv"


def _venv_python() -> Path | None:
    """전용 가상환경의 파이썬. 없으면 None."""
    exe = _VENV_DIR / ("Scripts" if os.name == "nt" else "bin") / (
        "python.exe" if os.name == "nt" else "python")
    return exe if exe.is_file() else None


def _venv_site_packages() -> Path | None:
    for pat in ("lib/python*/site-packages", "Lib/site-packages"):
        for d in _VENV_DIR.glob(pat):
            if d.is_dir():
                return d
    return None


def _require_playwright() -> tuple[object | None, dict | None]:
    """Playwright를 불러온다. 전용 가상환경 → 시스템 순으로 본다.

    함수 안에서 import하는 이유: 웹을 안 쓰는 프로젝트에서 이 스크립트가 통째로
    죽으면 안 된다. 앱·서버 타겟은 Playwright 없이 돌아가야 한다.
    """
    sp = _venv_site_packages()
    if sp and str(sp) not in sys.path:
        sys.path.insert(0, str(sp))
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright, None
    except ImportError:
        return None, {
            "ok": False, "code": "playwright_missing",
            "error": "웹을 밟으려면 Playwright가 필요합니다",
            "fix": "web setup  # 전용 환경을 만들고 브라우저까지 받습니다 (약 100MB)",
            "manual": f"{sys.executable} -m venv {_VENV_DIR} && "
                      f"{_VENV_DIR}/bin/pip install playwright && "
                      f"{_VENV_DIR}/bin/python -m playwright install chromium",
            "why": ("gstack 같은 별도 설치물에 기대지 않으려고 Playwright를 직접 씁니다. "
                    "시스템 파이썬을 건드리지 않도록 전용 환경에 깝니다"),
            "ask_user": "웹을 밟으려면 브라우저(약 100MB)를 받아야 합니다. 설치할까요?",
        }


def _web_connect(state: dict):
    """열려 있는 브라우저에 붙는다. 호출부가 with로 감싸 쓴다."""
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
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return (pw, browser, page), None


def _web_setup(force: bool = False) -> dict:
    """웹을 밟을 환경을 만든다 — 전용 가상환경 + Playwright + Chromium.

    안내만 하고 사용자를 세워 두지 않는다. 다만 **약 100MB를 받으므로 부르는 쪽이
    먼저 물어본다** (SKILL.md의 절차). 시스템 파이썬은 건드리지 않는다 — macOS의
    Homebrew 파이썬은 PEP 668로 pip를 막아 두어 애초에 깔리지도 않는다.
    """
    steps = []
    if not _venv_python() or force:
        r = subprocess.run([sys.executable, "-m", "venv", str(_VENV_DIR)],
                           capture_output=True, text=True)
        steps.append({"step": "가상환경 생성", "ok": r.returncode == 0,
                      "error": (r.stderr or "")[-300:] or None})
        if r.returncode != 0:
            return {"ok": False, "code": "venv_failed", "steps": steps,
                    "error": "가상환경을 만들지 못했습니다"}

    vpy = _venv_python()
    if vpy is None:
        return {"ok": False, "code": "venv_missing", "steps": steps,
                "error": "가상환경 파이썬을 찾지 못했습니다"}

    r = subprocess.run([str(vpy), "-m", "pip", "install", "-q", "playwright"],
                       capture_output=True, text=True, timeout=900)
    steps.append({"step": "playwright 설치", "ok": r.returncode == 0,
                  "error": (r.stderr or "")[-300:] or None})
    if r.returncode != 0:
        return {"ok": False, "code": "pip_failed", "steps": steps,
                "error": "playwright를 설치하지 못했습니다"}

    # 브라우저 내려받기가 제일 오래 걸린다(약 100MB). 여기서 끊기면 web open이 실패한다.
    r = subprocess.run([str(vpy), "-m", "playwright", "install", "chromium"],
                       capture_output=True, text=True, timeout=1800)
    steps.append({"step": "chromium 내려받기", "ok": r.returncode == 0,
                  "error": (r.stderr or "")[-300:] or None})
    if r.returncode != 0:
        return {"ok": False, "code": "browser_failed", "steps": steps,
                "error": "브라우저를 받지 못했습니다"}

    return {"ok": True, "steps": steps, "venv": str(_VENV_DIR),
            "summary": "웹을 밟을 준비가 됐습니다",
            "next": "web open --url <주소>"}


def cmd_web(args) -> int:
    """웹 화면을 조작한다. 한 번에 한 동작 — agent가 화면을 보고 다음을 정한다."""
    if args.action == "setup":
        return emit(_web_setup(force=args.force))

    root = Path(args.root).resolve()
    state_f = _web_state_path(root)

    if args.action == "open":
        sync_playwright, err = _require_playwright()
        if err:
            return emit(err)
        import socket
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()

        # ⚠️ Playwright의 launch()로 띄우면 **드라이버가 죽을 때 브라우저도 함께 죽는다.**
        # 이 스킬은 호출이 여러 번으로 쪼개지므로(agent가 화면을 보고 다음 수를 정한다)
        # 그러면 두 번째 명령이 붙을 곳이 없다. 실측으로 확인한 함정이다.
        # 그래서 **브라우저를 Playwright 밖에서 독립 프로세스로** 띄우고 CDP로 붙는다.
        with sync_playwright() as pw:
            exe = pw.chromium.executable_path
        profile = _home_dir(root) / ".browser-profile"
        profile.mkdir(parents=True, exist_ok=True)

        cmd = [exe, f"--remote-debugging-port={port}",
               f"--user-data-dir={profile}",   # 쿠키·로그인이 다음 실행에도 남는다
               f"--window-size={args.width},{args.height}",
               "--no-first-run", "--no-default-browser-check"]
        if not args.headed:
            cmd.append("--headless=new")
        if args.url:
            cmd.append(args.url)
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                start_new_session=True)   # 우리가 끝나도 살아 있어야 한다

        # 포트가 열릴 때까지 기다린다. 안 기다리면 바로 다음 명령이 붙지 못한다.
        import socket as _s
        cdp = f"http://127.0.0.1:{port}"
        for _ in range(60):
            with _s.socket() as probe:
                probe.settimeout(0.3)
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.25)
        else:
            proc.terminate()
            return emit({"ok": False, "code": "browser_start_failed",
                         "error": "브라우저가 뜨지 않았습니다",
                         "hint": "web setup 으로 브라우저를 다시 받아 보세요"})

        state_f.parent.mkdir(parents=True, exist_ok=True)
        state_f.write_text(json.dumps({
            "cdp": cdp, "pid": proc.pid, "headed": bool(args.headed),
            "profile": str(profile),
            "opened_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, ensure_ascii=False), encoding="utf-8")
        return emit({
            "action": "open", "url": args.url, "cdp": cdp, "pid": proc.pid,
            "state_file": str(state_f),
            "summary": f"브라우저를 열었습니다 ({args.url or '빈 탭'})",
            "next": "web shot  # 화면을 먼저 봅니다",
        })

    if not state_f.is_file():
        return emit({"ok": False, "code": "browser_not_open",
                     "error": "열린 브라우저가 없습니다",
                     "next": f"web open --root {root} --url <주소>"})
    state = json.loads(state_f.read_text(encoding="utf-8"))

    conn, err = _web_connect(state)
    if err:
        if err.get("code") == "browser_gone":
            state_f.unlink(missing_ok=True)   # 죽은 상태파일을 남기면 계속 헛돈다
        return emit(err)
    pw, browser, page = conn

    try:
        if args.action == "close":
            browser.close()
            # CDP로 붙은 브라우저는 close()로 안 죽는 경우가 있다(우리가 띄운 독립 프로세스다)
            pid = state.get("pid")
            if pid:
                try:
                    os.kill(int(pid), 15)
                except (ProcessLookupError, PermissionError, ValueError):
                    pass
            state_f.unlink(missing_ok=True)
            return emit({"action": "close", "summary": "브라우저를 닫았습니다"})

        if args.action == "goto":
            if not args.url:
                return emit({"ok": False, "code": "url_required", "error": "--url 이 필요합니다"})
            page.goto(args.url, wait_until="domcontentloaded")

        elif args.action == "click":
            if not args.selector:
                return emit({"ok": False, "code": "selector_required",
                             "error": "--selector 가 필요합니다",
                             "hint": "text=로그인 · #submit · button:has-text('저장')"})
            page.click(args.selector, timeout=args.timeout * 1000)

        elif args.action == "type":
            if not (args.selector and args.text is not None):
                return emit({"ok": False, "code": "missing_argument",
                             "error": "--selector 와 --text 가 필요합니다"})
            page.fill(args.selector, args.text, timeout=args.timeout * 1000)

        elif args.action == "shot":
            out = Path(args.out) if args.out else (_home_dir(root) / "shots" /
                  f"{time.strftime('%Y%m%d-%H%M%S')}.png")
            out.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out), full_page=args.full)
            return emit({"action": "shot", "file": str(out), "url": page.url,
                         "title": page.title(),
                         "summary": f"화면을 찍었습니다: {out.name}",
                         "next": "이미지를 읽어 다음 조작을 정하세요"})

        elif args.action == "assert":
            # 무엇을 확인했는지 남긴다 — 통과했다는 말만으로는 근거가 되지 않는다
            checks = []
            if args.url:
                checks.append({"expect_url": args.url, "got": page.url,
                               "ok": args.url in page.url})
            if args.text:
                found = page.get_by_text(args.text).count() > 0
                checks.append({"expect_text": args.text, "ok": found})
            if args.selector:
                checks.append({"expect_selector": args.selector,
                               "ok": page.locator(args.selector).count() > 0})
            if not checks:
                return emit({"ok": False, "code": "nothing_to_assert",
                             "error": "--url · --text · --selector 중 하나는 있어야 합니다"})
            passed = all(c["ok"] for c in checks)
            return emit({"action": "assert", "checks": checks, "ok": passed,
                         "url": page.url,
                         "summary": "확인 통과" if passed else "확인 실패"})

        elif args.action == "console":
            # 이미 쌓인 것은 못 본다. 지금부터 잠깐 듣는다 — 조작 직후에 부른다.
            logs = []
            page.on("console", lambda m: logs.append({"type": m.type, "text": m.text}))
            page.wait_for_timeout(args.timeout * 1000)
            errs = [l for l in logs if l["type"] == "error"]
            return emit({"action": "console", "logs": logs[-50:],
                         "error_count": len(errs),
                         "summary": f"콘솔 {len(logs)}줄 (오류 {len(errs)})"})

        return emit({"action": args.action, "url": page.url, "title": page.title(),
                     "summary": f"{args.action} 완료 — {page.url}",
                     "next": "web shot  # 결과를 눈으로 확인하세요"})
    except Exception as e:
        return emit({"ok": False, "code": "web_action_failed",
                     "action": args.action, "error": str(e)[:400],
                     "url": page.url if page else None,
                     "next": "web shot  # 지금 화면이 무엇인지 먼저 봅니다"})
    finally:
        # 연결만 끊는다. browser.close()를 부르면 다음 호출이 붙을 곳이 없어진다.
        pw.stop()


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
        urls = _api_base_urls(root)
        base = urls[0] if urls else ""
    if not base:
        return emit({"ok": False, "code": "base_url_required",
                     "error": "API 주소를 알 수 없습니다 — --base-url 로 알려주세요"})

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
            row["expect_server"] = st["expect_server"]   # DB 대조는 backend 서브커맨드로

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
                 "backend  # 서버 로그·DB를 대조해 원인을 좁히세요"),
    })


# ── DB 대조 (이슈 #589) ──────────────────────────────────────────────────
#
# **접속 방법은 agent가 정한다.** 프로젝트마다 설정이 사는 곳이 다르고(application.yml ·
# .env · settings.py · ormconfig), 붙는 길도 제각각이다 — 로컬 DB · 열린 포트 · SSH로
# 들어가야만 닿는 DB · 컨테이너 안에서 실행 · 터널 경유.
#
# 예전에는 py가 Spring의 application-prod.yml을 찾아 psql로 붙는 한 가지만 했다.
# 그 바깥은 전부 못 했고, MySQL은 읽어 놓고 psql로 붙으려다 조용히 실패했다.
# 이제 py는 **받은 대로 실행만 한다.**

# 엔진별 클라이언트. 없는 엔진은 추측하지 않고 그렇다고 말한다.
_DB_CLIENTS = {
    "postgres": "psql",
    "postgresql": "psql",
    "mysql": "mysql",
    "mariadb": "mysql",
}


def _db_argv(engine: str, db: dict, sql: str) -> tuple[list[str], dict]:
    """엔진에 맞는 명령과 환경변수를 만든다. 비밀번호는 argv가 아니라 env로 넘긴다 —
    argv는 같은 기기의 다른 프로세스에서 보인다."""
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


# ── 접근 방법 기록 (이슈 #589) ───────────────────────────────────────────
#
# **어떻게 DB에 붙고 로그를 보는지는 agent가 코드를 읽고 판단한다.**
# 서버는 Spring·Django·FastAPI·Express·NestJS·Rails… 끝이 없고, 같은 프레임워크라도
# 설정이 사는 곳과 붙는 길이 제각각이다. 정규식으로 맞히려는 시도는 성립하지 않는다.
#
# 그래서 py는 찾지 않는다. agent가 알아낸 것을 여기에 적어 두고, 다음 실행은 그것을 쓴다.
# learned.json과 같은 자리(프로젝트 밖)에 있어 워크트리를 오가도 남는다.

_ACCESS_FILE = "access.json"


def _access_path(root: Path) -> Path:
    return _home_dir(root) / _ACCESS_FILE


def _load_access(root: Path) -> dict:
    f = _access_path(root)
    if not f.is_file():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def cmd_access(args) -> int:
    """이 프로젝트에 어떻게 붙는지를 적어 두고 꺼내 쓴다.

    agent가 코드를 읽어 알아낸 것을 기록한다 — DB 접속, 로그 보는 법, API 주소.
    비밀번호는 **값을 적지 않는다.** 어느 환경변수에서 읽을지만 적는다.
    """
    root = Path(args.root).resolve()
    data = _load_access(root)

    if args.action == "show":
        return emit({
            "file": str(_access_path(root)),
            "access": data,
            "summary": (f"{', '.join(data)} 기록됨" if data else "아직 기록이 없습니다"),
            "next": (None if data else
                     "코드를 읽어 붙는 법을 알아낸 뒤 access set --key db --json '{...}'"),
        })

    if args.action == "set":
        if not args.key:
            return emit({"ok": False, "code": "key_required",
                         "error": "--key 가 필요합니다 (db · logs · base_url 등)"})
        try:
            value = json.loads(args.json_value) if args.json_value else None
        except json.JSONDecodeError as e:
            return emit({"ok": False, "code": "bad_json", "error": f"--json 이 올바르지 않습니다: {e}"})
        if value is None:
            return emit({"ok": False, "code": "value_required", "error": "--json 이 필요합니다"})

        # 비밀번호 원문이 섞여 들어오면 막는다. 파일은 로컬에만 있지만 공유될 수 있다.
        leaked = _find_secrets(json.dumps(value, ensure_ascii=False))
        if leaked and not args.allow_secret:
            return emit({
                "ok": False, "code": "secret_in_value",
                "error": "비밀값으로 보이는 것이 들어 있습니다",
                "found": leaked[:5],
                "hint": '값 대신 읽을 곳을 적으세요. 예: {"password_env": "ELUM_DB_PASSWORD"}',
            })

        data[args.key] = value
        f = _access_path(root)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return emit({"file": str(f), "key": args.key, "access": data,
                     "summary": f"{args.key} 기록 완료"})

    if args.action == "unset":
        if args.key in data:
            del data[args.key]
            _access_path(root).write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return emit({"key": args.key, "access": data, "summary": f"{args.key} 지움"})
        return emit({"key": args.key, "access": data, "code": "not_found",
                     "summary": f"{args.key} 가 없습니다"})

    return emit({"ok": False, "code": "unknown_action", "error": args.action})


def cmd_db(args) -> int:
    """SQL 한 줄을 실행한다. **어떻게 붙을지는 호출하는 쪽이 정한다.**

    세 가지 길이 있다.
      --command  임의 명령 (docker exec 등). 가장 자유롭다
      --via ssh  원격에 들어가 그 안에서 클라이언트를 실행한다
      (기본)     여기서 직접 붙는다
    """
    sql = args.sql
    if not sql:
        return emit({"ok": False, "code": "sql_required", "error": "--sql 이 필요합니다"})

    # 적어 둔 접근 방법을 그대로 쓴다. 기록해 놓고 매번 값을 꺼내 조립해야 하면 소용이 없다.
    # 인자로 직접 준 값이 언제나 이긴다 — 기록이 낡았을 때 빠져나갈 길을 막지 않는다.
    if args.profile:
        saved = _load_access(Path(args.root).resolve()).get(args.profile)
        if not saved:
            return emit({"ok": False, "code": "profile_not_found",
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
            # 비밀번호는 값이 아니라 "어디서 읽을지"로 적어 둔다
            env_key = saved.get("password_env")
            if env_key and not args.password:
                args.password = os.environ.get(env_key)
                if not args.password:
                    return emit({"ok": False, "code": "password_env_empty",
                                 "error": f"환경변수 {env_key} 가 비어 있습니다",
                                 "hint": f"{env_key}=... 를 주고 다시 부르세요"})

    # ① 임의 명령 — agent가 접속을 통째로 정한 경우
    if args.command:
        argv = ["bash", "-lc", f"{args.command} {_shq(sql)}"] if args.append_sql \
               else ["bash", "-lc", args.command]
        stdin = None if args.append_sql else sql
        try:
            r = subprocess.run(argv, input=stdin, capture_output=True, text=True,
                               timeout=args.timeout)
        except subprocess.TimeoutExpired:
            return emit({"ok": False, "code": "db_timeout",
                         "error": f"응답 없음 ({args.timeout}초)"})
        return emit({
            "ok": r.returncode == 0, "via": "command",
        "code": "ok" if r.returncode == 0 else "db_query_failed",
            "rows": _db_rows(r.stdout), "raw": r.stdout[:4000],
            "error": (r.stderr or "").strip()[:500] or None,
            "summary": "실행 완료" if r.returncode == 0 else "실행 실패",
        })

    engine = (args.engine or "").lower()
    if engine not in _DB_CLIENTS:
        return emit({
            "ok": False, "code": "unsupported_engine",
            "error": f"engine '{args.engine}' 은 다루지 않습니다",
            "supported": sorted(set(_DB_CLIENTS)),
            "hint": "--command 로 직접 실행할 명령을 주면 어떤 DB든 됩니다",
        })

    db = {"host": args.host, "port": args.port, "name": args.db,
          "user": args.user, "password": args.password or os.environ.get("DB_PASSWORD")}
    argv, env = _db_argv(engine, db, sql)

    # ② SSH 경유 — 서버 안에서만 닿는 DB
    if args.via == "ssh":
        if not args.ssh_host:
            return emit({"ok": False, "code": "ssh_host_required",
                         "error": "--ssh-host 가 필요합니다"})
        remote = " ".join(f"{k}={_shq(v)}" for k, v in env.items() if v)
        remote += " " + " ".join(_shq(a) for a in argv)
        dest = f"{args.ssh_user}@{args.ssh_host}" if args.ssh_user else args.ssh_host
        ssh = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
        if args.ssh_port:
            ssh += ["-p", str(args.ssh_port)]
        full = ssh + [dest, remote]
        try:
            r = subprocess.run(full, capture_output=True, text=True, timeout=args.timeout)
        except subprocess.TimeoutExpired:
            return emit({"ok": False, "code": "db_timeout",
                         "error": f"응답 없음 ({args.timeout}초)"})
        return emit({
            "ok": r.returncode == 0, "via": "ssh",
        "code": "ok" if r.returncode == 0 else "db_query_failed", "engine": engine,
            "rows": _db_rows(r.stdout), "raw": r.stdout[:4000],
            "error": (r.stderr or "").strip()[:500] or None,
            "summary": "실행 완료" if r.returncode == 0 else "실행 실패",
            "hint": ("비밀번호 없이 붙는 키가 있어야 합니다(BatchMode)"
                     if r.returncode != 0 else None),
        })

    # ③ 직접 — 여기서 붙는다
    exe = shutil.which(argv[0])
    if not exe:
        return emit({
            "ok": False, "code": "client_missing",
            "error": f"{argv[0]} 가 없습니다",
            "install": ("brew install libpq" if argv[0] == "psql" else "brew install mysql-client"),
            "hint": "--via ssh 로 서버 안에서 실행하거나 --command 로 직접 명령을 주세요",
        })
    try:
        r = subprocess.run([exe] + argv[1:], env=dict(os.environ, **env),
                           capture_output=True, text=True, timeout=args.timeout)
    except subprocess.TimeoutExpired:
        return emit({"ok": False, "code": "db_timeout",
                     "error": f"응답 없음 ({args.timeout}초)"})
    return emit({
        "ok": r.returncode == 0, "via": "direct",
        "code": "ok" if r.returncode == 0 else "db_query_failed", "engine": engine,
        "rows": _db_rows(r.stdout), "raw": r.stdout[:4000],
        "error": (r.stderr or "").strip()[:500] or None,
        "summary": "실행 완료" if r.returncode == 0 else "실행 실패",
    })


def cmd_logs(args) -> int:
    """서버 로그를 본다. **보는 방법은 적어 둔 것을 쓴다.**

    로그는 컨테이너 안에 있을 수도, 파일일 수도, 관리자 화면에만 있을 수도 있다.
    py가 맞히려 들지 않는다 — agent가 알아내 access 에 적고, 여기서는 실행만 한다.
    """
    root = Path(args.root).resolve()
    command = args.command
    if not command:
        saved = _load_access(root).get(args.profile or "logs")
        if isinstance(saved, dict):
            command = saved.get("command")
        elif isinstance(saved, str):
            command = saved
    if not command:
        return emit({
            "ok": False, "code": "no_log_command",
            "error": "로그를 어떻게 보는지 모릅니다",
            "hint": ('코드를 읽어 알아낸 뒤 적어 두세요. 예: '
                     'access set --key logs --json \'{"command":"ssh u@h \\"docker logs --tail 200 app\\""}\''),
        })
    if args.tail:
        command = f"{command} | tail -n {int(args.tail)}"
    if args.grep:
        command = f"{command} | grep -i -- {_shq(args.grep)}"
    try:
        r = subprocess.run(["bash", "-lc", command], capture_output=True, text=True,
                           timeout=args.timeout)
    except subprocess.TimeoutExpired:
        return emit({"ok": False, "code": "logs_timeout",
                     "error": f"응답 없음 ({args.timeout}초)"})
    out = r.stdout or ""
    return emit({
        "ok": r.returncode == 0,
        "code": "ok" if r.returncode == 0 else "logs_failed",
        "lines": out.splitlines()[-(args.tail or 200):],
        "error": (r.stderr or "").strip()[:500] or None,
        "summary": f"{len(out.splitlines())}줄" if r.returncode == 0 else "실행 실패",
    })


def _db_rows(out: str) -> list[list[str]]:
    """탭으로 나뉜 출력을 행 목록으로. 판정은 agent가 한다."""
    rows = []
    for line in (out or "").splitlines():
        if line.strip():
            rows.append(line.split("\t"))
    return rows[:200]


def cmd_backend(args) -> int:
    """서버 쪽을 대조한다 — probe / orphans / logs."""
    import json
    from datetime import date

    root = Path(args.root).resolve()
    conf = _backend_conf(root)
    yml_rel = args.config or conf.get("db_config")
    yml = (root / yml_rel) if yml_rel else None
    if yml is None or not yml.exists():
        return emit({"ok": False, "code": "backend_config_not_found",
                     "error": "서버 설정 파일을 찾지 못했습니다",
                     "next": "--config 로 application-*.yml 경로를 주세요"})
    cfg = _read_spring_config(yml)
    # 프로필별 파일에는 서버 주소·관리자 계정이 없을 수 있다. 공통 파일에서 채운다 —
    # 한 파일만 보고 "설정이 없다"고 끝내면 로그를 영영 못 본다.
    for sibling in ("application.yml", "application.yaml"):
        f = yml.parent / sibling
        if f == yml or not f.exists():
            continue
        extra = _read_spring_config(f)
        for key in ("admin", "base_url", "db"):
            if not cfg.get(key) and extra.get(key):
                cfg[key] = extra[key]

    if args.action == "probe":
        admin_paths = dict(conf.get("admin") or _ADMIN_DEFAULTS)
        # setdefault 로는 못 채운다 — 앞선 probe 가 base: null 을 이미 적어 뒀을 수 있다.
        if not admin_paths.get("base"):
            admin_paths["base"] = cfg.get("base_url")
        # 접속 주소·포트·DB 이름은 **적지 않는다.** 이 파일은 레포에 올라가고
        # 레포가 공개일 수 있다. 설정 파일이 gitignore 되어 있어도 여기로 새면 의미가 없다.
        # 매 실행에서 설정 파일을 다시 읽으면 되므로 굳이 남길 이유도 없다.
        backend = {
            "kind": "spring",
            "db_config": str(yml.relative_to(root)),
            "db_engine": cfg["db"]["engine"] if cfg["db"] else None,
            "db_reachable": bool(cfg["db"]),
            "admin": {k: v for k, v in admin_paths.items() if k != "base"},
            "admin_base_in_config": bool(admin_paths.get("base")),
            "admin_account_in_config": bool(cfg["admin"]),
        }
        d = _scenario_dir(root, create=True)
        f = d / _APP_MAP_FILE
        doc = {}
        if f.exists():
            try:
                doc = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                doc = {}
        doc["backend"] = backend
        doc["backend_scanned"] = date.today().isoformat()
        f.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
        return emit({
            "backend": backend,
            "summary": (f"{backend['kind']} · {backend['db_engine'] or 'DB 미확인'} · "
                        f"관리자 계정 {'있음' if cfg['admin'] else '없음'} · "
                        f"주소는 기록하지 않음(설정 파일에서 매번 읽음)"),
            "next": "backend orphans / backend logs 를 인자 없이 쓸 수 있습니다",
        })

    if args.action == "orphans":
        if not cfg["db"]:
            return emit({"ok": False, "code": "db_not_configured",
                         "error": f"{yml_rel} 에서 jdbc URL을 찾지 못했습니다"})
        res = _orphan_scan(cfg["db"])
        if "error" in res:
            return emit({"ok": False, "code": "db_query_failed",
                         "error": res["error"],
                         "next": "psql 설치와 DB 접근 권한을 확인하세요"})
        bad = [c for c in res["checked"] if c["orphans"] > 0]
        return emit({
            "database": cfg["db"]["name"],
            "checked": res["checked"],
            "orphans": bad,
            "skipped": res["skipped"],
            "summary": (f"{len(res['checked'])}개 참조 중 고아 {len(bad)}곳 "
                        + (", ".join(f"{c['table']}.{c['column']}={c['orphans']}"
                                     for c in bad) if bad else "(없음)")),
            "next": ("외래키가 없는(fk=null) 곳부터 보세요 — DB가 대신 지워 주지 않아 "
                     "삭제 코드에서 빠뜨리기 쉽습니다" if bad else
                     "삭제 경로는 깨끗합니다"),
        })

    # logs
    if not cfg["admin"]:
        return emit({"ok": False, "code": "admin_account_not_found",
                     "error": f"{yml_rel} 에서 관리자 계정을 찾지 못했습니다"})
    admin_paths = dict(_ADMIN_DEFAULTS)
    admin_paths.update({k: v for k, v in (conf.get("admin") or {}).items() if v})
    base = args.base or admin_paths.get("base") or cfg.get("base_url")
    if not base:
        return emit({"ok": False, "code": "base_url_not_found",
                     "error": "서버 주소를 찾지 못했습니다",
                     "next": "--base https://... 로 지정하세요"})

    ok, content = _admin_log_tail(base, cfg["admin"], admin_paths, args.lines)
    if not ok:
        return emit({"ok": False, "code": "log_fetch_failed", "error": content})

    rows = content.split("\n")
    if args.grep:
        pat = re.compile(args.grep)
        rows = [r for r in rows if pat.search(r)]
    shown = rows[-args.tail:] if args.tail else rows

    out_file = None
    if args.out:
        out_path = Path(args.out).expanduser()
        out_path.write_text(content, encoding="utf-8")
        out_file = str(out_path)

    errs = [r for r in rows if " ERROR " in r or " WARN " in r]
    return emit({
        "base": base,
        "lines_requested": args.lines,
        "matched": len(rows),
        "errors_or_warnings": len(errs),
        "content": "\n".join(shown),
        "saved": out_file,
        "summary": f"{len(rows)}줄 · ERROR/WARN {len(errs)}건",
        "next": ("--grep 으로 요청 경로를 좁혀 앱이 실제로 보낸 본문을 확인하세요"
                 if not args.grep else None),
    })


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="e2e_cli",
        description="Flutter 실기기 E2E 준비 조사",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_d = sub.add_parser("detect", help="프로젝트·패키지·API·기기를 한 번에 조사")
    p_d.add_argument("--path", default=".", help="탐색 시작 경로 (기본: 현재 디렉터리)")
    p_d.add_argument("--target", default=None,
                     help=f"밟을 대상을 직접 지정 ({'·'.join(TARGETS)}). 생략하면 감지한다")
    p_d.set_defaults(func=cmd_detect)

    p_v = sub.add_parser("devices", help="연결·부팅된 기기 조회")
    p_v.set_defaults(func=cmd_devices)

    p_doc = sub.add_parser("doctor", help="도구·산출물 보호 상태 점검")
    p_doc.add_argument("--root", default=".", help="프로젝트 루트")
    p_doc.set_defaults(func=cmd_doctor)

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

    p_b = sub.add_parser("bootstrap", help="앱 구조를 스캔하고 기능별 폴더를 만든다")
    p_b.add_argument("--path", default=".", help="프로젝트 경로")
    p_b.add_argument("--target", default=None,
                     help=f"훑을 대상 ({'·'.join(TARGETS)}). 생략하면 감지한다")
    p_b.set_defaults(func=cmd_bootstrap)

    p_e = sub.add_parser("edges", help="코드에서 밟아야 할 실패 경로를 뽑는다")
    p_e.add_argument("--path", default=".", help="프로젝트 경로")
    p_e.add_argument("--samples", type=int, default=3, help="분류별로 보여줄 예시 수")
    p_e.add_argument("--target", default=None,
                     help=f"훑을 대상 ({'·'.join(TARGETS)}). 생략하면 감지한다")
    p_e.set_defaults(func=cmd_edges)

    p_n = sub.add_parser("note", help="이 프로젝트에서 알아낸 것을 쌓는다")
    p_n.add_argument("action",
                     choices=["show", "constraint", "screen", "pitfall", "run"])
    p_n.add_argument("--root", default=".")
    p_n.add_argument("--name", help="screen: 화면 이름 / run: 시나리오 이름")
    p_n.add_argument("--anchor", help="screen: 이 화면임을 알아보는 단서(문구 등)")
    p_n.add_argument("--taps", nargs="*", help="screen: '라벨=x,y' 형태로 여러 개")
    p_n.add_argument("--screen-size", help="screen: 좌표를 잰 해상도. 예 1080x2400")
    p_n.add_argument("--text",
                     help="constraint: 지켜야 할 것 / pitfall: 함정 / run: 결과 요약")
    p_n.add_argument("--check",
                     help="constraint: 밟으면서 무엇을 보면 위반을 알 수 있는지")
    p_n.add_argument(
        "--scope", choices=["project", "flutter", "platform"], default="project",
        help=("pitfall 범위. project=이 앱에서만 / flutter=모든 Flutter 앱 / "
              "platform=기기·OS 차원. project가 아니면 skill로 올리라고 안내한다"))
    p_n.set_defaults(func=cmd_note)

    p_web = sub.add_parser("web", help="웹 화면을 조작한다 (target: web)")
    p_web.add_argument("action",
                       choices=["setup", "open", "goto", "click", "type", "shot",
                                "assert", "console", "close"])
    p_web.add_argument("--force", action="store_true",
                       help="setup: 이미 있어도 다시 만든다")
    p_web.add_argument("--root", default=".", help="프로젝트 루트")
    p_web.add_argument("--url", default=None, help="주소 (open·goto·assert)")
    p_web.add_argument("--selector", default=None,
                       help="대상 (click·type·assert). text=로그인 · #id · button:has-text('x')")
    p_web.add_argument("--text", default=None, help="입력할 값 또는 확인할 문구")
    p_web.add_argument("--out", default=None, help="스크린샷 저장 경로")
    p_web.add_argument("--full", action="store_true", help="페이지 전체를 찍는다")
    p_web.add_argument("--headed", action="store_true", help="브라우저를 눈에 보이게 연다")
    p_web.add_argument("--width", type=int, default=1280)
    p_web.add_argument("--height", type=int, default=800)
    p_web.add_argument("--timeout", type=int, default=10, help="대기 제한(초)")
    p_web.set_defaults(func=cmd_web)

    p_api = sub.add_parser("api", help="서버 시나리오를 밟는다 (target: server)")
    p_api.add_argument("--name", required=True, help="시나리오 이름")
    p_api.add_argument("--root", default=".", help="프로젝트 루트")
    p_api.add_argument("--base-url", dest="base_url", default=None,
                       help="API 주소. 생략하면 시나리오·설정에서 찾는다")
    p_api.add_argument("--timeout", type=int, default=30, help="요청당 제한 시간(초)")
    p_api.set_defaults(func=cmd_api)

    p_ac = sub.add_parser("access", help="이 프로젝트에 붙는 법을 적어 두고 꺼내 쓴다")
    p_ac.add_argument("action", choices=["show", "set", "unset"])
    p_ac.add_argument("--root", default=".", help="프로젝트 루트")
    p_ac.add_argument("--key", default=None, help="db · logs · base_url 등")
    p_ac.add_argument("--json", dest="json_value", default=None,
                      help='적을 내용(JSON). 예: {"how":"ssh","engine":"postgres",...}')
    p_ac.add_argument("--allow-secret", dest="allow_secret", action="store_true",
                      help="비밀값 경고를 무시한다 (권장하지 않음)")
    p_ac.set_defaults(func=cmd_access)

    p_db = sub.add_parser("db", help="SQL을 실행한다 (접속 방법은 호출하는 쪽이 정한다)")
    p_db.add_argument("--sql", required=True, help="실행할 SQL")
    p_db.add_argument("--engine", default=None, help="postgres · mysql (--command 면 불필요)")
    p_db.add_argument("--host", default=None)
    p_db.add_argument("--port", default=None)
    p_db.add_argument("--db", default=None, help="데이터베이스 이름")
    p_db.add_argument("--user", default=None)
    p_db.add_argument("--password", default=None,
                      help="생략하면 DB_PASSWORD 환경변수를 본다 (권장)")
    p_db.add_argument("--via", choices=["direct", "ssh"], default="direct",
                      help="ssh면 원격에 들어가 그 안에서 실행한다")
    p_db.add_argument("--ssh-host", dest="ssh_host", default=None)
    p_db.add_argument("--ssh-user", dest="ssh_user", default=None)
    p_db.add_argument("--ssh-port", dest="ssh_port", default=None)
    p_db.add_argument("--command", default=None,
                      help="접속을 통째로 지정한다. 예: \"docker exec -i pg psql -U root -d elum -c\"")
    p_db.add_argument("--append-sql", dest="append_sql", action="store_true",
                      help="--command 뒤에 SQL을 인자로 붙인다 (기본은 표준입력으로 넘김)")
    p_db.add_argument("--profile", default=None,
                      help="access 에 적어 둔 기록을 쓴다 (예: db). 인자로 준 값이 우선한다")
    p_db.add_argument("--root", default=".", help="--profile 을 찾을 프로젝트 루트")
    p_db.add_argument("--timeout", type=int, default=40)
    p_db.set_defaults(func=cmd_db)

    p_lg = sub.add_parser("logs", help="서버 로그를 본다 (보는 방법은 access 에 적어 둔다)")
    p_lg.add_argument("--root", default=".", help="프로젝트 루트")
    p_lg.add_argument("--profile", default=None, help="access 의 어느 키를 쓸지 (기본 logs)")
    p_lg.add_argument("--command", default=None, help="즉석으로 실행할 명령")
    p_lg.add_argument("--tail", type=int, default=200)
    p_lg.add_argument("--grep", default=None)
    p_lg.add_argument("--timeout", type=int, default=60)
    p_lg.set_defaults(func=cmd_logs)

    p_bk = sub.add_parser("backend", help="서버 로그·DB를 대조한다 (화면만으론 못 잡는 것)")
    p_bk.add_argument("action", choices=["probe", "orphans", "logs"])
    p_bk.add_argument("--root", default=".", help="프로젝트 루트")
    p_bk.add_argument("--config", help="application-*.yml 경로 (미지정 시 자동 탐색)")
    p_bk.add_argument("--base", help="logs: 서버 주소. 미지정 시 설정에서 읽는다")
    p_bk.add_argument("--lines", type=int, default=2000, help="logs: 받아올 줄 수")
    p_bk.add_argument("--grep", help="logs: 이 정규식에 맞는 줄만")
    p_bk.add_argument("--tail", type=int, default=80, help="logs: 결과 끝 N줄만 출력")
    p_bk.add_argument("--out", help="logs: 전체를 이 파일로 저장")
    p_bk.set_defaults(func=cmd_backend)

    p_s = sub.add_parser("shrink", help="이슈 첨부용으로 이미지 축소")
    p_s.add_argument("paths", nargs="+")
    p_s.add_argument("--max-side", type=int, default=700)
    p_s.set_defaults(func=cmd_shrink)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help(sys.stderr)
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
