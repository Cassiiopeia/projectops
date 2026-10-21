"""`web dialog` — 다음에 뜰 대화상자(alert·confirm·prompt)를 어떻게 처리할지 미리 건다 (#892).

대화상자는 누르는 순간 뜨므로 뜬 뒤에 처리하면 늦다. 상태 파일에 적어 두고 붙을 때마다 다시 건다
(`session.arm_dialog`, #625). 한 번 쓰면 지워진다. 처리 결과는 그 호출의 결과 `dialog` 에 실린다.
"""
from __future__ import annotations

from pathlib import Path

from pro_launch.registry import Action
from pro_launch.runtime.browser import write_state
from pro_launch.runtime.output import out


def execute(args, state: dict, state_f: Path) -> int:
    if args.clear:
        state.pop("dialog", None)
        write_state(state_f, state)
        return out({"action": "dialog", "armed": None,
                    "summary": "Dialog handling cleared (dialogs get dismissed)"})
    if not (args.accept or args.dismiss):
        return out({"action": "dialog", "armed": state.get("dialog"),
                    "summary": "Armed handling: " + (state["dialog"]["action"] if state.get("dialog") else "none (dialogs get dismissed)"),
                    "hint": "web dialog --accept [--text <prompt input>] or --dismiss"})
    plan = {"action": "accept" if args.accept else "dismiss"}
    if args.accept and args.text is not None:
        plan["text"] = args.text
    state["dialog"] = plan
    write_state(state_f, state)
    return out({"action": "dialog", "armed": plan,
                "summary": f"The next dialog will be {'accepted' if args.accept else 'dismissed'} (once)",
                "next": "web click --ref <number>  # the action that opens the dialog. Its result carries what was done in dialog"})


def configure(p) -> None:
    group = p.add_mutually_exclusive_group()
    group.add_argument("--accept", action="store_true", help="Accept (OK on confirm · prompt gets --text)")
    group.add_argument("--dismiss", action="store_true", help="Dismiss (Cancel)")


ACTION = Action(name="dialog", needs="state_offline", run=execute, configure=configure,
                options=("text", "clear"),
                help="Arm the next dialog (alert · confirm · prompt) to be accepted or dismissed (once)",
                example='web dialog --accept --text "New name"')
