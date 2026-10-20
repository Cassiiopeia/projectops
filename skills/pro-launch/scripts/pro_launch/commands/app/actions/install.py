"""`app install` — 빌드를 기기에 설치한다 (Android .apk · iOS 시뮬레이터 .app) (#924)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from pro_launch.commands.app.app_control import resolve_target
from pro_launch.registry import Action
from pro_launch.runtime.android_device import host_pressure_fields, install_apk
from pro_launch.runtime.output import out

# simctl install 한 번의 최대 대기 (초)
IOS_INSTALL_TIMEOUT_SECONDS = 300


def _install_ios(udid: str, app_path: Path) -> dict:
    try:
        r = subprocess.run(["xcrun", "simctl", "install", udid, str(app_path)], capture_output=True,
                           text=True, timeout=IOS_INSTALL_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return {"is_ok": False, "code": "device_unresponsive", "step": "install",
                "detail": f"응답 없음 ({IOS_INSTALL_TIMEOUT_SECONDS}초)", **host_pressure_fields(),
                "next": f"device reboot --device {udid}"}
    except OSError as error:
        return {"is_ok": False, "code": "install_failed", "step": "install", "detail": str(error)}
    if r.returncode != 0:
        return {"is_ok": False, "code": "install_failed", "step": "install",
                "detail": ((r.stderr or "") + (r.stdout or "")).strip()[-300:]}
    return {"is_ok": True, "code": "ok", "step": "install", "detail": "Success", "retried": False}


def _invalid_path(code: str, error: str, hint: str) -> int:
    return out({"ok": False, "code": code, "error": error, "next": hint})


def _app_install(args) -> int:
    if not getattr(args, "path", None):
        return _invalid_path("args_required", "--path 가 필요합니다",
                             "app install --device $DEV --path build/app-debug.apk  (iOS 시뮬레이터는 Runner.app 폴더)")
    platform, dev_id, _, err = resolve_target(args, is_package_required=False)
    if err is not None:
        return err
    build_path = Path(args.path).expanduser()
    if not build_path.exists():
        return _invalid_path("install_path_missing", f"{build_path} 가 없습니다", "빌드를 먼저 만들었는지 경로를 확인한다")
    suffix = build_path.suffix.lower()
    is_valid_build = (suffix == ".apk" and build_path.is_file()) if platform == "android" else \
        (suffix == ".app" and build_path.is_dir())
    if not is_valid_build:
        expected = ".apk 파일" if platform == "android" else ".app 폴더 (시뮬레이터용 빌드 — .ipa 는 실기기용이라 설치하지 못한다)"
        return _invalid_path("install_path_invalid", f"{platform} 에는 {expected}를 설치한다: {build_path}",
                             "flutter build apk --debug / xcodebuild -sdk iphonesimulator 의 산출물을 쓴다")
    result = install_apk(dev_id, build_path.resolve()) if platform == "android" else \
        _install_ios(dev_id, build_path.resolve())
    common = {"action": "install", "platform": platform, "device": dev_id, "path": str(build_path)}
    if result["is_ok"]:
        return out({"ok": True, "code": "ok", **common, "retried": result.get("retried", False),
                    "summary": f"{build_path.name} 설치 완료", "next": "app launch  # 설치한 앱을 띄운다"})
    return out({"ok": False, "code": result["code"], **common, "step": result["step"],
                "error": f"{result['step']} 단계 실패: {result['detail']}",
                "retried": result.get("retried", False),
                **{k: result[k] for k in ("resources", "host_advice") if k in result},
                "summary": f"{build_path.name} 설치 실패 ({result['step']})",
                "next": result.get("next") or "device list 로 기기 상태를 확인하고 다시 시도한다"})


def _configure(p) -> None:
    p.add_argument("--path", default=None, help="install: 설치할 빌드 — Android .apk 파일 · iOS 시뮬레이터 .app 폴더")


ACTION = Action(name="install", device_use="mutate", run=_app_install, configure=_configure)
