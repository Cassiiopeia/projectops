"""`web login` — 저장된 자격증명을 지정한 입력칸에 넣고, 2단계 인증 등은 사용자에게 넘긴 뒤 조건이 맞으면 이어간다 (#881).

제공자별(Google·Apple …) 화면 자동화는 두지 않는다 — 화면이 제공자마다 달라 계속 깨진다.
틀만 일반적으로: 입력(선택자) > 제출 > 완료 조건(URL·문구) 대기 > 안 되면 사용자 인계(needs_user) > `--resume` 으로 재개.
값은 결과·오류·로그에 남기지 않는다 (명령줄에도 이름만 적는다).
"""
from __future__ import annotations

import os
import time

from pro_launch.commands.web.session import read_url_title
# 사용자 인계 대기 상한 — 명령 전체 시간 상한도 이 값을 더하므로 한 곳에 둔다
from pro_launch.commands.web.watchdog import MAXIMUM_HANDOFF_SECONDS
from pro_launch.registry import Action
from pro_launch.runtime.creds import load_cred, with_login_policy

# 아이디로 쓸 필드를 자동으로 고를 때 보는 순서
IDENTIFIER_FIELD_CANDIDATES = ("username", "account", "email", "user", "login", "id")
# 완료 조건을 다시 보는 간격 (초)
CONDITION_POLL_SECONDS = 1.0


def _pick_identifier_field(cred: dict, wanted: str | None) -> str | None:
    if wanted:
        return wanted
    return next((field for field in IDENTIFIER_FIELD_CANDIDATES if cred.get(field) not in (None, "")), None)


def _mask(text: str, secret_values: list[str]) -> str:
    for value in sorted(secret_values, key=len, reverse=True):
        if value:
            text = text.replace(value, "***")
    return text


def _fill_otp(page, selector: str, code: str, timeout_ms: int) -> int:
    """일회용 코드를 넣는다. 선택자가 한 칸이면 통째로, 여러 칸(한 글자씩)이면 글자마다 나눠 넣는다. 넣은 칸 수."""
    boxes = page.locator(selector)
    boxes.first.wait_for(state="visible", timeout=timeout_ms)
    count = boxes.count()
    if count <= 1:
        boxes.first.fill(code, timeout=timeout_ms)
        return 1
    for index, digit in enumerate(code[:count]):
        boxes.nth(index).fill(digit, timeout=timeout_ms)
    return min(count, len(code))


def _is_condition_met(page, until_url: str | None, until_text: str | None) -> bool:
    try:
        if until_url and until_url not in page.url:
            return False
        if until_text and not page.get_by_text(until_text).first.is_visible():
            return False
    except Exception:
        return False
    return True


def _wait_for_condition(page, args) -> bool:
    """완료 조건(URL 일부·보이는 문구)을 --handoff-seconds 동안 기다린다. 조건이 없으면 True."""
    if not (args.until_url or args.until_text):
        return True
    deadline = time.time() + min(max(args.handoff_seconds, 0), MAXIMUM_HANDOFF_SECONDS)
    while True:
        if _is_condition_met(page, args.until_url, args.until_text):
            return True
        if time.time() >= deadline:
            return False
        # time.sleep 이면 Playwright 가 이벤트를 못 받아 page.url 이 옛 값에 멈춘다 (실측)
        page.wait_for_timeout(CONDITION_POLL_SECONDS * 1000)


def _fill_credentials(page, args, timeout_ms: int, filled: list[str], secret_values: list[str]) -> dict | None:
    """아이디·비밀번호·일회용 코드를 넣고 제출한다 > 실패 결과.

    넣은 칸 이름·가릴 값은 받은 목록에 바로 쌓는다 — 넣다가 예외가 나도 호출부가 그 값을 가린다.
    """
    cred: dict = {}
    if args.login_cred:
        cred, err = load_cred(args.login_cred)
        if err:
            return err
    if args.user_selector:
        field = _pick_identifier_field(cred, args.user_field)
        value = cred.get(field) if field else None
        if value in (None, ""):
            return {
                "ok": False, "code": "cred_field_missing",
                "error": f"'{args.login_cred}' has no value to use as the user id (fields tried: {IDENTIFIER_FIELD_CANDIDATES})",
                "next": "web login ... --user-field <field name>  # see the fields with cred list"}
        secret_values.append(str(value))
        page.locator(args.user_selector).first.fill(str(value), timeout=timeout_ms)
        filled.append(f"user:{field}")
    if args.password_selector:
        value = cred.get(args.password_field)
        if value in (None, ""):
            return {
                "ok": False, "code": "cred_field_missing",
                "error": f"'{args.login_cred}' has no '{args.password_field}' value",
                "next": "web login ... --password-field <field name>"}
        secret_values.append(str(value))
        page.locator(args.password_selector).first.fill(str(value), timeout=timeout_ms)
        filled.append(f"password:{args.password_field}")
    if args.otp_env:
        code = os.environ.get(args.otp_env, "").strip()
        if not code or not args.otp_selector:
            return {
                "ok": False, "code": "otp_missing",
                "error": "A one-time code needs both --otp-env <env var> and --otp-selector",
                "next": f'{args.otp_env or "CODE"}="123456" launch_cli.py web login --otp-env ... --otp-selector ...'}
        secret_values.append(code)
        boxes = _fill_otp(page, args.otp_selector, code, timeout_ms)
        filled.append(f"otp:{boxes} boxes")
    if args.submit_selector:
        page.locator(args.submit_selector).first.click(timeout=timeout_ms)
        filled.append("submit")
    return None


def _handoff_payload(page, args, state: dict, filled: list[str]) -> dict:
    """조건이 안 맞음 > 사용자에게 넘긴다. 다시 부를 명령(--resume)을 그대로 준다."""
    url, title = read_url_title(page, timeout=2)
    is_headed = bool(state.get("headed"))
    condition = " ".join(f"--{flag} '{value}'" for flag, value in
                         (("until-url", args.until_url), ("until-text", args.until_text)) if value)
    return {"ok": False, "code": "needs_user", "action": "login", "url": url, "title": title, "filled": filled,
            "summary": "Handing the remaining login steps to the user (completion condition not met yet)",
            "needs_user": {"kind": "user_action", "is_headed": is_headed,
                           "message": "The user must finish the remaining steps in the browser (two-factor auth, device approval, etc.)"},
            "hint": (None if is_headed else
                     "The browser is headless — for the user to act, run web close, then reopen with web open --headed"),
            "ask_user": "Please finish the remaining login steps in the browser (verification code, device approval) and tell me when done",
            "next": f"web login --resume {condition} --handoff-seconds 120  # continue after the user is done"}


def execute(page, args, state: dict) -> dict:
    timeout_ms = args.timeout * 1000
    if not args.resume and not (args.user_selector or args.password_selector or args.otp_env):
        return {"ok": False, "code": "missing_argument",
                "error": "One of --user-selector, --password-selector or --otp-env is required (use --resume to resume)",
                "next": "web find  # find the input refs/selectors first"}
    if (args.user_selector or args.password_selector) and not args.login_cred:
        return {"ok": False, "code": "missing_argument", "error": "--cred is required",
                "next": "cred list  # see saved credentials and their use_when"}
    filled: list[str] = []
    secret_values: list[str] = []
    try:
        if not args.resume:
            failure = _fill_credentials(page, args, timeout_ms, filled, secret_values)
            if failure:
                return failure
        if not _wait_for_condition(page, args):
            # 사용자 인계에도 중간 화면 정책을 싣는다 (#905)
            return with_login_policy(_handoff_payload(page, args, state, filled), args.login_cred)
    except Exception as e:
        return {"ok": False, "code": "web_action_failed", "action": "login", "filled": filled,
                "error": _mask(str(e), secret_values)[:400],
                "next": "web find  # check the input selectors are right"}
    url, title = read_url_title(page)
    result = {"action": "login", "url": url, "title": title, "filled": filled, "resumed": bool(args.resume),
              "summary": "Login steps done" + (" (condition confirmed)" if (args.until_url or args.until_text) else ""),
              "next": "web text  # read the screen after login"}
    # 로그인 결과에 중간 화면 정책을 싣는다 (#905)
    return with_login_policy(result, args.login_cred)


def configure(p) -> None:
    # dest 를 따로 둔다 — web 디스패처가 args.cred 를 보면 password 필드를 미리 꺼내려 한다
    p.add_argument("--cred", dest="login_cred", metavar="NAME", default=None, help="Saved credential name (cred list). Values never appear in output")
    p.add_argument("--user-selector", dest="user_selector", default=None, help="Selector of the user id input")
    p.add_argument("--user-field", dest="user_field", default=None,
                   help=f"Field to enter as the user id (default: the first present of {'·'.join(IDENTIFIER_FIELD_CANDIDATES)})")
    p.add_argument("--password-selector", dest="password_selector", default=None, help="Selector of the password input")
    p.add_argument("--password-field", dest="password_field", default="password", help="Field to enter as the password")
    p.add_argument("--submit-selector", dest="submit_selector", default=None, help="Selector of the button to press after filling")
    p.add_argument("--otp-env", dest="otp_env", default=None, help="Name of the env var holding the one-time code")
    p.add_argument("--otp-selector", dest="otp_selector", default=None,
                   help="Selector of the code input. For one-box-per-digit inputs, a selector matching all the boxes")
    p.add_argument("--until-url", dest="until_url", default=None, help="Completion condition: the URL contains this string")
    p.add_argument("--until-text", dest="until_text", default=None, help="Completion condition: this text is visible on screen")
    p.add_argument("--handoff-seconds", dest="handoff_seconds", type=int, default=0,
                   help=f"Seconds to wait for the completion condition (max {MAXIMUM_HANDOFF_SECONDS}). Past that, hands off as needs_user")
    p.add_argument("--resume", action="store_true", help="Skip input and only wait for the completion condition again (after a user handoff)")


ACTION = Action(name="login", run=execute, configure=configure, options=("timeout",),
                help="Fill saved credentials into the given inputs, hand two-factor auth to the user, and continue once the condition (URL/text) holds",
                example="web login --cred staging-admin --user-selector '#email' --password-selector '#pw' "
                        "--submit-selector 'button[type=submit]' --until-url /dashboard --handoff-seconds 120")
