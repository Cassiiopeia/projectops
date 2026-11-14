#!/usr/bin/env python3
"""
asc_client.py

App Store Connect API client (issue #643). The only place ASC is called.
A library module without a CLI; ios_release.py and others import it.

  - Auth: env ASC_KEY_ID / ASC_ISSUER_ID / ASC_KEY_PATH (.p8 path)
    Actions injects missing secrets as empty strings, so an empty value also counts as "missing".
  - The JWT ES256 signature is made with the openssl CLI, using only the standard library.
    openssl returns a DER signature, so it is converted to the raw form JWT needs (r||s, 64 bytes).
  - Where lookups fail (insufficient permissions, network), the caller falls back.
    This module only reports failure as AscError or returns None; it decides nothing itself.
"""

from __future__ import annotations

import base64
import http.client
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# AscError text reaches PR comments as a reason, so it follows the repo language (#769). Warning logs are English
from i18n.messages import t as message  # noqa: E402

BASE_URL = "https://api.appstoreconnect.apple.com"
_PAGE_LIMIT = 200
_HTTP_TIMEOUT = 30
_JWT_TTL = 1200


class AscError(Exception):
    """ASC call failure. For HTTP errors, status holds the status code."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _warn(msg: str) -> None:
    print(f"warning: {msg}", file=sys.stderr)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _read_der_len(buf: bytes, pos: int) -> tuple[int, int]:
    """Read a DER length field and return (length, next position). Handles the long form (0x81, etc.) too."""
    first = buf[pos]
    if first < 0x80:
        return first, pos + 1
    n = first & 0x7F
    return int.from_bytes(buf[pos + 1:pos + 1 + n], "big"), pos + 1 + n


def der_to_raw(der: bytes) -> bytes:
    """Convert a DER ECDSA signature to 64-byte r||s (32 bytes each, left zero-padded)."""
    if not der or der[0] != 0x30:
        raise ValueError("not a DER signature")
    _, pos = _read_der_len(der, 1)
    parts = []
    for _ in range(2):
        if der[pos] != 0x02:
            raise ValueError("not a DER integer")
        ln, pos = _read_der_len(der, pos + 1)
        # Drop the leading 0x00 used for positive notation, then left-pad to 32 bytes
        parts.append(der[pos:pos + ln].lstrip(b"\x00").rjust(32, b"\x00"))
        pos += ln
    if any(len(p) != 32 for p in parts):
        raise ValueError("r or s is longer than 32 bytes")
    return parts[0] + parts[1]


def make_jwt(key_id: str, issuer_id: str, key_path: str, now: int | None = None, ttl: int = _JWT_TTL) -> str:
    """JWT for the ASC API. Lifetime must be 20 minutes (1200 seconds) or less."""
    iat = int(time.time()) if now is None else int(now)
    header = {"alg": "ES256", "kid": key_id, "typ": "JWT"}
    payload = {"iss": issuer_id, "iat": iat, "exp": iat + ttl, "aud": "appstoreconnect-v1"}
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(payload, separators=(",", ":")).encode())
    ).encode("ascii")
    proc = subprocess.run(["openssl", "dgst", "-sha256", "-sign", key_path],
                          input=signing_input, capture_output=True, check=True)
    return signing_input.decode("ascii") + "." + _b64url(der_to_raw(proc.stdout))


def _sign_with_base64_key(key_id: str, issuer: str, key_base64: str) -> str:
    """Unpack the base64 key (Secret as is) into a temp file, sign, and delete it at once — so workflows need not create a key file."""
    with tempfile.TemporaryDirectory() as folder:
        key_file = Path(folder) / "AuthKey.p8"
        key_file.write_bytes(base64.b64decode(key_base64))
        key_file.chmod(0o600)
        return make_jwt(key_id, issuer, str(key_file))


def token_from_env() -> str | None:
    """Build a token from env vars. None if any is empty or signing fails (the caller falls back).

    Key source order: ASC_KEY_PATH (file) > ASC_KEY_BASE64 (raw Secret).
    """
    key_id = os.environ.get("ASC_KEY_ID", "").strip()
    issuer = os.environ.get("ASC_ISSUER_ID", "").strip()
    key_path = os.environ.get("ASC_KEY_PATH", "").strip()
    key_base64 = os.environ.get("ASC_KEY_BASE64", "").strip()
    if not (key_id and issuer and (key_path or key_base64)):
        return None
    try:
        if key_path:
            return make_jwt(key_id, issuer, key_path)
        return _sign_with_base64_key(key_id, issuer, key_base64)
    except Exception as e:  # fall back on any failure: no openssl, missing/broken key file, etc.
        _warn(f"could not create the App Store Connect token, continuing without App Store Connect lookups: {e}")
        return None


def request(url: str, token: str, timeout: int = _HTTP_TIMEOUT) -> dict:
    """GET call. Kept as a module-level function because tests monkeypatch it."""
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}", "User-Agent": "projectops-asc-client"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise AscError(f"ASC HTTP {e.code}: {url}", status=e.code) from e
    except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError) as e:
        # Connection resets, mid-read drops, TLS errors and bad response bodies must all become AscError
        # so the caller falls back (instead of dying with a traceback where only AscError is caught).
        # JSONDecodeError and UnicodeDecodeError are subclasses of ValueError.
        raise AscError(message("ios_release.asc.call_failed", error=e)) from e


def _url(path: str, params: dict) -> str:
    return f"{BASE_URL}{path}?{urllib.parse.urlencode(params)}"


def get_all(path: str, params: dict, token: str) -> list[dict]:
    """Follow links.next to the end and collect data items."""
    items: list[dict] = []
    url: str | None = _url(path, {**params, "limit": _PAGE_LIMIT})
    while url:
        page = request(url, token)
        items.extend(page.get("data") or [])
        url = (page.get("links") or {}).get("next")
    return items


def find_app_id(bundle_id: str, token: str) -> str | None:
    """Accept only apps with an exact bundle ID match (filters out prefix matches the filter may return)."""
    page = request(_url("/v1/apps", {"filter[bundleId]": bundle_id, "limit": _PAGE_LIMIT}), token)
    for app in page.get("data") or []:
        if (app.get("attributes") or {}).get("bundleId") == bundle_id:
            return app.get("id")
    return None


def list_app_store_versions(app_id: str, token: str) -> list[dict]:
    """iOS app version list. Holds both new (appVersionState) and old (appStoreState) states."""
    rows = get_all(f"/v1/apps/{app_id}/appStoreVersions", {"filter[platform]": "IOS"}, token)
    out = []
    for r in rows:
        a = r.get("attributes") or {}
        out.append({"version": a.get("versionString"),
                    "appVersionState": a.get("appVersionState"),
                    "appStoreState": a.get("appStoreState")})
    return out


def parse_build_number(value: str | None) -> int | None:
    """The part before the first dot if it is an integer. Does not crash on dotted (45300.1) or non-integer values."""
    if not value:
        return None
    head = str(value).split(".", 1)[0].strip()
    return int(head) if head.isdigit() else None


def _numbers(rows: list[dict], *keys: str) -> list[int]:
    nums = []
    for r in rows:
        a = r.get("attributes") or {}
        for k in keys:
            n = parse_build_number(a.get(k))
            if n is not None:
                nums.append(n)
    return nums


def recent_max_build(app_id: str, token: str) -> int | None:
    """Highest recently uploaded build number. Looks only at the first page of builds and buildUploads.
    Sort order is not guaranteed by the docs, so values are collected and the max taken. None if both fail."""
    nums: list[int] = []
    ok = False
    for path, keys in ((f"/v1/builds", ("version",)), (f"/v1/apps/{app_id}/buildUploads", ("cfBundleVersion", "version"))):
        params = {"sort": "-uploadedDate", "limit": _PAGE_LIMIT}
        if path == "/v1/builds":
            params["filter[app]"] = app_id
        try:
            nums += _numbers(request(_url(path, params), token).get("data") or [], *keys)
            ok = True
        except AscError as e:
            _warn(f"part of the latest build lookup failed ({path}): {e}")
    return max(nums) if ok and nums else None


def build_exists(app_id: str, build_number: int, token: str) -> bool:
    """Whether a build with this number is already uploaded. True if either finds it.
    If not found but either lookup failed, "absent" cannot be asserted, so AscError is raised
    (the caller blocks re-upload; a just-uploaded build may appear in the builds list late)."""
    target = str(build_number)
    errors: list[AscError] = []
    queries = (
        ("/v1/builds", {"filter[app]": app_id, "filter[version]": target, "limit": _PAGE_LIMIT}, "version"),
        (f"/v1/apps/{app_id}/buildUploads", {"filter[cfBundleVersion]": target, "limit": _PAGE_LIMIT}, "cfBundleVersion"),
    )
    for path, params, key in queries:
        try:
            for r in request(_url(path, params), token).get("data") or []:
                if str((r.get("attributes") or {}).get(key)) == target:
                    return True
        except AscError as e:
            errors.append(e)
    if errors:
        raise errors[0]
    return False
