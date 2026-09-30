"""App Store Connect 클라이언트 테스트 (이슈 #643). 네트워크 호출 없음, 모두 monkeypatch."""
import base64
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asc_client as asc


def _der(r: bytes, s: bytes) -> bytes:
    """r, s 정수 바이트열로 DER ECDSA 서명을 손으로 조립한다 (짧은 길이 형식)."""
    body = b"\x02" + bytes([len(r)]) + r + b"\x02" + bytes([len(s)]) + s
    return b"\x30" + bytes([len(body)]) + body


def test_der_to_raw_pads_to_64_bytes():
    r = bytes([0x11] * 31)                 # 31바이트: 좌측 0 패딩 필요
    s = b"\x00" + bytes([0x99] * 32)       # 33바이트: 선행 0x00 제거 필요
    raw = asc.der_to_raw(_der(r, s))
    assert len(raw) == 64
    assert raw[:32] == b"\x00" + r
    assert raw[32:] == bytes([0x99] * 32)


def _b64d(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl 없음")
def test_make_jwt_verifies_with_openssl(tmp_path):
    key = tmp_path / "k.p8"
    gen = subprocess.run(
        "openssl ecparam -name prime256v1 -genkey -noout | openssl pkcs8 -topk8 -nocrypt",
        shell=True, capture_output=True, check=True)
    key.write_bytes(gen.stdout)
    pub = tmp_path / "pub.pem"
    pub.write_bytes(subprocess.run(["openssl", "ec", "-in", str(key), "-pubout"],
                                   capture_output=True, check=True).stdout)

    token = asc.make_jwt("KID", "ISS", str(key), now=1000)
    h, p, sig = token.split(".")
    assert json.loads(_b64d(h)) == {"alg": "ES256", "kid": "KID", "typ": "JWT"}
    assert json.loads(_b64d(p)) == {"iss": "ISS", "iat": 1000, "exp": 2200, "aud": "appstoreconnect-v1"}

    # raw r||s 를 DER로 되돌려 openssl로 검증
    raw = _b64d(sig)
    assert len(raw) == 64

    def _int(b: bytes) -> bytes:
        b = b.lstrip(b"\x00") or b"\x00"
        return (b"\x00" + b) if b[0] & 0x80 else b

    der = _der(_int(raw[:32]), _int(raw[32:]))
    (tmp_path / "sig.der").write_bytes(der)
    (tmp_path / "msg").write_bytes(f"{h}.{p}".encode())
    res = subprocess.run(["openssl", "dgst", "-sha256", "-verify", str(pub),
                          "-signature", str(tmp_path / "sig.der"), str(tmp_path / "msg")],
                         capture_output=True)
    assert res.returncode == 0, res.stdout + res.stderr


def test_token_from_env_none_when_empty(monkeypatch):
    # Actions는 없는 시크릿을 빈 문자열로 주입한다 (Review Focus 3)
    for k in ("ASC_KEY_ID", "ASC_ISSUER_ID", "ASC_KEY_PATH"):
        monkeypatch.setenv(k, "")
    assert asc.token_from_env() is None
    monkeypatch.setenv("ASC_KEY_ID", "K")
    monkeypatch.setenv("ASC_ISSUER_ID", "I")
    monkeypatch.delenv("ASC_KEY_PATH")
    assert asc.token_from_env() is None


def test_token_from_env_none_when_signing_fails(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("ASC_KEY_ID", "K")
    monkeypatch.setenv("ASC_ISSUER_ID", "I")
    monkeypatch.setenv("ASC_KEY_PATH", str(tmp_path / "missing.p8"))
    assert asc.token_from_env() is None
    assert "경고" in capsys.readouterr().err


def test_get_all_follows_next(monkeypatch):
    calls = []
    pages = [
        {"data": [{"id": "1"}, {"id": "2"}], "links": {"next": "https://x/next"}},
        {"data": [{"id": "3"}], "links": {}},
    ]

    def fake(url, token, timeout=30):
        calls.append(url)
        return pages[len(calls) - 1]

    monkeypatch.setattr(asc, "request", fake)
    items = asc.get_all("/v1/builds", {"a": "b"}, "tok")
    assert [i["id"] for i in items] == ["1", "2", "3"]
    assert len(calls) == 2 and calls[1] == "https://x/next"
    assert "limit=200" in calls[0]


def test_find_app_id_exact_match(monkeypatch):
    monkeypatch.setattr(asc, "request", lambda url, token, timeout=30: {"data": [
        {"id": "A1", "attributes": {"bundleId": "com.a.b"}},
        {"id": "A2", "attributes": {"bundleId": "com.a"}},
    ]})
    assert asc.find_app_id("com.a", "tok") == "A2"
    assert asc.find_app_id("com.zzz", "tok") is None


def test_list_app_store_versions_shape(monkeypatch):
    monkeypatch.setattr(asc, "request", lambda url, token, timeout=30: {"data": [
        {"attributes": {"versionString": "2.1.2", "appVersionState": "READY_FOR_DISTRIBUTION",
                        "appStoreState": "READY_FOR_SALE"}},
        {"attributes": {"versionString": "2.2.0"}},
    ]})
    assert asc.list_app_store_versions("A", "tok") == [
        {"version": "2.1.2", "appVersionState": "READY_FOR_DISTRIBUTION", "appStoreState": "READY_FOR_SALE"},
        {"version": "2.2.0", "appVersionState": None, "appStoreState": None},
    ]


@pytest.mark.parametrize("v,expected", [("45105", 45105), ("45300.1", 45300), ("abc", None),
                                        (None, None), ("", None)])
def test_parse_build_number(v, expected):
    assert asc.parse_build_number(v) == expected


def _router(builds=None, uploads=None):
    """URL에 따라 builds / buildUploads 응답을 돌려주는 가짜 request."""
    def fake(url, token, timeout=30):
        src = uploads if "buildUploads" in url else builds
        if isinstance(src, Exception):
            raise src
        return {"data": src or [], "links": {}}
    return fake


def test_recent_max_build_combines_sources(monkeypatch):
    monkeypatch.setattr(asc, "request", _router(
        builds=[{"attributes": {"version": "214"}}, {"attributes": {"version": "45104"}}],
        uploads=[{"attributes": {"cfBundleVersion": "45105"}}]))
    assert asc.recent_max_build("A", "tok") == 45105
    err = asc.AscError("boom", status=403)
    monkeypatch.setattr(asc, "request", _router(builds=err, uploads=err))
    assert asc.recent_max_build("A", "tok") is None


def test_build_exists_true_and_false(monkeypatch):
    monkeypatch.setattr(asc, "request", _router(builds=[{"attributes": {"version": "77"}}], uploads=[]))
    assert asc.build_exists("A", 77, "tok") is True
    monkeypatch.setattr(asc, "request", _router(builds=[], uploads=[{"attributes": {"cfBundleVersion": "78"}}]))
    assert asc.build_exists("A", 78, "tok") is True
    monkeypatch.setattr(asc, "request", _router(builds=[], uploads=[]))
    assert asc.build_exists("A", 79, "tok") is False


def test_build_exists_raises_when_any_query_fails_and_not_found(monkeypatch):
    # 한쪽 조회만 실패해도 "없음"으로 단정하면 이미 올라간 빌드를 재업로드할 수 있다 (U4)
    err = asc.AscError("boom", status=403)
    monkeypatch.setattr(asc, "request", _router(builds=err, uploads=[]))
    with pytest.raises(asc.AscError):
        asc.build_exists("A", 80, "tok")
    monkeypatch.setattr(asc, "request", _router(builds=[], uploads=err))
    with pytest.raises(asc.AscError):
        asc.build_exists("A", 80, "tok")
    # 다른 쪽에서 찾았다면 확정이므로 실패한 조회는 무시
    monkeypatch.setattr(asc, "request", _router(builds=err, uploads=[{"attributes": {"cfBundleVersion": "80"}}]))
    assert asc.build_exists("A", 80, "tok") is True

