#!/usr/bin/env python3
"""
asc_client.py

App Store Connect API 클라이언트 (이슈 #643). ASC 호출의 유일한 위치다.
CLI가 없는 라이브러리 모듈이며 ios_release.py 등이 import 해서 쓴다.

  - 인증: 환경변수 ASC_KEY_ID / ASC_ISSUER_ID / ASC_KEY_PATH (.p8 경로)
    Actions는 없는 시크릿을 빈 문자열로 주입하므로 빈 값도 "없음"으로 본다.
  - JWT ES256 서명은 openssl CLI로 만들어 외부 패키지 없이 표준 라이브러리만 쓴다.
    openssl은 DER 서명을 주므로 JWT가 요구하는 raw(r||s 64바이트)로 바꾼다.
  - 조회가 안 되는 환경(권한 부족, 네트워크)은 호출하는 쪽이 폴백한다.
    이 모듈은 실패를 AscError로 알리거나 None을 돌려줄 뿐 스스로 판단하지 않는다.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://api.appstoreconnect.apple.com"
_PAGE_LIMIT = 200
_HTTP_TIMEOUT = 30
_JWT_TTL = 1200


class AscError(Exception):
    """ASC 호출 실패. HTTP 오류면 status에 상태 코드가 들어간다."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _warn(msg: str) -> None:
    print(f"경고: {msg}", file=sys.stderr)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _read_der_len(buf: bytes, pos: int) -> tuple[int, int]:
    """DER 길이 필드를 읽어 (길이, 다음 위치)를 돌려준다. 긴 형식(0x81 등)도 처리."""
    first = buf[pos]
    if first < 0x80:
        return first, pos + 1
    n = first & 0x7F
    return int.from_bytes(buf[pos + 1:pos + 1 + n], "big"), pos + 1 + n


def der_to_raw(der: bytes) -> bytes:
    """DER ECDSA 서명을 64바이트 r||s로 바꾼다 (각 32바이트, 좌측 0 패딩)."""
    if not der or der[0] != 0x30:
        raise ValueError("DER 서명 형식이 아닙니다")
    _, pos = _read_der_len(der, 1)
    parts = []
    for _ in range(2):
        if der[pos] != 0x02:
            raise ValueError("DER 정수가 아닙니다")
        ln, pos = _read_der_len(der, pos + 1)
        # 양수 표기용 선행 0x00 제거 후 32바이트로 좌측 패딩
        parts.append(der[pos:pos + ln].lstrip(b"\x00").rjust(32, b"\x00"))
        pos += ln
    if any(len(p) != 32 for p in parts):
        raise ValueError("r 또는 s가 32바이트를 넘습니다")
    return parts[0] + parts[1]


def make_jwt(key_id: str, issuer_id: str, key_path: str, now: int | None = None, ttl: int = _JWT_TTL) -> str:
    """ASC API용 JWT. 수명은 20분(1200초) 이하여야 한다."""
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


def token_from_env() -> str | None:
    """환경변수로 토큰을 만든다. 하나라도 비었거나 서명에 실패하면 None (호출자가 폴백)."""
    key_id = os.environ.get("ASC_KEY_ID", "").strip()
    issuer = os.environ.get("ASC_ISSUER_ID", "").strip()
    key_path = os.environ.get("ASC_KEY_PATH", "").strip()
    if not (key_id and issuer and key_path):
        return None
    try:
        return make_jwt(key_id, issuer, key_path)
    except Exception as e:  # openssl 없음, 키 파일 없음/손상 등 어떤 실패든 폴백
        _warn(f"ASC 토큰 생성 실패, ASC 조회 없이 진행합니다: {e}")
        return None


def request(url: str, token: str, timeout: int = _HTTP_TIMEOUT) -> dict:
    """GET 호출. 테스트에서 monkeypatch 하는 지점이라 모듈 수준 함수로 둔다."""
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}", "User-Agent": "projectops-asc-client"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise AscError(f"ASC HTTP {e.code}: {url}", status=e.code) from e
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise AscError(f"ASC 호출 실패: {e}") from e


def _url(path: str, params: dict) -> str:
    return f"{BASE_URL}{path}?{urllib.parse.urlencode(params)}"


def get_all(path: str, params: dict, token: str) -> list[dict]:
    """links.next를 끝까지 따라가며 data 항목을 모은다."""
    items: list[dict] = []
    url: str | None = _url(path, {**params, "limit": _PAGE_LIMIT})
    while url:
        page = request(url, token)
        items.extend(page.get("data") or [])
        url = (page.get("links") or {}).get("next")
    return items


def find_app_id(bundle_id: str, token: str) -> str | None:
    """번들 ID 정확 일치 앱만 인정한다 (필터가 접두 일치를 돌려줘도 걸러냄)."""
    page = request(_url("/v1/apps", {"filter[bundleId]": bundle_id, "limit": _PAGE_LIMIT}), token)
    for app in page.get("data") or []:
        if (app.get("attributes") or {}).get("bundleId") == bundle_id:
            return app.get("id")
    return None


def list_app_store_versions(app_id: str, token: str) -> list[dict]:
    """iOS 앱 버전 목록. 신형(appVersionState)과 구형(appStoreState) 상태를 모두 담는다."""
    rows = get_all(f"/v1/apps/{app_id}/appStoreVersions", {"filter[platform]": "IOS"}, token)
    out = []
    for r in rows:
        a = r.get("attributes") or {}
        out.append({"version": a.get("versionString"),
                    "appVersionState": a.get("appVersionState"),
                    "appStoreState": a.get("appStoreState")})
    return out


def parse_build_number(value: str | None) -> int | None:
    """첫 번째 점 앞 성분이 정수면 그 값. 점 형식(45300.1)과 비정수도 죽지 않는다."""
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
    """최근 올라간 빌드 번호 중 최대. builds와 buildUploads 첫 페이지만 본다.
    정렬 기준이 문서에 보장되지 않으므로 값을 직접 모아 최대를 구한다. 둘 다 실패하면 None."""
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
            _warn(f"ASC 최근 빌드 조회 일부 실패 ({path}): {e}")
    return max(nums) if ok and nums else None


def build_exists(app_id: str, build_number: int, token: str) -> bool:
    """해당 번호의 빌드가 이미 올라가 있는가. 하나라도 찾으면 True.
    못 찾았는데 한쪽이라도 조회가 실패했으면 "없음"을 단정할 수 없으므로 AscError를 던진다
    (호출자가 재업로드를 막는다. 방금 올린 빌드는 builds 목록 반영이 늦을 수 있다)."""
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
