"""Figma 토큰 찾기·저장·REST 조회: FIGMA_TOKEN > config launch.credentials 의 provider figma 항목

새 저장소를 만들지 않는다 — 토큰 원본은 pro-launch cred 가 쓰는 config.json 한 곳이다.
토큰 값은 반환·출력 어디에도 싣지 않는다 (출처 이름만 알린다).
"""
from __future__ import annotations

import os

from common import config
from common.http import request

TOKEN_ENV_NAME = "FIGMA_TOKEN"
DEFAULT_CRED_NAME = "projectops-pro-figma"
FIGMA_API = "https://api.figma.com/v1"
FIGMA_PROVIDER = "figma"
# 토큰이 없을 때 에이전트가 사용자에게 보여 줄 선택지 (check-fresh 와 ingest 가 같이 쓴다)
TOKEN_MISSING_OPTIONS = [
    {"id": "register", "label": "Register a Figma token now (saved once, never asked again)",
     "command": "figma_cli.py token --prompt   # hidden input in your own terminal, or --from-env NAME"},
    {"id": "skip", "label": "Skip the change check this time (the result stays 'unknown')"},
    {"id": "user_confirmed", "label": "You confirm the design has not changed, and the work continues"},
]


def find_token() -> tuple[str | None, str | None]:
    """(토큰, 출처). 출처는 'env:FIGMA_TOKEN' 또는 'cred:<이름>' — 값은 밖으로 내지 않는다."""
    env_value = os.environ.get(TOKEN_ENV_NAME, "").strip()
    if env_value:
        return env_value, f"env:{TOKEN_ENV_NAME}"
    data = config.load() or {}
    credentials = (data.get("launch") or {}).get("credentials") or {}
    for name, entry in credentials.items():
        if isinstance(entry, dict) and entry.get("provider") == FIGMA_PROVIDER and entry.get("token"):
            return str(entry["token"]), f"cred:{name}"
    return None, None


def save_token(token: str, cred_name: str | None = None) -> tuple[str | None, dict | None]:
    """(저장한 항목 이름, None) 또는 (None, 오류 payload). 기존 figma 항목이 있으면 토큰만 바꾼다."""
    data, status = config.load_with_status()
    if status == "unreadable":
        # 깨진 config 를 덮어쓰면 다른 섹션이 날아간다
        return None, {"ok": False, "code": "config_unreadable",
                      "error": "config.json exists but cannot be read; not overwriting it",
                      "hint": "Fix or restore ~/.projectops/config/config.json first"}
    data = data or {}
    credentials = data.setdefault("launch", {}).setdefault("credentials", {})
    existing = next((n for n, e in credentials.items()
                     if isinstance(e, dict) and e.get("provider") == FIGMA_PROVIDER), None)
    name = cred_name or existing or DEFAULT_CRED_NAME
    entry = credentials.get(name) if isinstance(credentials.get(name), dict) else {}
    entry.update({"kind": "http", "provider": FIGMA_PROVIDER, "token": token})
    entry.setdefault("scope", "readonly")
    entry.setdefault("use_when", "pro-figma design lookup, asset download and change check")
    credentials[name] = entry
    config.save(data)
    return name, None


def fetch_json(path: str, token: str, timeout: int = 20) -> dict:
    """GET {FIGMA_API}{path}. request() 결과를 그대로 돌려준다 (4xx·5xx 도 결과다)."""
    return request("GET", f"{FIGMA_API}{path}", headers={"X-Figma-Token": token}, timeout=timeout)


def fetch_file_state(file_key: str, token: str) -> dict:
    """파일의 현재 lastModified · version. depth=1 이라 본문은 거의 안 받는다.

    반환: ok · lastModified · version · name  /  실패면 ok False + code (figma_token_rejected ·
    figma_file_not_found · request_failed)
    """
    r = fetch_json(f"/files/{file_key}?depth=1", token)
    if not r.get("ok"):
        return {"ok": False, "code": r.get("code", "request_failed"), "error": r.get("error", "")}
    status = r["status"]
    if status in (401, 403):
        return {"ok": False, "code": "figma_token_rejected", "status": status}
    if status == 404:
        return {"ok": False, "code": "figma_file_not_found", "status": status}
    body = r.get("json")
    if status != 200 or not isinstance(body, dict):
        return {"ok": False, "code": "request_failed", "status": status}
    return {"ok": True, "lastModified": body.get("lastModified"), "version": body.get("version"),
            "name": body.get("name")}
