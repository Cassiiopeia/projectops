"""`app tree` — 누를 수 있는 요소와 화면 언어를 본다."""
from __future__ import annotations


import app_input

from pro_launch.commands.app.gestures import backend_for, elapsed_seconds
from pro_launch.registry import Action
from pro_launch.runtime.output import out


def _app_tree(args) -> int:
    """누를 수 있는 요소와 화면 언어 — tap 의 --text/--id/--desc 를 고르는 용도."""
    be, dev_id, err = backend_for(args)
    if err is not None:
        return err
    nodes = be.nodes(dev_id)
    if nodes is None:
        return out({"ok": False, "code": "tree_unsupported", "error": f"{be.name} 은 화면 구조를 읽지 못한다"})
    els = app_input.slim([n for n in nodes if n["text"] or n["desc"] or (n["clickable"] and n["id"])])
    return out({"ok": bool(els), "code": "ok" if els else "ui_dump_failed", "device": dev_id,
                "platform": be.name, "locale": be.locale(dev_id), "count": len(els), "elements": els,
                "elapsed_seconds": elapsed_seconds(args),
                "summary": f"요소 {len(els)}개", "next": "app tap --text '<elements 의 text>'"})


ACTION = Action(name="tree", run=_app_tree)
