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
                    "summary": "대화상자 처리를 풀었습니다 (뜨면 닫는다)"})
    if not (args.accept or args.dismiss):
        return out({"action": "dialog", "armed": state.get("dialog"),
                    "summary": "걸어 둔 처리: " + (state["dialog"]["action"] if state.get("dialog") else "없음 (뜨면 닫는다)"),
                    "hint": "web dialog --accept [--text <prompt 입력>] 또는 --dismiss"})
    plan = {"action": "accept" if args.accept else "dismiss"}
    if args.accept and args.text is not None:
        plan["text"] = args.text
    state["dialog"] = plan
    write_state(state_f, state)
    return out({"action": "dialog", "armed": plan,
                "summary": f"다음 대화상자를 {'수락' if args.accept else '거절'}합니다 (한 번)",
                "next": "web click --ref <번호>  # 대화상자를 띄우는 조작. 결과의 dialog 에 처리 내용이 실린다"})


def configure(p) -> None:
    group = p.add_mutually_exclusive_group()
    group.add_argument("--accept", action="store_true", help="수락 (confirm 확인 · prompt 는 --text 를 넣는다)")
    group.add_argument("--dismiss", action="store_true", help="거절 (취소)")


ACTION = Action(name="dialog", needs="state_offline", run=execute, configure=configure,
                options=("text", "clear"),
                help="다음 대화상자(alert·confirm·prompt)를 수락·거절하도록 미리 건다 (한 번)",
                example='web dialog --accept --text "새 이름"')
