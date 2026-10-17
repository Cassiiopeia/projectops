"""이름 붙은 자격증명 저장소 (pro-launch).

pro-ssh · pro-github 가 `~/.projectops/config/config.json` 에 서버·PAT 를 두고 잘 쓰는 것과
같은 방식이다. pro-launch 도 **다음 실행에서 다시 묻지 않도록** 같은 파일의 `launch` 섹션에 둔다.

    config["launch"]["credentials"][이름] = {
        "kind": "ssh | dockerhub | db | http | github-org | other",
        "use_when": "agent 가 이 자격증명을 써도 되는지 판단하는 근거",
        "scope": "test-only | readonly | ...   (무엇까지 허용되는지)",
        "notes": "알아둘 것(포트 범위, 지켜야 할 이름 규칙, 서버에 있는 운영 서비스 등)",
        "ssh_server": "pro-ssh 에 등록된 서버 이름 — 있으면 host·port·user·password 를 거기서 가져온다",
        ... 값(password · token · username · host ...)
    }

**왜 access.json 이 아니라 config.json 인가**: access.json 은 프로젝트별 "붙는 법" 기록이라
비밀이 없어야 한다(find_secrets 가 막는다). 비밀은 사용자 홈의 이 파일 한 곳에만 둔다.
access.json 에는 `{"cred": "이름"}` 처럼 이름만 적는다.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from common import config as cfg

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

# 출력에 드러내지 않는 키. 이름이 이것을 포함하면 값을 가린다.
SECRET_KEYS = ("password", "passwd", "token", "secret", "passphrase", "api_key", "apikey", "private_key")


class CredError(Exception):
    """저장·조회 실패. code 는 JSON 응답의 code 로 쓴다."""

    def __init__(self, code: str, message: str, next_hint: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.next_hint = next_hint                  # JSON 응답의 next (있을 때만)


def _is_secret_key(key: str) -> bool:
    k = key.lower()
    return any(s in k for s in SECRET_KEYS)


def _section(data: dict | None, create: bool = False) -> dict:
    data = data if isinstance(data, dict) else {}
    launch = data.get("launch")
    if not isinstance(launch, dict):
        if not create:
            return {}
        launch = data["launch"] = {}
    creds = launch.get("credentials")
    if not isinstance(creds, dict):
        if not create:
            return {}
        creds = launch["credentials"] = {}
    return creds


def load_all() -> dict:
    return _section(cfg.load())


def ssh_servers() -> list[dict]:
    """config.json 의 옛 pro-ssh `ssh` 섹션 서버 목록 (읽기 전용)."""
    data = cfg.load() or {}
    servers = data.get("ssh")
    if isinstance(servers, dict):                 # 구버전 형태 {"instances": [...]}
        servers = servers.get("instances")
    return [s for s in servers or [] if isinstance(s, dict)]


def _ssh_server(name: str) -> dict | None:
    for s in ssh_servers():
        if s.get("name") == name:
            return s
    return None


def resolve(name: str) -> dict:
    """이름으로 자격증명을 꺼낸다. `ssh_server` 참조가 있으면 pro-ssh 서버 값을 바탕으로 합친다."""
    entry = load_all().get(name)
    if not isinstance(entry, dict):
        known = ", ".join(sorted(load_all())) or "(없음)"
        raise CredError("cred_not_found", f"'{name}' 자격증명이 없습니다. 있는 것: {known}")
    merged: dict = {}
    ref = entry.get("ssh_server")
    if ref:
        srv = _ssh_server(ref)
        if not srv:
            raise CredError("ssh_server_not_found", f"pro-ssh 에 '{ref}' 서버가 없습니다")
        for k in ("host", "port", "user", "password", "key_path", "auth"):
            if srv.get(k) not in (None, ""):
                merged[k] = srv[k]
    merged.update({k: v for k, v in entry.items() if v not in (None, "")})
    merged["name"] = name
    return merged


def public_view(entry: dict, reveal: bool = False) -> dict:
    """사람·agent 에게 보여 줄 모양. 비밀 값은 `<저장됨>` 으로 가린다."""
    if reveal:
        return dict(entry)
    return {k: ("<저장됨>" if (_is_secret_key(k) and v) else v) for k, v in entry.items()}


def secret_values(entry: dict) -> list[str]:
    return [str(v) for k, v in entry.items() if _is_secret_key(k) and isinstance(v, (str, int)) and str(v)]


def mask(text: str | None, entry: dict) -> str:
    """출력에 비밀 값이 섞였으면 가린다 (서버가 환경변수를 되풀이해 찍는 경우 등)."""
    if not text:
        return text or ""
    for v in sorted(secret_values(entry), key=len, reverse=True):
        if len(v) >= 4:
            text = text.replace(v, "***")
    return text


def env_for(entry: dict) -> dict:
    """저장된 값을 명령이 환경변수로 읽게 한다. 명령 문자열에 비밀을 적지 않아도 된다."""
    env = {"CRED_NAME": entry.get("name", ""), "CRED_KIND": str(entry.get("kind", ""))}
    mapping = {"host": "CRED_HOST", "port": "CRED_PORT", "user": "CRED_USER", "username": "CRED_USERNAME",
               "password": "CRED_PASSWORD", "token": "CRED_TOKEN", "db": "CRED_DB"}
    for k, var in mapping.items():
        if entry.get(k) not in (None, ""):
            env[var] = str(entry[k])
    if entry.get("password"):
        env["SSHPASS"] = str(entry["password"])      # sshpass -e 가 읽는다
    return env


def validate_name(name: str | None) -> str:
    if not name or not NAME_RE.match(name):
        raise CredError("bad_name", "--name 은 영문·숫자로 시작하고 영문·숫자·._- 만 쓸 수 있습니다 (64자 이하)")
    return name


def _write_config(data: dict) -> Path:
    """config.json 을 쓴다. 새로 쓸 때는 소유자만 읽게 한다(600) — 비밀이 들어 있는 파일이다."""
    path = cfg.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".config.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2))
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)                  # 쓰다 끊겨도 기존 파일이 깨지지 않는다
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def save_credential(name: str, fields: dict, replace: bool = False) -> Path:
    """다른 섹션(github · ssh ...)을 건드리지 않고 launch.credentials[name] 만 갱신한다."""
    validate_name(name)
    if not isinstance(fields, dict) or not fields:
        raise CredError("value_required", "--json 은 비어 있지 않은 객체(JSON)여야 합니다")
    data = cfg.load()
    if data is None and cfg.config_path().exists():
        # 파일은 있는데 읽지 못했다 = 깨졌다. 덮어쓰면 PAT·서버 정보가 전부 사라진다.
        raise CredError("config_unreadable", "config.json 을 읽지 못했습니다 (깨졌을 수 있습니다). 덮어쓰지 않았습니다")
    if "login_policy" in fields:
        # 정책은 키·값 검증과 키 단위 병합이 필요하다 > 전용 경로로만 (#905)
        raise CredError("use_cred_policy", "login_policy 는 cred set 으로 바꾸지 않습니다",
                        next_hint=f"cred policy set --name {name} --key <키> --value <ask|always|never>")
    data = data or {}
    creds = _section(data, create=True)
    existing = dict(creds.get(name) or {})
    base = {} if replace else existing
    base.update(fields)
    if replace and isinstance(existing.get("login_policy"), dict):
        base["login_policy"] = existing["login_policy"]   # --replace 는 값만 바꾼다. 정책은 cred policy unset 으로
    creds[name] = base
    return _write_config(data)


def delete_credential(name: str) -> bool:
    data = cfg.load()
    creds = _section(data)
    if name not in creds:
        return False
    del creds[name]
    _write_config(data)
    return True


# ── 로그인 중간 화면 정책 (#905) ─────────────────────────────────────────
# 판정: 계정 launch.credentials.<이름>.login_policy > 전체 launch.login_policy > ask
# 화면 3종: 기기 신뢰(다시 묻지 않기) · 로그인 상태 유지 · 패스키·연락처 추가 같은 권유
LOGIN_POLICY_KEYS = ("trust_device", "keep_signed_in", "skip_nags")
# ask: 사용자에게 묻는다 · always: 묻지 않고 받아들인다(권유는 건너뛴다) · never: 묻지 않고 거절한다
LOGIN_POLICY_VALUES = ("ask", "always", "never")
LOGIN_POLICY_DEFAULT_VALUE = "ask"


def _validate_login_policy(key: str, value: str | None = None) -> None:
    if key not in LOGIN_POLICY_KEYS:
        raise CredError("invalid_policy_key", f"'{key}' 는 정책 키가 아닙니다. 쓸 수 있는 것: {', '.join(LOGIN_POLICY_KEYS)}")
    if value is not None and value not in LOGIN_POLICY_VALUES:
        raise CredError("invalid_policy_value", f"'{value}' 는 정책 값이 아닙니다. 쓸 수 있는 것: {', '.join(LOGIN_POLICY_VALUES)}")


def _policy_of(holder) -> dict:
    """login_policy 객체에서 올바른 키·값만 남긴다 (손으로 잘못 고친 값은 없는 것으로 본다)"""
    policy = holder.get("login_policy") if isinstance(holder, dict) else None
    if not isinstance(policy, dict):
        return {}
    return {key: value for key, value in policy.items() if key in LOGIN_POLICY_KEYS and value in LOGIN_POLICY_VALUES}


def resolve_login_policy(name: str | None) -> dict:
    """최종 정책: 키마다 {"value", "source": credential | global | default}"""
    data = cfg.load()
    data = data if isinstance(data, dict) else {}       # 읽지 못했거나 객체가 아니면 저장된 선택 없음
    launch = data.get("launch") if isinstance(data.get("launch"), dict) else {}
    global_policy = _policy_of(launch)
    credential_policy = _policy_of(_section(data).get(name)) if name else {}
    resolved = {}
    for key in LOGIN_POLICY_KEYS:
        if key in credential_policy:
            resolved[key] = {"value": credential_policy[key], "source": "credential"}
        elif key in global_policy:
            resolved[key] = {"value": global_policy[key], "source": "global"}
        else:
            resolved[key] = {"value": LOGIN_POLICY_DEFAULT_VALUE, "source": "default"}
    return resolved


def _load_for_policy_write() -> dict:
    """정책을 쓸 config 를 읽는다. 깨진 파일은 덮어쓰지 않는다 (PAT·서버 정보 보호)"""
    data = cfg.load()
    if (data is None and cfg.config_path().exists()) or (data is not None and not isinstance(data, dict)):
        raise CredError("config_unreadable", "config.json 을 읽지 못했습니다 (깨졌을 수 있습니다). 덮어쓰지 않았습니다")
    return data or {}


def _policy_holder(data: dict, name: str | None, create: bool) -> dict | None:
    """정책을 담을 객체: 이름이 있으면 그 계정, 없으면 launch 섹션. 계정이 없으면 cred_not_found"""
    if name:
        entry = _section(data).get(name)
        if not isinstance(entry, dict):
            known = ", ".join(sorted(_section(data))) or "(없음)"
            raise CredError("cred_not_found", f"'{name}' 자격증명이 없습니다. 있는 것: {known}")
        return entry
    launch = data.get("launch")
    if not isinstance(launch, dict):
        if not create:
            return None
        launch = data["launch"] = {}
    return launch


def has_credential(name: str) -> bool:
    """이름 붙은 항목이 있는지만 본다 (ssh_server 참조는 풀지 않는다)"""
    return isinstance(load_all().get(name), dict)


def set_login_policy(name: str | None, key: str, value: str) -> Path:
    """정책 한 키 저장 — 이름이 있으면 그 계정에, 없으면 전체 기본값에"""
    _validate_login_policy(key, value)
    data = _load_for_policy_write()
    holder = _policy_holder(data, name, create=True)
    policy = holder.get("login_policy") if isinstance(holder.get("login_policy"), dict) else {}
    policy[key] = value
    holder["login_policy"] = policy
    return _write_config(data)


def unset_login_policy(name: str | None, key: str) -> bool:
    """정책 한 키 제거 (위 층으로 돌아간다). 마지막 키면 login_policy 객체도 지운다. 지웠으면 True"""
    _validate_login_policy(key)
    data = _load_for_policy_write()
    holder = _policy_holder(data, name, create=False)
    policy = holder.get("login_policy") if holder else None
    if not isinstance(policy, dict) or key not in policy:
        return False
    del policy[key]
    if not policy:
        del holder["login_policy"]
    _write_config(data)
    return True
