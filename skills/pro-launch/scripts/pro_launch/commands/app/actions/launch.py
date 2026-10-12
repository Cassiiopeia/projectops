"""`app launch` — 앱을 띄운다."""
from __future__ import annotations

import os
import subprocess

from pro_launch.registry import Action
from pro_launch.runtime.context import project_root
from pro_launch.runtime.devices import adb_shell, load_devices, no_device_response, pick_device
from pro_launch.runtime.output import out


def _app_launch(args) -> int:
    root = project_root(args)
    platform, dev_id, dev = pick_device(args.device)
    if not platform:
        return no_device_response(dev, args.device)
    pkg = args.pkg or os.environ.get("PKG") or load_devices(root)["package"]
    if not pkg:
        return out({"ok": False, "code": "package_required",
                    "error": "띄울 앱을 모릅니다",
                    "next": "--pkg <패키지명·번들ID>  (detect 가 찾은 값을 쓰세요)"})
    if platform == "android":
        # monkey 는 런처 액티비티 이름을 몰라도 띄운다 — am start 는 액티비티까지 알아야 한다
        text = adb_shell(dev_id, "monkey", "-p", pkg, "-c",
                          "android.intent.category.LAUNCHER", "1")
        ok = "Events injected: 1" in text
        err = None if ok else (text.strip()[-300:] or "앱을 띄우지 못했습니다")
    else:
        r = subprocess.run(["xcrun", "simctl", "launch", dev_id, pkg],
                           capture_output=True, text=True, timeout=30)
        ok = r.returncode == 0
        err = None if ok else (r.stderr or "").strip()[:300]
    return out({"ok": ok, "code": "ok" if ok else "launch_failed",
                "platform": platform, "device": dev_id, "package": pkg, "error": err,
                "summary": f"{pkg} 실행" + ("" if ok else " 실패"),
                "next": "app shot  # 뜬 화면을 봅니다" if ok else
                        "설치돼 있는지 확인하세요 (device list 의 installed)"})


ACTION = Action(name="launch", run=_app_launch)
