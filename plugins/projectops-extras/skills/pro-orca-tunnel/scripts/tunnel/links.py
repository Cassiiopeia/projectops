"""앱 접속 링크 보관과 터널 주소 바꾸기: 앱 형식을 모르고도 링크 안의 옛 터널 주소를 새 주소로 바꿈
평문 주소와 base64(JSON) 로 감싼 값 안의 주소를 함께 바꿈. 형식이 바뀌어 못 찾으면 host_not_found (하네스로 대응)
"""
from __future__ import annotations

import base64
import json
import re
import urllib.parse

from . import state

# 빠른 터널 이름 (옛 주소 찾기)
TUNNEL_HOST_PATTERN = re.compile(r"[a-z0-9-]+\.trycloudflare\.com")
# base64 로 보이는 덩어리 (길이 40 이상)
ENCODED_CHUNK_PATTERN = re.compile(r"[A-Za-z0-9+/_-]{40,}={0,2}")


def link_path(app: str):
    safe_name = re.sub(r"[^a-z0-9-]", "-", app.lower())
    return state.STATE_DIR / f"link-{safe_name}.txt"


def save(app: str, link: str) -> None:
    """본인만 읽는 파일로 저장 (링크에 기기 인증 값이 들 수 있음)"""
    state.write_private(link_path(app), link.strip())


def load(app: str) -> str | None:
    try:
        text = link_path(app).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def _decode_chunk(chunk: str) -> tuple[str, bool, bool] | None:
    """(풀린 글, url-safe 였나, 패딩 있었나). JSON 이 아니면 None"""
    padded = chunk + "=" * (-len(chunk) % 4)
    is_url_safe = "-" in chunk or "_" in chunk
    decoder = base64.urlsafe_b64decode if is_url_safe else base64.b64decode
    try:
        text = decoder(padded).decode("utf-8")
        json.loads(text)
    except (ValueError, UnicodeDecodeError):
        return None
    return text, is_url_safe, chunk.endswith("=")


def _encode_chunk(text: str, is_url_safe: bool, is_padded: bool) -> str:
    raw = text.encode("utf-8")
    encoded = (base64.urlsafe_b64encode(raw) if is_url_safe else base64.b64encode(raw)).decode("ascii")
    return encoded if is_padded else encoded.rstrip("=")


def retarget(link: str, new_host: str) -> tuple[str, int]:
    """링크 안의 모든 trycloudflare 주소 > new_host. (새 링크, 바꾼 개수)"""
    replaced = 0

    def replace_hosts(text: str) -> str:
        nonlocal replaced
        updated, count = TUNNEL_HOST_PATTERN.subn(new_host, text)
        replaced += count
        return updated

    # 퍼센트 인코딩을 한 겹 풀어 안쪽까지 봄 (#pairing=orca%3A%2F%2F...)
    is_quoted = "%3A" in link or "%3D" in link
    working = urllib.parse.unquote(link) if is_quoted else link

    def replace_encoded(match: re.Match) -> str:
        decoded = _decode_chunk(match.group(0))
        if decoded is None:
            return match.group(0)
        text, is_url_safe, is_padded = decoded
        updated = replace_hosts(text)
        return _encode_chunk(updated, is_url_safe, is_padded) if updated != text else match.group(0)

    working = ENCODED_CHUNK_PATTERN.sub(replace_encoded, working)
    working = replace_hosts(working)
    if not is_quoted:
        return working, replaced
    # 다시 감쌈: 첫 # 뒤 값만 원래처럼 인코딩
    if "#" in working:
        head, fragment = working.split("#", 1)
        if "=" in fragment:
            key, value = fragment.split("=", 1)
            return f"{head}#{key}={urllib.parse.quote(value, safe='')}", replaced
    return urllib.parse.quote(working, safe=":/?#&="), replaced
