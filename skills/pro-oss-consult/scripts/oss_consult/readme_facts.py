"""Tidy facts about the README, health files and labels (pure functions, no network)
Only cuts the first screen, finds files in three locations and counts; makes no verdicts
"""
from __future__ import annotations

import re

_HANGUL = re.compile(r"[가-힣]")
_CJK = re.compile(r"[぀-ヿ一-鿿]")
_BADGE = re.compile(r"(shields\.io|badge\.svg|badgen\.net|/badge/|codecov\.io|trendshift)", re.I)
_MEDIA = re.compile(
    r"https?://[^\s)\"'<>]+?(?:\.(?:gif|mp4|webm|mov|png|jpe?g|svg|webp)\b[^\s)\"'<>]*"
    r"|asciinema\.org/a/[^\s)\"'<>]+|youtube\.com/watch[^\s)\"'<>]+|youtu\.be/[^\s)\"'<>]+"
    r"|user-attachments/assets/[^\s)\"'<>]+)"
    r"|(?<=\]\()(?!https?:)[^\s)]+\.(?:gif|mp4|webm|mov|png|jpe?g|svg|webp)",
    re.I,
)
_TRANSLATION = re.compile(r"README[._-]([a-z]{2}(?:[-_][A-Za-z]{2,4})?)\.md", re.I)


# Lines passed as the first screen. The agent reads the source itself but the full text is not included (tokens).
TOP_LINES = 40
MAX_TOP_LINES = 400
HEAD_LINES = 15


def analyze_readme(text: str | None, top_lines: int = TOP_LINES) -> dict:
    """Trim the README for the agent to read. No verdicts.

    - `top`: the first screen as is — read it to judge the value proposition, demo and install location
    - `headings`: the overall structure — read it to judge whether comparison, benchmark or "when not to use" sections exist
    - The rest are counts only. Truncated lists are flagged with `*_total`/`*_truncated`
    """
    if not text:
        return {"present": False}
    lines = text.splitlines()
    headings = [ln.strip() for ln in lines if re.match(r"^#{1,3}\s", ln)]
    first_code = next((i + 1 for i, ln in enumerate(lines) if ln.strip().startswith("```")), None)
    # Measure ratios on human-readable prose only — drop letters from code blocks, URLs, link targets and HTML tags
    prose = re.sub(r"```.*?```", "", text, flags=re.S)
    prose = re.sub(r"\]\([^)]*\)|https?://\S+|<[^>]+>", " ", prose)
    letters = re.findall(r"[A-Za-z가-힣぀-ヿ一-鿿]", prose)
    foreign = len(_HANGUL.findall(prose)) + len(_CJK.findall(prose))
    media = []
    for i, ln in enumerate(lines):
        for m in _MEDIA.finditer(ln):
            if not _BADGE.search(m.group(0)):
                media.append({"line": i + 1, "ref": m.group(0)[:160]})
    return {
        "present": True,
        "lines": len(lines),
        "top": "\n".join(lines[:top_lines]),
        "top_lines": min(top_lines, len(lines)),
        "headings": headings[:60],
        "headings_total": len(headings),
        "headings_truncated": len(headings) > 60,
        # Count per URL — keeps one shields.io/badge/... matching two patterns from being counted twice
        "badges": sum(1 for u in re.findall(r"https?://[^\s)\"'<>]+", text) if _BADGE.search(u)),
        "media": media[:30],
        "media_total": len(media),
        "media_truncated": len(media) > 30,
        "first_code_block_line": first_code,
        "translations_linked": sorted({m.group(1).lower() for m in _TRANSLATION.finditer(text)}),
        "non_english_ratio": round(foreign / (len(letters) or 1), 3),
    }


def text_head(text: str | None, n: int = HEAD_LINES) -> dict:
    """First n lines of a document and its total line count. Whether it is 'empty' is for the agent to judge from the source."""
    lines = (text or "").splitlines()
    return {"head": "\n".join(lines[:n]), "lines": len(lines)}


# File to find → where it is usually kept. GitHub looks in .github/ → root → docs/ in that order.
# Names match **ignoring case, hyphen/underscore and extension variants** (CODE-OF-CONDUCT.md, CHANGES.rst, etc.).
_DOC_EXT = ("", ".md", ".markdown", ".rst", ".txt", ".adoc")
_HEALTH_FILES = {
    "license": (("license", "licence", "copying", "unlicense"), _DOC_EXT),
    "contributing": (("contributing",), _DOC_EXT),
    "code_of_conduct": (("code_of_conduct",), _DOC_EXT),
    "security": (("security",), _DOC_EXT),
    "support": (("support",), _DOC_EXT),
    "changelog": (("changelog", "change_log", "changes", "history", "releases", "release_notes", "news"), _DOC_EXT),
    "governance": (("governance",), _DOC_EXT),
    "roadmap": (("roadmap",), _DOC_EXT),
    "architecture": (("architecture",), _DOC_EXT),
    "agents_md": (("agents", "claude"), _DOC_EXT),
    "claude_md": (("claude",), _DOC_EXT),
    "codeowners": (("codeowners",), ("",)),
    "funding": (("funding",), (".yml", ".yaml")),
    "citation": (("citation",), (".cff",)),
    "pr_template": (("pull_request_template",), _DOC_EXT),
    "dependabot": (("dependabot", "renovate"), (".yml", ".yaml", ".json", ".json5")),
}


def _stem_ext(name: str) -> tuple[str, str]:
    base = name.lower()
    for ext in (".markdown", ".json5", ".yaml", ".adoc", ".json", ".yml", ".cff", ".rst", ".txt", ".md"):
        if base.endswith(ext):
            return base[: -len(ext)].replace("-", "_"), ext
    return base.replace("-", "_"), ""


def match_health_name(key: str, name: str) -> bool:
    """Whether a file name is a variant of health file `key` (ignoring case, hyphens and extension)."""
    stems, exts = _HEALTH_FILES[key]
    stem, ext = _stem_ext(name)
    return stem in stems and ext in exts


def _find_in(listing: dict, key: str) -> dict | None:
    """Find the first match in one location, with a file of the same name winning over a folder."""
    hits = [(n, t) for n, t in listing.items() if match_health_name(key, n)]
    hits.sort(key=lambda h: (h[1] != "file", h[0]))
    return {"name": hits[0][0], "type": hits[0][1]} if hits else None


def detect_files(root: dict, github: dict, docs: dict, templates: list[str],
                 extra: dict[str, dict] | None = None) -> dict:
    """Find health files in the root, .github and docs listings (name → type).

    Tell "exists" apart from "works" — if LICENSE is a folder, GitHub does not recognize it (coursebook).
    The GitHub community profile API does not recognize yml issue forms, so the folder is checked directly.
    `extra` lists subfolders to search for a privacy policy (path → listing).
    """
    found: dict = {}
    for key in _HEALTH_FILES:
        hit = None
        for where, listing in ((".github", github), ("root", root), ("docs", docs)):
            h = _find_in(listing, key)
            if h:
                hit = {"where": where, **h}
                break
        found[key] = hit
    lic = found.get("license")
    if lic and lic["type"] != "file":
        lic["license_is_dir"] = True
    forms = [t for t in templates if t.endswith((".yml", ".yaml")) and t != "config.yml"]
    md = [t for t in templates if t.endswith(".md")]
    found["issue_templates"] = {
        "forms_yml": len(forms),
        "markdown": len(md),
        "config_yml": "config.yml" in templates,
    }
    found["docs_dir"] = "docs" in root or "website" in root
    found["examples_dir"] = "examples" in root or "example" in root
    found["skills_dir"] = "skills" in root
    # For checking deployable apps (apps.md). Privacy policy file names vary, so scan them in lowercase.
    # In a Flutter app fastlane lives under android/·ios/, not the root, so do not decide here;
    # only report that mobile folders exist — the agent checks below them.
    places = [("root", root), ("docs", docs), (".github", github)] + sorted((extra or {}).items())
    priv = None
    for where, listing in places:
        for n, t in listing.items():
            if n.lower().startswith(("privacy", "privacy_policy", "개인정보")):
                priv = {"where": where, "name": n, "type": t}
                break
        if priv:
            break
    found["privacy_policy"] = priv
    found["privacy_searched"] = [w for w, _ in places]
    found["store_metadata_root"] = "fastlane" in root
    found["mobile_dirs"] = sorted(d for d in ("android", "ios") if d in root)
    return found


def extra_privacy_dirs(root: dict, docs: dict) -> list[str]:
    """Folders to look one level deeper for a privacy policy (only ones actually in the listing — minimizes API calls)."""
    out = [f"docs/{d}" for d in ("store", "legal", "privacy") if docs.get(d) == "dir"]
    if root.get("store") == "dir":
        out.append("store")
    if root.get("fastlane") == "dir":
        out.append("fastlane/metadata")
    return out


def summarize_labels(names: list[str], capped: bool = False) -> dict:
    """Return only all label names and their count. Whether the scheme is good is for the agent to judge from the names."""
    return {"count": len(names), "names": names[:150],
            "truncated": len(names) > 150, "capped": capped}
