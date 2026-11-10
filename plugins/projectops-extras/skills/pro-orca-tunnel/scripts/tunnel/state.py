"""상태 폴더 ~/.projectops/tunnel: 포트별 터널 기록, 로그, Orca 짝 맞추기 원본 (계정·세션 공통)"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

# 계정·세션이 달라도 같은 기록을 보도록 사용자 홈 한 곳에 둠
STATE_DIR = Path(os.environ.get("PROJECTOPS_TUNNEL_DIR") or Path.home() / ".projectops" / "tunnel")
STATE_FILE = STATE_DIR / "state.json"
PAIRING_FILE = STATE_DIR / "orca-pairing.json"


def ensure_dir() -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR


def load() -> dict:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"tunnels": {}}
    if not isinstance(data, dict) or not isinstance(data.get("tunnels"), dict):
        return {"tunnels": {}}
    return data


def save(data: dict) -> None:
    ensure_dir()
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, STATE_FILE)


def remember_tunnel(port: int, pid: int, url: str | None, log_path: Path) -> None:
    data = load()
    data["tunnels"][str(port)] = {"pid": pid, "url": url, "log": str(log_path), "started": int(time.time())}
    save(data)


def forget_tunnel(port: int) -> None:
    data = load()
    if data["tunnels"].pop(str(port), None) is not None:
        save(data)


def log_path_for(port: int) -> Path:
    return ensure_dir() / f"cloudflared-{port}.log"


def remember_value(key: str, value) -> None:
    data = load()
    data[key] = value
    save(data)


def write_private(path: Path, text: str) -> None:
    """본인만 읽는 파일로 저장 (짝 맞추기 코드는 접속 열쇠)"""
    ensure_dir()
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(temporary, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
