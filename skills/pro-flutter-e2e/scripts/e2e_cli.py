#!/usr/bin/env python3
"""e2e_cli — pro-flutter-e2e 전용 CLI (projectops 3-layer 표준, Layer 2).

Flutter 프로젝트를 실기기에서 밟기 전에 필요한 값들을 한 번에 찾아낸다.
매 호출마다 agent가 grep 조합을 다시 짜지 않도록 여기에 모아 둔다.

서브커맨드:
    detect   프로젝트 루트·패키지명·번들ID·API URL·연결된 기기를 한 번에 조사
    devices  연결/부팅된 기기만 조회

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

    return emit({
        "ok": not missing_required,
        "code": "ok" if not missing_required else "missing_required_tool",
        "checks": checks,
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
# 시나리오 — 프로젝트마다 다른 "무엇을 어떻게 밟을지"를 파일로 둔다
# =========================================================================

_SCENARIO_DIRS = ("docs/testing/e2e", ".projectops/e2e")

_TEMPLATE = {
    "name": "{무엇을 밟는지 한 줄}",
    "description": "{왜 이 경로가 중요한지}",
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


def _scenario_dir(root: Path, create: bool = False) -> Path:
    """시나리오를 둘 곳. 이미 쓰고 있는 폴더가 있으면 그것을 따른다."""
    for rel in _SCENARIO_DIRS:
        d = root / rel
        if d.is_dir():
            return d
    d = root / _SCENARIO_DIRS[0]
    if create:
        d.mkdir(parents=True, exist_ok=True)
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


def cmd_scenario(args) -> int:
    root = Path(args.root).resolve()
    d = _scenario_dir(root, create=(args.action == "init"))

    if args.action == "list":
        files = sorted(d.glob("*.json")) if d.is_dir() else []
        return emit({
            "dir": str(d),
            "scenarios": [{"file": f.name, "name": _safe_name(f)} for f in files],
            "summary": f"{len(files)}개" if files else "시나리오 없음",
            "next": None if files else f"scenario init --name {{이름}} --root {root}",
        })

    if args.action == "init":
        if not args.name:
            return emit({"ok": False, "code": "name_required",
                         "error": "--name 으로 파일 이름을 정하세요"})
        f = d / f"{args.name}.json"
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
    f = d / f"{args.name}.json"
    if not f.exists():
        return emit({"ok": False, "code": "not_found", "error": f"{f} 없음",
                     "next": f"scenario list --root {root}"})
    import json
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return emit({"ok": False, "code": "invalid_json", "error": f"{f}: {e}"})

    problems = _validate(data)
    # 템플릿 자리를 안 채운 채 실행하면 엉뚱한 걸 누른다 — 문제로 잡는다
    placeholders = [k for k in json.dumps(data, ensure_ascii=False).split('"')
                    if k.startswith("{") and k.endswith("}")]
    if placeholders:
        problems.append(
            f"채우지 않은 자리가 {len(placeholders)}개 있습니다 — 템플릿 그대로면 실행할 수 없습니다")

    return emit({
        "ok": not problems,
        "code": "ok" if not problems else "scenario_invalid",
        "file": str(f),
        "scenario": data,
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

    p_doc = sub.add_parser("doctor", help="필요한 도구가 있는지 점검")
    p_doc.set_defaults(func=cmd_doctor)

    p_sc = sub.add_parser("scenario", help="프로젝트별 밟기 시나리오 관리")
    p_sc.add_argument("action", choices=["init", "list", "show"])
    p_sc.add_argument("--name", help="시나리오 파일 이름 (확장자 제외)")
    p_sc.add_argument("--root", default=".", help="프로젝트 루트")
    p_sc.add_argument("--force", action="store_true", help="init 시 덮어쓰기")
    p_sc.set_defaults(func=cmd_scenario)

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
