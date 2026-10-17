"""`web close` — 브라우저를 닫는다."""
from __future__ import annotations

from pathlib import Path

from pro_launch.commands.web.session import web_connect
from pro_launch.registry import Action
from pro_launch.runtime.browser import write_state
from pro_launch.runtime.output import out
from pro_launch.runtime.procs import kill_browser, manual_kill_command


def _web_close(state: dict, state_f: Path) -> int:
    pid = state.get("pid")
    alive = False
    if pid:
        try:
            alive = kill_browser(int(pid))
        except ValueError:
            pass
    # ⚠️ 살아 있으면 상태 파일을 남긴다. 지우면 떠 있는 브라우저에 다시 붙을 길이 사라진다(실측).
    if alive:
        return out({"ok": False, "code": "browser_still_alive", "pid": pid,
                    "error": f"브라우저(pid {pid})가 아직 살아 있습니다",
                    "next": f"{manual_kill_command(pid)}  # 직접 종료한 뒤 다시 여세요"})
    state_f.unlink(missing_ok=True)
    return out({"action": "close", "summary": "브라우저를 닫았습니다"})


def _close_by_connection(state: dict, state_f: Path) -> int:
    """pid 를 모르는 옛 상태 파일 — 연결해서 닫는 수밖에 없다."""
    conn, err = web_connect(state)
    if err:
        if err.get("code") == "browser_gone":
            # 죽은 브라우저 정보만 지운다. 뷰포트·규칙은 사람이 정한 것이라 남긴다
            for k in ("cdp", "pid"):
                state.pop(k, None)
            write_state(state_f, state)
        return out(err)
    pw, browser, _page = conn
    try:
        browser.close()
        state_f.unlink(missing_ok=True)
        return out({"action": "close", "summary": "브라우저를 닫았습니다"})
    except Exception as e:
        return out({"ok": False, "code": "web_action_failed", "action": "close",
                    "error": str(e)[:400], "next": "web shot  # 지금 화면이 무엇인지 먼저 봅니다"})
    finally:
        pw.stop()


def execute(args, state: dict, state_f: Path) -> int:
    if state.get("pid"):
        # 연결부터 맺지 않는다 — 응답 없는 브라우저에서는 연결·close 가 모두 멈춘다 (#712)
        return _web_close(state, state_f)
    return _close_by_connection(state, state_f)


ACTION = Action(name="close", needs="state_online", run=execute, options=(),
                help="브라우저를 닫는다", example="web close")
