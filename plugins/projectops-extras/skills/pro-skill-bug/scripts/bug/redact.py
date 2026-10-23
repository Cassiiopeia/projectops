"""이슈 본문 기계적 가리기: 비밀값 · 개인 식별 형식만 (URL 은 건드리지 않음 — 판단은 에이전트)"""
from __future__ import annotations

import re

# 표식 형식: <redacted:종류>
MASK = "<redacted:{kind}>"

# 규칙 (순서 고정: 헤더 > 토큰 > 키=값 > 이메일 > 주민번호 > 사업자번호 > 전화)
HEADER_LINE_RE = re.compile(r"(?im)^(\s*(?:authorization|cookie|set-cookie)\s*:\s*)(\S.*)$")
HEADER_JSON_RE = re.compile(r'(?i)("(?:authorization|cookie|set-cookie)"\s*:\s*")([^"]+)')
TOKEN_RE = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16})\b")
SECRET_KV_RE = re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key|pat)(\s*[=:]\s*)(?!<redacted)([^\s&\"',]+)")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
RRN_RE = re.compile(r"(?<!\d)\d{6}-[1-4]\d{6}(?!\d)")
BUSINESS_NO_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{5}(?!\d)")
PHONE_RE = re.compile(r"(?<!\d)01[016789]-?\d{3,4}-?\d{4}(?!\d)")


def _count_sub(pattern: re.Pattern, replacement, text: str) -> tuple[str, int]:
    return pattern.subn(replacement, text)


def redact_text(text: str) -> tuple[str, dict[str, int]]:
    """글 > (가린 글, 종류별 개수). 바뀐 것이 없으면 빈 dict"""
    counts: dict[str, int] = {}

    def apply(kind: str, pattern: re.Pattern, replacement) -> None:
        nonlocal text
        text, hits = _count_sub(pattern, replacement, text)
        if hits:
            counts[kind] = counts.get(kind, 0) + hits

    header_mask = MASK.format(kind="header")
    apply("header", HEADER_LINE_RE, lambda m: m.group(1) + header_mask)
    apply("header", HEADER_JSON_RE, lambda m: m.group(1) + header_mask)
    apply("token", TOKEN_RE, MASK.format(kind="token"))
    apply("secret", SECRET_KV_RE, lambda m: m.group(1) + m.group(2) + MASK.format(kind="secret"))
    apply("email", EMAIL_RE, MASK.format(kind="email"))
    apply("rrn", RRN_RE, MASK.format(kind="rrn"))
    apply("business-no", BUSINESS_NO_RE, MASK.format(kind="business-no"))
    apply("phone", PHONE_RE, MASK.format(kind="phone"))
    return text, counts
