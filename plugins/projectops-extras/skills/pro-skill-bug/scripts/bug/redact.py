"""Mechanical redaction for issue bodies: secrets, personal ID formats, home paths (URLs untouched; the agent judges those)"""
from __future__ import annotations

import re
from pathlib import Path

# Marker format: <redacted:kind>
MASK = "<redacted:{kind}>"

# Rules (fixed order: header > token > key=value > email > resident number > business number > phone > typed input > home path)
# Header: line start · curl -H "..." · JSON "authorization": "..." (value runs up to a quote, backslash or line end)
HEADER_RE = re.compile(r'(?i)\b(authorization|cookie|set-cookie)(\\?["\']?\s*:\s*\\?["\']?)([^"\'\\\n]+)')
TOKEN_RE = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}"
    r"|eyJ[\w-]+\.[\w-]+\.[\w-]+|AIza[\w-]{35}|xox[abposr]-[\w-]+|glpat-[\w-]{20,})"
    r"|\bBearer\s+[A-Za-z0-9._~+/=-]{6,}")
# key=value: prefixed keys like DB_PASSWORD · global_pat, quotes and JSON escapes allowed
SECRET_KV_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])((?:[A-Za-z0-9]+_)*(?:password|passwd|secret|token|api[_-]?key|pat))"
    r"(\\?[\"']?\s*[=:]\s*\\?[\"']?)(?!<redacted)([^\s&\"'\\,}]+)")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
# Resident number: forms with the back digits partly masked by a site (991029-*******) still expose the birth date, so include them
RRN_RE = re.compile(r"(?<!\d)\d{6}-[1-4*•●][\d*•●]{6}(?![\d*])")
BUSINESS_NO_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{5}(?!\d)")
PHONE_RE = re.compile(r"(?<!\d)01[016789]-?\d{3,4}-?\d{4}(?!\d)")
# Typed values: web type --text "…" · Playwright fill('…') / type('…') (mostly personal input like names and birth dates)
TYPED_TEXT_RE = re.compile(r"(\btype\b[^\n;|&]*?--text\s+\\?[\"'])([^\"'\\\n]+)")
TYPED_CALL_RE = re.compile(r"(\.(?:fill|type)\(\s*\\?[\"'])([^\"'\\\n]+)")


def _home_forms() -> list[tuple[str, str]]:
    """Two forms of home path > ~ (/Users/<name>, -Users-<name> inside transcript folder names)"""
    home = str(Path.home()).rstrip("/")
    if not home or home == "/":
        return []
    return [(home, "~"), ("-" + home.strip("/").replace("/", "-"), "-~")]


def redact_text(text: str) -> tuple[str, dict[str, int]]:
    """Text > (redacted text, count per kind). Empty dict if nothing changed"""
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
