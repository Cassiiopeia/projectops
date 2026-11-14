"""Store app access links and swap the tunnel host: replaces the old tunnel host inside a link without knowing the app's format
Replaces plain URLs and URLs inside base64(JSON) values. If a format change hides it, host_not_found (handled via the harness)
"""
from __future__ import annotations

import base64
import json
import re
import urllib.parse

from . import state

# Quick tunnel host name (to find the old address)
TUNNEL_HOST_PATTERN = re.compile(r"[a-z0-9-]+\.trycloudflare\.com")
# Chunks that look like base64 (length 40+)
ENCODED_CHUNK_PATTERN = re.compile(r"[A-Za-z0-9+/_-]{40,}={0,2}")


def link_path(app: str):
    safe_name = re.sub(r"[^a-z0-9-]", "-", app.lower())
    return state.STATE_DIR / f"link-{safe_name}.txt"


def save(app: str, link: str) -> None:
    """Save as an owner-only file (links may carry device auth values)"""
    state.write_private(link_path(app), link.strip())


def load(app: str) -> str | None:
    try:
        text = link_path(app).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def _decode_chunk(chunk: str) -> tuple[str, bool, bool] | None:
    """(decoded text, was url-safe, had padding). None if not JSON"""
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
    """Every trycloudflare host in the link > new_host. (new link, replacement count)"""
    replaced = 0

    def replace_hosts(text: str) -> str:
        nonlocal replaced
        updated, count = TUNNEL_HOST_PATTERN.subn(new_host, text)
        replaced += count
        return updated

    # Undo one layer of percent-encoding to look inside (#pairing=orca%3A%2F%2F...)
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
    # Re-wrap: encode only the value after the first # as before
    if "#" in working:
        head, fragment = working.split("#", 1)
        if "=" in fragment:
            key, value = fragment.split("=", 1)
            return f"{head}#{key}={urllib.parse.quote(value, safe='')}", replaced
    return urllib.parse.quote(working, safe=":/?#&="), replaced
