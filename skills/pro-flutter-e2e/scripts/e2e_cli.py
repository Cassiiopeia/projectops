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
