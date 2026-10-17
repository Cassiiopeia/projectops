"""저장된 자격증명을 명령에서 꺼내 쓰는 얇은 층. 저장·마스킹 자체는 credentials.py."""
from __future__ import annotations


import credentials


#
# pro-ssh · pro-github 가 config.json 에 서버·PAT 를 두고 쓰는 것과 같은 방식이다.
# 비밀은 사용자 홈의 config.json(launch.credentials) 한 곳에만 두고, access.json 에는 이름만 적는다.
def load_cred(name: str | None):
    """(자격증명, None) 또는 (None, 오류 JSON 을 낼 payload)."""
    if not name:
        return None, None
    try:
        return credentials.resolve(name), None
    except credentials.CredError as e:
        return None, {"ok": False, "code": e.code, "error": e.message,
                      "next": "cred list  # 저장된 자격증명과 use_when 을 본다"}


def cred_name_for(args, saved) -> str | None:
    """--cred 가 없으면 access 기록에 적힌 cred 이름을 쓴다."""
    if getattr(args, "cred", None):
        return args.cred
    return saved.get("cred") if isinstance(saved, dict) else None


def cred_field(name: str, field: str | None) -> tuple[str | None, dict | None]:
    """저장된 자격증명에서 입력할 값 하나를 꺼낸다 (기본 password). (값, None) 또는 (None, 오류)."""
    cred, err = load_cred(name)
    if err:
        return None, err
    f = field or "password"
    v = cred.get(f)
    if v in (None, ""):
        keys = sorted(k for k, x in cred.items() if x not in (None, "") and k not in ("name", "kind"))
        return None, {"ok": False, "code": "cred_field_missing",
                      "error": f"'{name}' 에 '{f}' 값이 없습니다", "fields": keys,
                      "next": f"cred set --name {name} --json '{{\"{f}\": \"...\"}}'  # 또는 --cred-field 로 다른 필드를 고른다"}
    return str(v), None


def with_login_policy(payload: dict, cred_name: str | None) -> dict:
    """로그인 입력 결과에 최종 정책을 싣는다 (#905). 성공·사용자 인계(needs_user)에만, 그 외 실패는 그대로

    agent 는 이 값을 보고 로그인 중간 화면(기기 신뢰·로그인 유지·권유)을 묻지 않고 처리할지 정한다.
    """
    if payload.get("ok") is False and payload.get("code") != "needs_user":
        return payload
    try:
        payload["login_policy"] = credentials.resolve_login_policy(cred_name)
    except Exception:
        pass                                        # 정책을 못 읽어도 입력 결과는 그대로 내보낸다
    return payload
