"""`app openurl` — open a deep link or URL on the device (iOS simctl openurl, Android VIEW intent)."""
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
                    "error": "--url needs an address with a scheme (e.g. myapp://home, https://...)",
                    "next": "app openurl --url 'myapp://path'"})
    platform, dev_id, _, err = resolve_target(args, is_package_required=False)
    if err is not None:
        return err
    if platform == "android":
        # adb shell re-parses arguments in the device shell — quote the URL so & and ? do not cut it off
        command = ["shell", "am", "start", "-W", "-a", "android.intent.action.VIEW", "-d", shlex.quote(url)]
        if getattr(args, "pkg", None):
            command += ["-p", args.pkg]
        ok, detail = run_tool(adb_command(dev_id, *command))
    else:
        ok, detail = run_tool(["xcrun", "simctl", "openurl", dev_id, url])
    return control_result("openurl", platform, dev_id, ok, detail, "openurl_failed",
                          f"open {url}", "app shot  # check the screen that opened",
                          "Check that the app registers this scheme (Info.plist · intent-filter)", url=url)


def configure(p) -> None:
    p.add_argument("--url", default=None, help="openurl: deep link / URL to open (e.g. myapp://home)")


ACTION = Action(name="openurl", device_use="mutate", run=_app_openurl, configure=configure)
