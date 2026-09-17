#!/usr/bin/env python3
"""e2e_cli — pro-flutter-e2e 전용 CLI (projectops 3-layer 표준, Layer 2).

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
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.emit import emit  # noqa: E402


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
    start = Path(args.path).resolve()
    root = _find_flutter_root(start)
    if root is None:
        return emit({
            "ok": False,
            "code": "flutter_project_not_found",
            "error": f"{start} 아래에서 Flutter 프로젝트를 찾지 못했습니다",
            "hint": "pubspec.yaml이 있는 경로를 --path로 지정하세요",
        })

    dev = _devices()
    has_device = bool(dev["android"] or dev["ios_booted"])
    return emit({
        "flutter_root": str(root),
        "android_package": _android_package(root),
        "ios_bundle_id": _ios_bundle_id(root),
        "api_base_urls": _api_base_urls(root),
        "devices": dev,
        "summary": (
            f"{root.name}: android={_android_package(root) or '없음'} "
            f"기기={len(dev['android'])}대/시뮬{len(dev['ios_booted'])}대"
        ),
        "next": None if has_device else "devices  # 기기가 없습니다. AVD를 부팅하세요",
    })


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


def cmd_bootstrap(args) -> int:
    """앱 구조를 스캔해 app-map.json에 적고 기능별 폴더를 만든다.

    매번 코드를 뒤져 라우트를 찾지 않도록 한 번 읽어 둔다. 폴더를 미리 만들어 두면
    새 기능의 시나리오를 어디에 넣을지 고민할 일이 없다 — 코드와 같은 이름이다.
    """
    import json
    from datetime import date

    root = Path(args.path).resolve()
    flutter_root = _find_flutter_root(root)
    if flutter_root is None:
        return emit({"ok": False, "code": "flutter_project_not_found",
                     "error": f"{root} 아래에서 Flutter 프로젝트를 찾지 못했습니다"})
    lib = flutter_root / "lib"

    groups = _scan_feature_groups(lib)
    routes = _scan_routes(lib)
    screens = _scan_screens(lib)
    auth = _scan_auth(lib)

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
        "flutter_root": str(flutter_root.relative_to(root))
                        if flutter_root != root else ".",
        "feature_groups": groups,
        "auth": auth,
        "routes": routes,
        "screens": screens,
    }
    (d / _APP_MAP_FILE).write_text(
        json.dumps(app_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 로그인 전제 템플릿을 제안한다 — 앱마다 방식이 다르므로 만들지는 않는다
    if auth["kind"] == "social" and auth["providers"]:
        hint = (f"_shared/login-{auth['providers'][0]}.json 부터 만드세요 "
                f"(감지된 방식: {', '.join(auth['providers'])})")
    else:
        hint = "_shared/login.json 을 만들어 로그인 단계를 한 곳에 두세요"

    return emit({
        "app_map": str((d / _APP_MAP_FILE).relative_to(root)),
        "feature_groups": groups,
        "created_folders": made,
        "auth": auth,
        "route_count": len(routes),
        "screen_count": len(screens),
        "summary": (f"기능 {len(groups)}개 · 라우트 {len(routes)}개 · "
                    f"화면 {len(screens)}개 · 인증 {auth['kind']}"
                    f"({len(auth['providers'])}종)"),
        "next": hint,
    })


# =========================================================================
# 시나리오 — 프로젝트마다 다른 "무엇을 어떻게 밟을지"를 파일로 둔다
# =========================================================================

_SCENARIO_DIRS = ("docs/testing/e2e", ".projectops/e2e")

_TEMPLATE = {
    "name": "{무엇을 밟는지 한 줄}",
    "description": "{왜 이 경로가 중요한지}",
    "precondition": None,   # 예: "_shared/login-kakao" — 앞에 붙일 흐름
    "reset": {
        "device": "pm clear",
        "server": "{테스트 계정을 지우는 명령. 없으면 null}",
    },
    "steps": [
        {
            "screen": "{화면 이름}",
            "do": "{무엇을 하는지 — tap '시작하기' / input '값' / back}",
            "expect_screen": "{다음에 보여야 할 것}",
            "expect_device": ["{로그에서 확인할 키. 예: elum.refreshToken}"],
            "expect_server": "{서버에서 확인할 쿼리. 없으면 null}",
            "human": None,
        }
    ],
    "conditions": [
        {"name": "큰 글씨", "apply": "settings put system font_scale 1.3",
         "revert": "settings put system font_scale 1.0"},
        {"name": "다크모드", "apply": "cmd uimode night yes",
         "revert": "cmd uimode night no"},
    ],
}

_REQUIRED_STEP_KEYS = ("screen", "do")


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
        if _GITIGNORE_UNSAFE in body and "pro-flutter-e2e" in body:
            gi.write_text(_GITIGNORE, encoding="utf-8")
            return True
        return False
    gi.write_text(_GITIGNORE, encoding="utf-8")
    return True


def _scenario_dir(root: Path, create: bool = False) -> Path:
    """시나리오를 둘 곳. 이미 쓰고 있는 폴더가 있으면 그것을 따른다."""
    for rel in _SCENARIO_DIRS:
        d = root / rel
        if d.is_dir():
            _ensure_gitignore(d)
            return d
    d = root / _SCENARIO_DIRS[0]
    if create:
        d.mkdir(parents=True, exist_ok=True)
        _ensure_gitignore(d)
    return d


def _validate(data: dict) -> list[str]:
    """시나리오가 실행 가능한 모양인지 본다. 밟기 전에 걸러야 중간에 안 멈춘다."""
    problems = []
    if not data.get("name"):
        problems.append("name이 비었습니다")
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
        if not any(st.get(k) for k in ("expect_screen", "expect_device", "expect_server")):
            problems.append(
                f"{i}번째 step({st.get('screen','?')})에 기대 결과가 없습니다 — "
                "화면·기기·서버 중 하나는 있어야 통과 판정을 할 수 있습니다")
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
        f.write_text(json.dumps(_TEMPLATE, ensure_ascii=False, indent=2) + "\n",
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
_GITIGNORE_MARK = "# pro-flutter-e2e — 산출물 폴더"

_GITIGNORE = f"""{_GITIGNORE_MARK}
#
# 이 폴더에서 나오는 것들에는 테스트 계정·토큰·서버 주소·로그인 화면 캡처가 섞인다.
# 그래서 **기본은 올리지 않는다.** 팀과 나눠야 할 파일이 생기면 아래에 한 줄씩 적는다.
#
#   !flows/auth/social-signup.json
#
# 적기 전에 그 파일을 열어 계정·토큰·주소가 없는지 눈으로 본다.

*

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
    lib = root / "lib"
    if not lib.is_dir():
        found = _find_flutter_root(root)
        lib = (found / "lib") if found else None
    if not lib or not lib.is_dir():
        return emit({"ok": False, "code": "lib_not_found",
                     "error": f"{root} 아래에서 lib/ 를 찾지 못했습니다"})

    hits: dict[str, list[dict]] = {}
    scanned = 0
    for f in sorted(lib.rglob("*.dart")):
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
                        "file": str(f.relative_to(lib.parent)),
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
    p_d.set_defaults(func=cmd_detect)

    p_v = sub.add_parser("devices", help="연결·부팅된 기기 조회")
    p_v.set_defaults(func=cmd_devices)

    p_doc = sub.add_parser("doctor", help="도구·산출물 보호 상태 점검")
    p_doc.add_argument("--root", default=".", help="프로젝트 루트")
    p_doc.set_defaults(func=cmd_doctor)

    p_sc = sub.add_parser("scenario", help="프로젝트별 밟기 시나리오 관리")
    p_sc.add_argument("action", choices=["init", "list", "show"])
    p_sc.add_argument("--name", help="시나리오 파일 이름 (확장자 제외)")
    p_sc.add_argument("--root", default=".", help="프로젝트 루트")
    p_sc.add_argument("--group",
                      help="init: flows/{그룹}/ 아래에 만든다. _shared 면 전제로 둔다")
    p_sc.add_argument("--force", action="store_true", help="init 시 덮어쓰기")
    p_sc.set_defaults(func=cmd_scenario)

    p_b = sub.add_parser("bootstrap", help="앱 구조를 스캔하고 기능별 폴더를 만든다")
    p_b.add_argument("--path", default=".", help="프로젝트 경로")
    p_b.set_defaults(func=cmd_bootstrap)

    p_e = sub.add_parser("edges", help="코드에서 밟아야 할 실패 경로를 뽑는다")
    p_e.add_argument("--path", default=".", help="프로젝트 경로")
    p_e.add_argument("--samples", type=int, default=3, help="분류별로 보여줄 예시 수")
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
