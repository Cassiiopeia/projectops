"""`app tree` — show tappable elements and the screen language."""
from __future__ import annotations


import app_input

from pro_launch.commands.app.gestures import (backend_for, elapsed_seconds, ios_failure_fields, session_fields,
                                              device_failure_response, with_session_advice)
from pro_launch.registry import Action
from pro_launch.runtime.foreground import read_android_foreground
from pro_launch.runtime.output import out


def _app_tree(args) -> int:
    """Tappable elements and the screen language — for choosing tap's --text/--id/--desc."""
    be, dev_id, err = backend_for(args)
    if err is not None:
        return err
    nodes = be.nodes(dev_id)
    if nodes is None:
        return out({"ok": False, "code": "tree_unsupported", "error": f"{be.name} cannot read the screen structure"})
    if not nodes and be.device_failure:
        return device_failure_response(be, dev_id, args)
    diagnostics = ios_failure_fields(be, dev_id) if not nodes else {}
    # If no elements were read, check whether another app covers the screen (Android, on failure only — dumpsys on every call is slow on a stressed device)
    if not nodes and be.name == "android":
        foreground = read_android_foreground(dev_id)
        if foreground["is_readable"]:
            diagnostics["foreground_package"] = foreground["package"]
    els = app_input.slim([n for n in nodes if n["text"] or n["desc"] or (n["clickable"] and n["id"])])
    result = {"ok": bool(els), "code": "ok" if els else "ui_dump_failed", "device": dev_id,
              "platform": be.name, "locale": be.locale(dev_id), "count": len(els), "elements": els,
              "elapsed_seconds": elapsed_seconds(args), **session_fields(be), **diagnostics,
              "summary": f"{len(els)} elements", "next": "app tap --text '<text from elements>'"}
    return out(with_session_advice(result, be, dev_id, args))


ACTION = Action(name="tree", device_use="read", run=_app_tree)
