"""`app launch` — 앱을 띄운다 (띄운 뒤 앞에 있는지까지 확인)."""
from __future__ import annotations

import time

from pro_launch.commands.app.app_control import control_result, launch_package, resolve_target
from pro_launch.commands.app.launch_check import check_after_launch, launch_failure_response
from pro_launch.registry import Action


def _app_launch(args) -> int:
    platform, dev_id, package, err = resolve_target(args)
    if err is not None:
        return err
    foreground_fields: dict = {}
    launched_epoch = time.time()
    ok, detail = launch_package(platform, dev_id, package)
    if ok:
        # 띄우라고 보낸 것과 앞에 나온 것은 다르다 (#923)
        check = check_after_launch(platform, dev_id, package, launched_epoch)
        if check["state"] in ("not_foreground", "app_exited"):
            return launch_failure_response("launch", platform, dev_id, package, check)
        if check.get("foreground_package"):
            foreground_fields = {"foreground_package": check["foreground_package"]}
    return control_result("launch", platform, dev_id, ok, detail or "Could not start the app", "launch_failed",
                          f"launch {package}", "app shot  # look at the screen that came up",
                          "Check that it is installed (installed in device list)", package=package, **foreground_fields)


ACTION = Action(name="launch", device_use="mutate", run=_app_launch)
