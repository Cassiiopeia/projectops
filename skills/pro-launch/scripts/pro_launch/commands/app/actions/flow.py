"""`app flow` — 프로젝트의 Maestro flow 파일을 기기에서 돌리고 명령별 결과 · 캡처를 JSON 하나로 돌려준다 (#862).

`app tap|swipe|run` 으로 안 되는 복잡한 제스처(밀고 곧바로 탭, 재시도 탭, 조건 대기)는 전용 옵션을 늘리지 않고
Maestro flow 로 쓴다. 이 동작은 그 flow 를 실행하는 통로만 맡는다: 실행 > driver 기동 실패면 한 번 다시 > 결과.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import app_input
import maestro_runs

from pro_launch.commands.app import steps as steps_module
from pro_launch.commands.app.gestures import auto_record_backend, backend_for, elapsed_seconds
from pro_launch.registry import Action
from pro_launch.runtime.context import project_root
from pro_launch.runtime.output import out
from pro_launch.runtime.shots import finish_shot, shot_target

# flow 한 번의 대기 기본 · 최대 (초) — Maestro 기동만 30~40초 (iOS 시뮬레이터 실측 33초)
DEFAULT_FLOW_TIMEOUT_SECONDS = 300
MAXIMUM_FLOW_TIMEOUT_SECONDS = 1800
# Maestro driver 가 시간 안에 안 뜬 출력 (Android 실측, 에뮬레이터 과부하) — 한 번만 다시 시도
DRIVER_START_TIMEOUT_MARKERS = ("did not start up in time",)
# Android 에 깔리는 Maestro driver 앱 — 다시 시도 전 강제 종료 (호스트의 다른 maestro 프로세스는 건드리지 않는다)
ANDROID_MAESTRO_DRIVER_PACKAGES = ("dev.mobile.maestro", "dev.mobile.maestro.test")
# 실패 원인으로 남길 출력 줄 수
FAILURE_DETAIL_LINE_COUNT = 8
# 응답 code 4개 > 다음 행동
FLOW_OUTCOMES = (
    {"code": "ok", "next": "screenshots 이미지를 읽어 결과를 확인한다"},
    {"code": "flow_failed", "next": "failed_command 를 app tree 로 보고 flow 를 고쳐 다시 app flow"},
    {"code": "flow_timeout", "next": "--timeout 을 늘리거나 flow 를 나눈다"},
    {"code": "maestro_driver_timeout",
     "next": "기계 과부하다 — 빌드 등 무거운 작업을 멈추거나 에뮬레이터를 cold boot 한다 (사용자에게 먼저 묻는다)"},
)
NEXT_HINT_BY_CODE = {outcome["code"]: outcome["next"] for outcome in FLOW_OUTCOMES}


def is_driver_start_timeout(lines: list[str]) -> bool:
    return any(marker in line for line in lines for marker in DRIVER_START_TIMEOUT_MARKERS)


def collect_flow_screenshots(output_folder: Path) -> list[Path]:
    """`--test-output-dir` 아래 takeScreenshot 결과 (<시각>/<flow>/takeScreenshot/<이름>.png), 찍은 순서."""
    return sorted(output_folder.glob("**/takeScreenshot/*.png"), key=lambda p: p.stat().st_mtime)


def _app_flow(args) -> int:
    """flow 파일 실행: 검증 > 기기 > Maestro 실행(driver 기동 실패면 정리 후 1회 더) > 캡처 옮기기 > 결과."""
    flow_file = Path(getattr(args, "file", None) or "")
    if not getattr(args, "file", None) or not flow_file.is_file():
        return out({"ok": False, "code": "flow_file_required",
                    "error": f"--file 에 Maestro flow(yaml) 경로가 필요하다 (받은 값: {getattr(args, 'file', None)!r})",
                    "next": "references/app.md 의 '제스처 플레이북' 예시 flow 를 본다"})
    timeout_seconds = getattr(args, "timeout", None) or DEFAULT_FLOW_TIMEOUT_SECONDS
    if not 0 < timeout_seconds <= MAXIMUM_FLOW_TIMEOUT_SECONDS:
        return out({"ok": False, "code": "bad_timeout",
                    "error": f"--timeout 은 1~{MAXIMUM_FLOW_TIMEOUT_SECONDS} 초다"})
    be, dev_id, err = backend_for(args)
    if err is not None:
        return err
    maestro = app_input.IOSMaestroBackend._maestro()
    if not maestro:
        return out({"ok": False, "code": "maestro_tool_missing", "error": "Maestro 가 없다",
                    "next": app_input.IOSMaestroBackend.install_hint})

    with tempfile.TemporaryDirectory() as output_folder:
        is_success, lines, retried = _run_with_driver_retry(maestro, be.name, dev_id, flow_file,
                                                            Path(output_folder), timeout_seconds)
        screenshots = [str(_keep_screenshot(args, png)) for png in collect_flow_screenshots(Path(output_folder))]
    return _flow_result(args, be, dev_id, flow_file, is_success, lines, retried, screenshots)


def _run_with_driver_retry(maestro: str, platform: str, dev_id: str, flow_file: Path,
                           output_folder: Path, timeout_seconds: int) -> tuple[bool | None, list[str], bool]:
    """(성공 여부 · 시간 초과면 None, 출력 줄, 다시 시도했나). driver 가 시간 안에 안 뜨면 정리하고 한 번만 더."""
    is_success, lines = _run_maestro(maestro, dev_id, flow_file, output_folder, timeout_seconds)
    if is_success or not is_driver_start_timeout(lines):
        return is_success, lines, False
    if platform == "android":
        for package in ANDROID_MAESTRO_DRIVER_PACKAGES:
            subprocess.run([app_input.sdk_tool("adb"), "-s", dev_id, "shell", "am", "force-stop", package],
                           capture_output=True, timeout=15)
    is_success, lines = _run_maestro(maestro, dev_id, flow_file, output_folder, timeout_seconds)
    return is_success, lines, True


def _run_maestro(maestro: str, dev_id: str, flow_file: Path, output_folder: Path,
                 timeout_seconds: int) -> tuple[bool | None, list[str]]:
    # 기록(maestro.log 에 입력값이 평문으로 남는다)은 임시 폴더로 돌려 함께 지운다
    command = [maestro, *(["--device", dev_id] if dev_id != "booted" else []),
               "test", "--test-output-dir", str(output_folder), str(flow_file)]
    try:
        r = maestro_runs.run_recorded(command, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        return None, [f"maestro 응답 없음 ({timeout_seconds}초)"]
    # 끝의 광고 상자(│ ╭ ╰)를 걷어야 실패 원인 줄이 보인다
    lines = [l for l in ((r.stdout or "") + (r.stderr or "")).splitlines()
             if l.strip() and not l.lstrip().startswith(("│", "╭", "╰"))]
    return r.returncode == 0, lines


def _keep_screenshot(args, png: Path) -> Path:
    """takeScreenshot 결과 > SHOT_DIR (이름 앞에 --shot 접두, 기본은 WebP 로 줄인다)."""
    prefix = getattr(args, "shot", None)
    raw, _ = shot_target(project_root(args), f"{prefix}_{png.stem}" if prefix else png.stem)
    shutil.copyfile(png, raw)
    return finish_shot(raw, False, args)


def _result_code(is_success: bool | None, lines: list[str]) -> str:
    """성공 > 시간 초과 > driver 기동 실패 > 그 밖의 flow 실패 순으로 응답 code."""
    if is_success:
        return "ok"
    if is_success is None:
        return "flow_timeout"
    if is_driver_start_timeout(lines):
        return "maestro_driver_timeout"
    return "flow_failed"


def _flow_result(args, be, dev_id: str, flow_file: Path, is_success: bool | None, lines: list[str],
                 retried: bool, screenshots: list[str]) -> int:
    """명령별 상태 + 캡처 + 원인 code > JSON 하나."""
    commands = [{"command": description, "status": status.lower()}
                for description, status in steps_module.maestro_statuses(lines)]
    failed_command = next((c["command"] for c in commands if c["status"] == "failed"), None)
    code = _result_code(is_success, lines)
    reason = [l for l in lines if "FAILED" in l or "Error" in l or "not found" in l.lower() or "응답 없음" in l]
    payload = {"ok": bool(is_success), "code": code, "device": dev_id, "via": be.name, "flow": str(flow_file),
               "commands": commands, "failed_command": failed_command, "screenshots": screenshots,
               "driver_retried": retried,
               "error": None if is_success else "\n".join((reason or lines)[-FAILURE_DETAIL_LINE_COUNT:])[-600:],
               "elapsed_seconds": elapsed_seconds(args)}
    if is_success:
        auto_record_backend(be)
    payload["summary"] = (f"flow 완료 — 명령 {len(commands)}개, 캡처 {len(screenshots)}장" if is_success
                          else f"실패 — {code}" + (f" ({failed_command})" if failed_command else ""))
    payload["next"] = NEXT_HINT_BY_CODE[code]
    return out(payload)


def configure(p) -> None:
    p.add_argument("--file", default=None, help="flow: 실행할 Maestro flow(yaml) 경로")
    p.add_argument("--timeout", type=int, default=None,
                   help=f"flow: 최대 대기 초 (기본 {DEFAULT_FLOW_TIMEOUT_SECONDS}, 최대 {MAXIMUM_FLOW_TIMEOUT_SECONDS})")


ACTION = Action(name="flow", run=_app_flow, configure=configure,
                help="프로젝트의 Maestro flow 를 돌리고 명령별 결과 · takeScreenshot 캡처를 JSON 으로 — 복잡한 제스처용",
                example="app flow --device $DEV --file .maestro/swipe_undo.yaml --shot undo")
