"""`app launch` — 앱을 띄운다."""
from __future__ import annotations

from pro_launch.commands.app.app_control import control_result, launch_package, resolve_target
from pro_launch.registry import Action


def _app_launch(args) -> int:
    platform, dev_id, package, err = resolve_target(args)
    if err is not None:
        return err
    ok, detail = launch_package(platform, dev_id, package)
    return control_result("launch", platform, dev_id, ok, detail or "앱을 띄우지 못했습니다", "launch_failed",
                          f"{package} 실행", "app shot  # 뜬 화면을 봅니다",
                          "설치돼 있는지 확인하세요 (device list 의 installed)", package=package)


ACTION = Action(name="launch", run=_app_launch)
