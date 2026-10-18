"""`app relaunch` — 앱을 끄고 다시 띄운다 (상태 초기화 없이 처음 화면부터)."""
from __future__ import annotations

import time

from pro_launch.commands.app.app_control import (control_result, launch_package, resolve_target,
                                                 terminate_package)
from pro_launch.commands.app.launch_check import check_after_launch, device_use_fields, launch_failure_response
from pro_launch.registry import Action
from pro_launch.runtime.context import project_root


def _app_relaunch(args) -> int:
    platform, dev_id, package, err = resolve_target(args)
    if err is not None:
        return err
    owner = device_use_fields(dev_id, str(project_root(args)))
    # 끄기 > 띄우기 (끄기 실패면 띄우지 않는다 — 옛 프로세스 위에 덮이면 재시작이 아니다)
    ok, was_running, detail = terminate_package(platform, dev_id, package)
    if not ok:
        return control_result("relaunch", platform, dev_id, ok, detail, "terminate_failed",
                              f"{package} 재시작", None, "device list 로 기기·설치 상태를 확인한다",
                              package=package, **owner)
    launched_epoch = time.time()
    ok, detail = launch_package(platform, dev_id, package)
    if ok:
        # 띄운 뒤 앞에 있는지 확인 (#923)
        check = check_after_launch(platform, dev_id, package, launched_epoch)
        if check["state"] in ("not_foreground", "app_exited"):
            return launch_failure_response("relaunch", platform, dev_id, package, check, was_running=was_running)
        if check.get("foreground_package"):
            owner = {**owner, "foreground_package": check["foreground_package"]}
    return control_result("relaunch", platform, dev_id, ok, detail or "앱을 띄우지 못했습니다",
                          "launch_failed", f"{package} 재시작", "app shot  # 뜬 화면을 봅니다",
                          "설치돼 있는지 확인하세요 (device list 의 installed)",
                          package=package, was_running=was_running, **owner)


ACTION = Action(name="relaunch", run=_app_relaunch)
