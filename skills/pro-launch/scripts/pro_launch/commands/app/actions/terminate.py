"""`app terminate` — 앱을 끈다 (iOS simctl terminate · Android am force-stop)."""
from __future__ import annotations

from pro_launch.commands.app.app_control import control_result, resolve_target, terminate_package
from pro_launch.registry import Action


def _app_terminate(args) -> int:
    platform, dev_id, package, err = resolve_target(args)
    if err is not None:
        return err
    ok, was_running, detail = terminate_package(platform, dev_id, package)
    return control_result("terminate", platform, dev_id, ok, detail, "terminate_failed",
                          f"{package} 종료", "app launch  # 다시 띄운다",
                          "device list 로 기기·설치 상태를 확인한다",
                          package=package, was_running=was_running)


ACTION = Action(name="terminate", device_use="mutate", run=_app_terminate)
