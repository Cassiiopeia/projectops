"""`app openurl` — 딥링크·URL 을 기기에서 연다 (iOS simctl openurl · Android VIEW 인텐트)."""
from __future__ import annotations

import shlex

from pro_launch.commands.app.app_control import adb_command, control_result, resolve_target, run_tool
from pro_launch.registry import Action
from pro_launch.runtime.output import out


def _has_scheme(url: str | None) -> bool:
    scheme, separator, rest = (url or "").partition(":")
    return bool(separator and rest and scheme and scheme.replace("+", "").replace("-", "").replace(".", "").isalnum())


def _app_openurl(args) -> int:
    url = getattr(args, "url", None)
    if not _has_scheme(url):
        return out({"ok": False, "code": "url_required",
                    "error": "--url 에 scheme 이 있는 주소가 필요하다 (예: myapp://home, https://...)",
                    "next": "app openurl --url 'myapp://path'"})
    platform, dev_id, _, err = resolve_target(args, is_package_required=False)
    if err is not None:
        return err
    if platform == "android":
        # adb shell 은 인자를 기기 셸에서 다시 해석한다 — & ? 가 든 URL 이 잘리지 않게 따옴표로 감싼다
        command = ["shell", "am", "start", "-W", "-a", "android.intent.action.VIEW", "-d", shlex.quote(url)]
        if getattr(args, "pkg", None):
            command += ["-p", args.pkg]
        ok, detail = run_tool(adb_command(dev_id, *command))
    else:
        ok, detail = run_tool(["xcrun", "simctl", "openurl", dev_id, url])
    return control_result("openurl", platform, dev_id, ok, detail, "openurl_failed",
                          f"{url} 열기", "app shot  # 열린 화면을 확인한다",
                          "앱이 이 scheme 을 등록했는지(Info.plist · intent-filter) 확인한다", url=url)


def configure(p) -> None:
    p.add_argument("--url", default=None, help="openurl: 열 딥링크·URL (예: myapp://home)")


ACTION = Action(name="openurl", device_use="mutate", run=_app_openurl, configure=configure)
