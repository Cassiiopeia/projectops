"""열려 있는 브라우저에 붙고, 붙어 있는 동안만 사는 설정을 다시 건다 (CDP 재연결)."""
from __future__ import annotations

import time

import stealth

from pro_launch.runtime.browser import require_playwright


# 콘솔 오류는 **페이지가 열리는 동안** 난다. 열린 뒤에 리스너를 달면 이미 늦다 (#625).
_CONSOLE_HOOK = r"""
(() => {
  if (window.__projectops_console) return;
  const buf = [];
  window.__projectops_console = buf;
  const push = (type, text) => {
    try { buf.push({ type, text: String(text).slice(0, 2000), at: Date.now() }); } catch (e) {}
    if (buf.length > 500) buf.splice(0, buf.length - 500);   // 무한히 쌓이지 않게
  };
  for (const level of ["log", "info", "warn", "error"]) {
    const orig = console[level];
    console[level] = function (...args) {
      push(level, args.map((a) => {
        try { return typeof a === "string" ? a : JSON.stringify(a); }
        catch (e) { return String(a); }
      }).join(" "));
      return orig.apply(console, args);
    };
  }
  // console.error 를 거치지 않는 것들 — 이쪽이 진짜 사고인 경우가 많다
  window.addEventListener("error", (e) => push("error", e.message || String(e.error || e)));
  window.addEventListener("unhandledrejection",
    (e) => push("error", "unhandled rejection: " + String(e.reason)));
})();
"""


def install_console_hook(page) -> bool:
    try:
        page.add_init_script(_CONSOLE_HOOK)
        return True
    except Exception:
        return False


def apply_routes(page, rules: list[dict]) -> int:
    """응답 바꿔치기 규칙을 건다. 이 연결이 붙어 있는 동안만 산다."""
    n = 0
    for rule in rules:
        # Playwright 는 handler(route, request) 로 부른다. 기본 인자로 rule 을 묶으면
        # 두 번째 인자(request)가 그 자리를 덮는다 — 실측으로 겪었다. 클로저로 묶는다.
        page_route = _route_handler(rule)
        try:
            page.route(rule["match"], page_route)
            n += 1
        except Exception:
            continue
    return n


def _route_handler(rule: dict):
    def handler(route, *_):
        if rule.get("delay_ms"):
            time.sleep(rule["delay_ms"] / 1000)
        if rule.get("status") is None:
            route.continue_()
            return
        route.fulfill(status=int(rule["status"]),
                      headers={"content-type": rule.get("content_type") or "application/json",
                               "access-control-allow-origin": "*"},
                      body=rule.get("body") or "")
    return handler


def install_stealth(ctx, page) -> bool:
    """자동화 표식 가리기 스크립트를 건다. 컨텍스트에 걸어야 붙어 있는 동안 뜨는 팝업(로그인 창)도 덮는다."""
    ok = True
    for script in stealth.init_scripts():
        try:
            ctx.add_init_script(script)
        except Exception:
            try:
                page.add_init_script(script)
            except Exception:
                ok = False
    return ok


def close_blank_tabs(ctx, keep) -> int:
    """작업 탭(keep) 외의 about:blank 탭을 닫는다.
    web open 마다 about:blank 로 띄우고 영속 프로필이 옛 탭을 복원해서 빈 탭이 쌓인다."""
    closed = 0
    for pg in list(ctx.pages):
        try:
            if pg != keep and pg.url == "about:blank":
                pg.close()
                closed += 1
        except Exception:
            pass
    return closed


def web_connect(state: dict):
    """열려 있는 브라우저에 붙고, 붙어 있는 동안만 사는 설정(훅·stealth·뷰포트·규칙·대화상자)을 다시 건다."""
    sync_playwright, err = require_playwright()
    if err:
        return None, err
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(state["cdp"])
    except Exception as e:
        pw.stop()
        return None, {"ok": False, "code": "browser_gone",
                      "error": f"열린 브라우저에 붙지 못했습니다: {e}",
                      "next": "web open  # 다시 엽니다"}
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    # 마지막 탭을 본다. 프로필이 영속이라 Chromium 이 옛 탭을 되살리는데,
    # pages[0] 을 잡으면 방금 연 탭이 아니라 그 옛 탭을 몰게 된다(실측).
    page = work_page(ctx)
    # 옛 상태 파일(키 없음)은 켠 것으로 본다 — 끄는 것은 --no-stealth 로 명시할 때뿐이다
    if state.get("stealth", True):
        install_stealth(ctx, page)
    install_console_hook(page)
    vp = state.get("viewport")
    if vp:
        try:
            page.set_viewport_size({"width": int(vp[0]), "height": int(vp[1])})
        except Exception:
            pass
    apply_routes(page, state.get("routes") or [])
    arm_dialog(page, state)
    return (pw, browser, page), None


# 이번 호출 중에 뜬 대화상자 기록을 디스패처에 넘기는 상태 키 — 결과에 실린 뒤 지워진다
DIALOG_EVENT_KEY = "_dialog_event"


def arm_dialog(page, state: dict) -> bool:
    """대화상자(alert·confirm·prompt) 처리를 건다. 붙을 때마다 다시 건다 — 연결이 끊기면 사라진다 (#625).

    `web dialog` 로 걸어 둔 처리(state["dialog"])는 다음 한 번에만 쓰고 지운다.
    걸어 둔 것이 없으면 닫는다(dismiss) — Playwright 기본 동작과 같고, 뜬 사실만 결과에 남긴다.
    """
    try:
        page.on("dialog", dialog_handler(state))
        return True
    except Exception:
        return False


def dialog_handler(state: dict):
    def handler(dialog) -> None:
        plan = state.pop("dialog", None) or {}
        should_accept = plan.get("action") == "accept"
        event = {"type": getattr(dialog, "type", None), "message": (getattr(dialog, "message", "") or "")[:300],
                 "handled": "accept" if should_accept else "dismiss", "armed": bool(plan)}
        try:
            if should_accept:
                prompt_text = plan.get("text")
                dialog.accept(prompt_text) if prompt_text is not None else dialog.accept()
            else:
                dialog.dismiss()
        except Exception as e:   # 이미 닫힌 대화상자 — 기록만 남긴다
            event["error"] = str(e)[:200]
        state[DIALOG_EVENT_KEY] = event
    return handler


# Chrome 이 스스로 띄우는 안내 탭. 작업 탭이 아니다
_BROWSER_INTERNAL = ("chrome://", "chrome-untrusted://", "devtools://", "edge://")


def work_page(ctx):
    """작업에 쓸 탭을 고른다.

    영속 프로필은 옛 탭을 되살리고, 설치된 Chrome 은 시작할 때 안내 탭(chrome://privacy-sandbox-dialog 등)을
    함께 띄운다. 그냥 마지막 탭을 쓰면 그 안내 탭을 잡았다가, 이동하는 순간 Chrome 이 닫아 버려
    'Target page, context or browser has been closed' 로 실패한다(#860 실측, 순서는 실행마다 달랐다).
    chrome:// 가 아닌 탭 중 마지막 것을 쓰고, 없으면 새로 연다.
    """
    live = [p for p in ctx.pages if not p.is_closed()]
    usable = [p for p in live if not p.url.startswith(_BROWSER_INTERNAL)]
    return usable[-1] if usable else ctx.new_page()


def safe_title(page) -> str:
    """제목을 읽는다. 리다이렉트 도중에 읽으면 'Execution context was destroyed' 로 터지므로
    로드가 끝나길 기다렸다 다시 읽는다 (#860)."""
    return read_url_title(page)[1]


def read_url_title(page, timeout: int = 10) -> tuple[str, str]:
    """주소와 제목을 읽는다. 서버·스크립트 리다이렉트 도중에 title() 을 부르면
    'Execution context was destroyed' 로 터진다 — 로드가 끝나길 기다렸다 다시 읽는다."""
    for _ in range(3):
        try:
            page.wait_for_load_state("load", timeout=timeout * 1000)
        except Exception:
            pass
        try:
            return page.url, page.title()
        except Exception:
            time.sleep(0.5)
    return page.url, ""


def settle(page, state: dict, timeout: int) -> None:
    """바꿔치기 규칙이 있으면 요청이 다 끝날 때까지 기다린다.

    규칙은 이 연결이 끊기면 사라진다. 로드가 끝나기 전에 떨어지면 뒤늦은 API 요청은
    진짜 응답을 받는다 — 빈 목록을 연출했는데 목록이 채워지는 이유가 이것이다.
    """
    if not state.get("routes"):
        return
    try:
        page.wait_for_load_state("networkidle", timeout=min(timeout, 15) * 1000)
    except Exception:
        pass


def done_payload(action: str, page) -> dict:
    """화면을 바꾸지 않은 동작(goto·type)의 공통 결과 — 지금 주소와 제목을 알려 준다.

    주소와 제목을 한 번에 읽는다. 따로 읽으면 리다이렉트 사이에 낀 서로 다른 시점의 값이 섞인다.
    """
    url, title = read_url_title(page)
    return {"action": action, "url": url, "title": title,
            "summary": f"{action} 완료 — {url}",
            "next": "web text  # 결과 화면의 글자를 읽는다"}
