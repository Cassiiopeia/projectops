"""`web login` — 저장된 자격증명을 지정한 입력칸에 넣고, 2단계 인증 등은 사용자에게 넘긴 뒤 조건이 맞으면 이어간다 (#881).

제공자별(Google·Apple …) 화면 자동화는 두지 않는다 — 화면이 제공자마다 달라 계속 깨진다.
틀만 일반적으로: 입력(선택자) > 제출 > 완료 조건(URL·문구) 대기 > 안 되면 사용자 인계(needs_user) > `--resume` 으로 재개.
값은 결과·오류·로그에 남기지 않는다 (명령줄에도 이름만 적는다).
"""
from __future__ import annotations

import os
import time

from pro_launch.commands.web.session import read_url_title
from pro_launch.registry import Action
from pro_launch.runtime.creds import load_cred, with_login_policy

# 아이디로 쓸 필드를 자동으로 고를 때 보는 순서
IDENTIFIER_FIELD_CANDIDATES = ("username", "account", "email", "user", "login", "id")
# 사용자 인계 대기 상한 (초) — CLI 한 번이 무한히 붙잡지 않게
MAXIMUM_HANDOFF_SECONDS = 600
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
                "error": f"'{args.login_cred}' 에 아이디로 쓸 값이 없습니다 (찾은 필드: {IDENTIFIER_FIELD_CANDIDATES})",
                "next": "web login ... --user-field <필드 이름>  # cred list 로 필드를 본다"}
        secret_values.append(str(value))
        page.locator(args.user_selector).first.fill(str(value), timeout=timeout_ms)
        filled.append(f"user:{field}")
    if args.password_selector:
        value = cred.get(args.password_field)
        if value in (None, ""):
            return {
                "ok": False, "code": "cred_field_missing",
                "error": f"'{args.login_cred}' 에 '{args.password_field}' 값이 없습니다",
                "next": "web login ... --password-field <필드 이름>"}
        secret_values.append(str(value))
        page.locator(args.password_selector).first.fill(str(value), timeout=timeout_ms)
        filled.append(f"password:{args.password_field}")
    if args.otp_env:
        code = os.environ.get(args.otp_env, "").strip()
        if not code or not args.otp_selector:
            return {
                "ok": False, "code": "otp_missing",
                "error": "일회용 코드는 --otp-env <환경변수> 와 --otp-selector 가 둘 다 필요합니다",
                "next": f'{args.otp_env or "CODE"}="123456" launch_cli.py web login --otp-env ... --otp-selector ...'}
        secret_values.append(code)
        boxes = _fill_otp(page, args.otp_selector, code, timeout_ms)
        filled.append(f"otp:{boxes}칸")
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
            "summary": "남은 로그인 단계를 사용자에게 넘깁니다 (완료 조건 아직 안 맞음)",
            "needs_user": {"kind": "user_action", "is_headed": is_headed,
                           "message": "브라우저에서 2단계 인증·기기 승인 등 남은 단계를 사용자가 마쳐야 한다"},
            "hint": (None if is_headed else
                     "보이지 않는 브라우저다 — 사용자가 조작하려면 web close 후 web open --headed 로 다시 연다"),
            "ask_user": "브라우저에서 남은 로그인 단계(인증 코드·기기 승인)를 마친 뒤 알려 주세요",
            "next": f"web login --resume {condition} --handoff-seconds 120  # 사용자가 마친 뒤 이어간다"}


def execute(page, args, state: dict) -> dict:
    timeout_ms = args.timeout * 1000
    if not args.resume and not (args.user_selector or args.password_selector or args.otp_env):
        return {"ok": False, "code": "missing_argument",
                "error": "--user-selector · --password-selector · --otp-env 중 하나는 필요합니다 (재개는 --resume)",
                "next": "web find  # 입력칸 ref·선택자를 먼저 찾는다"}
    if (args.user_selector or args.password_selector) and not args.login_cred:
        return {"ok": False, "code": "missing_argument", "error": "--cred 가 필요합니다",
                "next": "cred list  # 저장된 자격증명과 use_when 을 본다"}
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
                "next": "web find  # 입력칸 선택자가 맞는지 본다"}
    url, title = read_url_title(page)
    result = {"action": "login", "url": url, "title": title, "filled": filled, "resumed": bool(args.resume),
              "summary": "로그인 단계를 마쳤습니다" + (" (조건 확인됨)" if (args.until_url or args.until_text) else ""),
              "next": "web text  # 로그인 뒤 화면을 읽는다"}
    # 로그인 결과에 중간 화면 정책을 싣는다 (#905)
    return with_login_policy(result, args.login_cred)


def configure(p) -> None:
    # dest 를 따로 둔다 — web 디스패처가 args.cred 를 보면 password 필드를 미리 꺼내려 한다
    p.add_argument("--cred", dest="login_cred", metavar="NAME", default=None, help="저장된 자격증명 이름 (cred list). 값은 출력에 남지 않는다")
    p.add_argument("--user-selector", dest="user_selector", default=None, help="아이디 입력칸 선택자")
    p.add_argument("--user-field", dest="user_field", default=None,
                   help=f"아이디로 넣을 필드 (기본: {'·'.join(IDENTIFIER_FIELD_CANDIDATES)} 중 처음 있는 것)")
    p.add_argument("--password-selector", dest="password_selector", default=None, help="비밀번호 입력칸 선택자")
    p.add_argument("--password-field", dest="password_field", default="password", help="비밀번호로 넣을 필드")
    p.add_argument("--submit-selector", dest="submit_selector", default=None, help="넣은 뒤 누를 버튼 선택자")
    p.add_argument("--otp-env", dest="otp_env", default=None, help="일회용 코드를 담은 환경변수 이름")
    p.add_argument("--otp-selector", dest="otp_selector", default=None,
                   help="코드 입력칸 선택자. 한 글자씩 나뉜 칸이면 그 칸들 모두를 가리키는 선택자")
    p.add_argument("--until-url", dest="until_url", default=None, help="완료 조건: 주소에 이 문자열이 들어 있다")
    p.add_argument("--until-text", dest="until_text", default=None, help="완료 조건: 이 문구가 화면에 보인다")
    p.add_argument("--handoff-seconds", dest="handoff_seconds", type=int, default=0,
                   help=f"완료 조건을 기다릴 시간(초, 최대 {MAXIMUM_HANDOFF_SECONDS}). 넘으면 needs_user 로 넘긴다")
    p.add_argument("--resume", action="store_true", help="입력은 건너뛰고 완료 조건만 다시 기다린다 (사용자 인계 뒤)")


ACTION = Action(name="login", run=execute, configure=configure, options=("timeout",),
                help="자격증명을 지정한 칸에 넣고, 2단계 인증은 사용자에게 넘긴 뒤 조건(URL·문구)이 맞으면 이어간다",
                example="web login --cred staging-admin --user-selector '#email' --password-selector '#pw' "
                        "--submit-selector 'button[type=submit]' --until-url /dashboard --handoff-seconds 120")
