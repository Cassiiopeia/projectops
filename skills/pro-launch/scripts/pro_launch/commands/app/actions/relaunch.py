"""`app relaunch` — 앱을 끄고 다시 띄운다 (상태 초기화 없이 처음 화면부터)."""
from __future__ import annotations

import time

from pro_launch.commands.app.app_control import (control_result, launch_package, resolve_target,
                                                 terminate_package)
from pro_launch.commands.app.launch_check import check_after_launch, launch_failure_response
from pro_launch.registry import Action


def _app_relaunch(args) -> int:
    platform, dev_id, package, err = resolve_target(args)
    if err is not None:
        return err
    foreground_fields: dict = {}
    # 끄기 > 띄우기 (끄기 실패면 띄우지 않는다 — 옛 프로세스 위에 덮이면 재시작이 아니다)
    ok, was_running, detail = terminate_package(platform, dev_id, package)
    if not ok:
        return control_result("relaunch", platform, dev_id, ok, detail, "terminate_failed",
                              f"relaunch {package}", None, "Check the device and install state with device list",
                              package=package, **foreground_fields)
    launched_epoch = time.time()
    ok, detail = launch_package(platform, dev_id, package)
    if ok:
        # 띄운 뒤 앞에 있는지 확인 (#923)
        check = check_after_launch(platform, dev_id, package, launched_epoch)
        if check["state"] in ("not_foreground", "app_exited"):
            return launch_failure_response("relaunch", platform, dev_id, package, check, was_running=was_running)
        if check.get("foreground_package"):
            foreground_fields = {"foreground_package": check["foreground_package"]}
    return control_result("relaunch", platform, dev_id, ok, detail or "Could not start the app",
                          "launch_failed", f"relaunch {package}", "app shot  # look at the screen that came up",
                          "Check that it is installed (installed in device list)",
                          package=package, was_running=was_running, **foreground_fields)


ACTION = Action(name="relaunch", device_use="mutate", run=_app_relaunch)
