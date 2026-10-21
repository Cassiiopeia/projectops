"""Actions Secret: 목록, PyNaCl 암호화 후 생성·갱신."""

from __future__ import annotations

import base64
import subprocess
import sys
import urllib.parse

from common import gh_client as client
from common.github_rest.transport import _API_BASE, PyNaClMissingError


def list_secrets(owner: str, repo: str, pat: str) -> list[dict]:
    """Actions Secret 목록을 반환한다."""
    data = client._request("GET", f"{_API_BASE}/repos/{owner}/{repo}/actions/secrets?per_page=100", None, pat)
    return [
        {"name": item["name"], "updated_at": item.get("updated_at")}
        for item in data.get("secrets", [])
    ]


def _load_nacl_public():
    """PyNaCl을 로드한다. 없으면 한 번 설치를 시도한다."""
    try:
        from nacl import encoding, public
        return encoding, public
    except ImportError:
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "PyNaCl", "-q"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            from nacl import encoding, public
            return encoding, public
        except Exception as e:
            raise PyNaClMissingError("PyNaCl is not available. Install it manually: pip install PyNaCl") from e


def _encrypt_secret(public_key: str, value: str) -> str:
    encoding, public = client._load_nacl_public()
    public_key_obj = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key_obj)
    encrypted = sealed_box.encrypt(value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def set_secret(owner: str, repo: str, name: str, value: str, pat: str) -> dict:
    """Actions Secret을 암호화해 생성 또는 갱신한다."""
    key = client._request("GET", f"{_API_BASE}/repos/{owner}/{repo}/actions/secrets/public-key", None, pat)
    encrypted_value = client._encrypt_secret(key["key"], value)
    client._request(
        "PUT",
        f"{_API_BASE}/repos/{owner}/{repo}/actions/secrets/{urllib.parse.quote(name, safe='')}",
        {"encrypted_value": encrypted_value, "key_id": key["key_id"]},
        pat,
    )
    return {"name": name, "status": "updated"}
