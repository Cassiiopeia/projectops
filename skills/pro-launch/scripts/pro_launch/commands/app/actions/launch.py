"""`app launch` — 앱을 띄운다 (띄운 뒤 앞에 있는지까지 확인)."""
from __future__ import annotations

import time

from pro_launch.commands.app.app_control import control_result, launch_package, resolve_target
from pro_launch.commands.app.launch_check import check_after_launch, device_use_fields, launch_failure_response
from pro_launch.registry import Action
from pro_launch.runtime.context import project_root


def _app_launch(args) -> int:
    platform, dev_id, package, err = resolve_target(args)
    if err is not None:
        return err
    owner = device_use_fields(dev_id, str(project_root(args)))
    launched_epoch = time.time()
    ok, detail = launch_package(platform, dev_id, package)
    if ok:
        # 띄우라고 보낸 것과 앞에 나온 것은 다르다 (#923)
        check = check_after_launch(platform, dev_id, package, launched_epoch)
        if check["state"] in ("not_foreground", "app_exited"):
            return launch_failure_response("launch", platform, dev_id, package, check)
        if check.get("foreground_package"):
            owner = {**owner, "foreground_package": check["foreground_package"]}
    return control_result("launch", platform, dev_id, ok, detail or "앱을 띄우지 못했습니다", "launch_failed",
                          f"{package} 실행", "app shot  # 뜬 화면을 봅니다",
                          "설치돼 있는지 확인하세요 (device list 의 installed)", package=package, **owner)


ACTION = Action(name="launch", run=_app_launch)
