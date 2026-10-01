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

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


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


def _ssh_server(name: str) -> dict | None:
    data = cfg.load() or {}
    servers = data.get("ssh")
    if isinstance(servers, dict):                 # 구버전 형태 {"instances": [...]}
        servers = servers.get("instances")
    for s in servers or []:
        if isinstance(s, dict) and s.get("name") == name:
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
    data = data or {}
    creds = _section(data, create=True)
    base = {} if replace else dict(creds.get(name) or {})
    base.update(fields)
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
