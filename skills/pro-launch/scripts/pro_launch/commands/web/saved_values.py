"""화면에서 읽은 값을 출력하지 않고 저장 — `web value --save-env` · `web clipboard --save-env` (#930).

입력칸 안 · 복사 버튼으로만 나오는 비밀값(Client Secret · 키 해시)을 OCR · pbpaste 로 읽어 대화 기록에 남겼다.
값은 상태 폴더의 0600 파일(`export 이름='값'`)에만 쓰고, 결과에는 길이와 sha256 앞 12자만 싣는다.
`web type --text-env 이름` 은 환경변수에 없으면 이 파일에서 읽는다 — source 없이 바로 쓴다.
"""
from __future__ import annotations

import hashlib
import os
import re
import shlex
from pathlib import Path

from pro_launch.runtime.context import state_home

# 상태 폴더 안의 저장 파일 이름 (사용자만 읽기 · 쓰기)
SAVED_VALUES_FILE = "saved-values.env"
FILE_MODE = 0o600
# 셸 변수 이름 규칙
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
HASH_PREFIX_CHARS = 12


def saved_values_path(root: Path) -> Path:
    return state_home(root) / SAVED_VALUES_FILE


def _sh_quote(value: str) -> str:
    """작은따옴표로 감싼다 — 큰따옴표면 $ 가 전개되어 다른 값이 된다"""
    return "'" + value.replace("'", "'\\''") + "'"


def read_saved_values(root: Path) -> dict[str, str]:
    """저장 파일 > {이름: 값}. 없거나 못 읽으면 빈 dict"""
    try:
        lines = saved_values_path(root).read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    values = {}
    for line in lines:
        try:
            words = shlex.split(line)
        except ValueError:
            continue
        if len(words) == 2 and words[0] == "export" and "=" in words[1]:
            name, value = words[1].split("=", 1)
            values[name] = value
    return values


def is_valid_env_name(name: str) -> bool:
    return bool(_ENV_NAME.fullmatch(name or ""))


def save_value(root: Path, name: str, value: str) -> dict:
    """값을 저장하고 > 결과에 실을 요약(이름 · 파일 · 길이 · 해시 앞자리). 값 자체는 돌려주지 않는다"""
    values = read_saved_values(root)
    values[name] = value
    path = saved_values_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"export {key}={_sh_quote(saved)}\n" for key, saved in values.items())
    # 만들 때부터 0600 — 쓰고 나서 권한을 바꾸면 그 사이에 읽힐 수 있다
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
    with os.fdopen(descriptor, "w", encoding="utf-8") as saved_file:
        saved_file.write(body)
    os.chmod(path, FILE_MODE)
    return {"saved_env": name, "env_file": str(path), "length": len(value),
            "sha256_prefix": hashlib.sha256(value.encode("utf-8")).hexdigest()[:HASH_PREFIX_CHARS]}


def invalid_name_failure(action: str, name: str) -> dict:
    return {"ok": False, "code": "bad_env_name", "action": action, "name": name,
            "error": f"'{name}' cannot be an environment variable name (letters, digits and _ only, not starting with a digit)",
            "next": f"web {action} --save-env CLIENT_SECRET"}


def saved_next(name: str) -> str:
    return f"web type --ref <number> --text-env {name}  # the value never appears on the command line or in output"
