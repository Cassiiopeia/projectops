"""`desktop find` — 글자·id·종류로 후보를 고르고 번호(ref)를 붙인다. 위험 버튼은 mutating: true."""
from __future__ import annotations

from pro_launch.commands.desktop.actions.tree import find
from pro_launch.registry import Action


def configure(p) -> None:
    p.add_argument("--text", dest="sel_text", default=None, help="visible text (exact > normalized > contains)")
    p.add_argument("--id", dest="sel_id", default=None, help="automation id")
    p.add_argument("--desc", dest="sel_desc", default=None, help="help text / description")
    p.add_argument("--role", default=None, help="element kind (button, edit, checkbox, menuitem…)")


ACTION = Action(name="find", needs="nothing", run=find, configure=configure, options=("window", "limits"),
                device_use="read", help="Find elements by text, id or kind and number them (ref)",
                example="desktop find --text \"Next\"")
