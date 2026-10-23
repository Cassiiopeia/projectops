"""이슈 본문 기계적 가리기: 비밀값 · 개인 식별 형식 · 홈 경로 (URL 은 건드리지 않음 — 판단은 에이전트)"""
from __future__ import annotations

import re
from pathlib import Path

# 표식 형식: <redacted:종류>
MASK = "<redacted:{kind}>"

# 규칙 (순서 고정: 헤더 > 토큰 > 키=값 > 이메일 > 주민번호 > 사업자번호 > 전화 > 입력값 > 홈 경로)
# 헤더: 줄 머리 · curl -H "..." · JSON "authorization": "..." 모두 (값은 따옴표·역슬래시·줄 끝 직전까지)
HEADER_RE = re.compile(r'(?i)\b(authorization|cookie|set-cookie)(\\?["\']?\s*:\s*\\?["\']?)([^"\'\\\n]+)')
TOKEN_RE = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}"
    r"|eyJ[\w-]+\.[\w-]+\.[\w-]+|AIza[\w-]{35}|xox[abposr]-[\w-]+|glpat-[\w-]{20,})"
    r"|\bBearer\s+[A-Za-z0-9._~+/=-]{6,}")
# 키=값: DB_PASSWORD · global_pat 같은 접두 키, 따옴표 · JSON 이스케이프 허용
SECRET_KV_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])((?:[A-Za-z0-9]+_)*(?:password|passwd|secret|token|api[_-]?key|pat))"
    r"(\\?[\"']?\s*[=:]\s*\\?[\"']?)(?!<redacted)([^\s&\"'\\,}]+)")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
# 주민번호: 뒷자리를 사이트가 일부 가린 형태(991029-*******)도 생년월일 노출이라 같이
RRN_RE = re.compile(r"(?<!\d)\d{6}-[1-4*•●][\d*•●]{6}(?![\d*])")
BUSINESS_NO_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{5}(?!\d)")
PHONE_RE = re.compile(r"(?<!\d)01[016789]-?\d{3,4}-?\d{4}(?!\d)")
# 입력한 값: web type --text "…" · Playwright fill('…') / type('…') (이름·생년월일 등 개인 입력이 대부분)
TYPED_TEXT_RE = re.compile(r"(\btype\b[^\n;|&]*?--text\s+\\?[\"'])([^\"'\\\n]+)")
TYPED_CALL_RE = re.compile(r"(\.(?:fill|type)\(\s*\\?[\"'])([^\"'\\\n]+)")


def _home_forms() -> list[tuple[str, str]]:
    """홈 경로 두 형태 > ~ (/Users/이름, 기록 폴더 이름 속 -Users-이름)"""
    home = str(Path.home()).rstrip("/")
    if not home or home == "/":
        return []
    return [(home, "~"), ("-" + home.strip("/").replace("/", "-"), "-~")]


def redact_text(text: str) -> tuple[str, dict[str, int]]:
    """글 > (가린 글, 종류별 개수). 바뀐 것이 없으면 빈 dict"""
    counts: dict[str, int] = {}

    def apply(kind: str, pattern: re.Pattern, replacement) -> None:
        nonlocal text
        text, hits = pattern.subn(replacement, text)
        if hits:
            counts[kind] = counts.get(kind, 0) + hits

    apply("header", HEADER_RE, lambda m: m.group(1) + m.group(2) + MASK.format(kind="header"))
    apply("token", TOKEN_RE, MASK.format(kind="token"))
    apply("secret", SECRET_KV_RE, lambda m: m.group(1) + m.group(2) + MASK.format(kind="secret"))
    apply("email", EMAIL_RE, MASK.format(kind="email"))
    apply("rrn", RRN_RE, MASK.format(kind="rrn"))
    apply("business-no", BUSINESS_NO_RE, MASK.format(kind="business-no"))
    apply("phone", PHONE_RE, MASK.format(kind="phone"))
    apply("typed", TYPED_TEXT_RE, lambda m: m.group(1) + MASK.format(kind="typed"))
    apply("typed", TYPED_CALL_RE, lambda m: m.group(1) + MASK.format(kind="typed"))
    for original, replacement in _home_forms():
        hits = text.count(original)
        if hits:
            text = text.replace(original, replacement)
            counts["home-path"] = counts.get("home-path", 0) + hits
    return text, counts
