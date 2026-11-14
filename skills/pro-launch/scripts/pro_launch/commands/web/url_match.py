"""Address matching shared by web wait --url-contains, web assert --url and web login --until-url (#1177, #1191, #1201)."""
from __future__ import annotations


def url_without_query(url: str, needle: str) -> str:
    """Address to compare: the URL without ?query and #fragment, so a sign-in page's continue= does not match (#1177)
    A needle that itself contains ? or # is compared with the full URL"""
    if "?" in needle or "#" in needle:
        return url
    return url.split("#", 1)[0].split("?", 1)[0]
