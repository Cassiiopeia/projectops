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
                          f"terminate {package}", "app launch  # start it again",
                          "Check the device and install state with device list",
                          package=package, was_running=was_running)


ACTION = Action(name="terminate", device_use="mutate", run=_app_terminate)
