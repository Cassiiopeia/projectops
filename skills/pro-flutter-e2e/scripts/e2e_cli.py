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


# =========================================================================
# 학습 노트 — 이 프로젝트에서만 통하는 것을 쌓아 간다
# =========================================================================

_NOTE_FILE = "learned.json"


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

    empty = {"schema": _NOTE_SCHEMA, "screens": {}, "pitfalls": [], "runs": []}
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
            "screens": notes.get("screens", {}),
            "pitfalls": notes.get("pitfalls", []),
            "pitfalls_to_promote": [
                x for x in notes.get("pitfalls", [])
                if x.get("scope", "project") != "project"
            ],
            "runs": notes.get("runs", [])[-5:],
            **({"warning": warning} if warning else {}),
            "summary": (f"화면 {len(notes.get('screens', {}))}개 · "
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

    p_e = sub.add_parser("edges", help="코드에서 밟아야 할 실패 경로를 뽑는다")
    p_e.add_argument("--path", default=".", help="프로젝트 경로")
    p_e.add_argument("--samples", type=int, default=3, help="분류별로 보여줄 예시 수")
    p_e.set_defaults(func=cmd_edges)

    p_n = sub.add_parser("note", help="이 프로젝트에서 알아낸 것을 쌓는다")
    p_n.add_argument("action", choices=["show", "screen", "pitfall", "run"])
    p_n.add_argument("--root", default=".")
    p_n.add_argument("--name", help="screen: 화면 이름 / run: 시나리오 이름")
    p_n.add_argument("--anchor", help="screen: 이 화면임을 알아보는 단서(문구 등)")
    p_n.add_argument("--taps", nargs="*", help="screen: '라벨=x,y' 형태로 여러 개")
    p_n.add_argument("--screen-size", help="screen: 좌표를 잰 해상도. 예 1080x2400")
    p_n.add_argument("--text", help="pitfall: 함정 내용 / run: 결과 요약")
    p_n.add_argument(
        "--scope", choices=["project", "flutter", "platform"], default="project",
        help=("pitfall 범위. project=이 앱에서만 / flutter=모든 Flutter 앱 / "
              "platform=기기·OS 차원. project가 아니면 skill로 올리라고 안내한다"))
    p_n.set_defaults(func=cmd_note)

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
