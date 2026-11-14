"""주소 비교 규칙: web wait --url-contains · web assert --url 공통 (#1177 · #1191)."""
from __future__ import annotations


def url_without_query(url: str, needle: str) -> str:
    """비교 대상 주소: ?검색어 · #조각을 뺀 주소 (로그인 주소의 continue= 에 걸리지 않게, #1177)
    찾는 글자에 ? · # 이 있으면 주소 전체와 비교"""
    if "?" in needle or "#" in needle:
        return url
    return url.split("#", 1)[0].split("?", 1)[0]
