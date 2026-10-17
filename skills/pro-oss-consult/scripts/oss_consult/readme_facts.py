"""README·건강 파일·라벨 사실 정리 (순수 함수, 네트워크 없음)
첫 화면 잘라내기·세 위치에서 파일 찾기·개수 측정만 하고 판정은 하지 않음
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


# 첫 화면으로 넘기는 줄 수. 에이전트가 원문을 직접 읽고 판단하되 전문을 싣지는 않는다(토큰).
TOP_LINES = 40
MAX_TOP_LINES = 400
HEAD_LINES = 15


def analyze_readme(text: str | None, top_lines: int = TOP_LINES) -> dict:
    """README를 에이전트가 읽기 좋게 줄인다. 판정은 하지 않는다.

    - `top`: 첫 화면 원문 — 가치 제안·데모·설치 위치는 이걸 읽고 판단한다
    - `headings`: 전체 구조 — 비교·벤치마크·"맞지 않는 경우" 절이 있는지는 이걸 보고 판단한다
    - 나머지는 세기만 한 측정값. 잘린 목록은 `*_total`/`*_truncated` 로 알린다
    """
    if not text:
        return {"present": False}
    lines = text.splitlines()
    headings = [ln.strip() for ln in lines if re.match(r"^#{1,3}\s", ln)]
    first_code = next((i + 1 for i, ln in enumerate(lines) if ln.strip().startswith("```")), None)
    # 비율은 사람이 읽는 본문으로만 잰다 — 코드 블록·URL·링크 주소·HTML 태그의 영문자는 뺀다
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
        # URL 단위로 센다 — shields.io/badge/... 하나에 패턴 두 개가 걸려 두 번 세는 것을 막는다
        "badges": sum(1 for u in re.findall(r"https?://[^\s)\"'<>]+", text) if _BADGE.search(u)),
        "media": media[:30],
        "media_total": len(media),
        "media_truncated": len(media) > 30,
        "first_code_block_line": first_code,
        "translations_linked": sorted({m.group(1).lower() for m in _TRANSLATION.finditer(text)}),
        "non_english_ratio": round(foreign / (len(letters) or 1), 3),
    }


def text_head(text: str | None, n: int = HEAD_LINES) -> dict:
    """문서의 앞 n줄과 총 줄 수. '빈 문서'인지는 에이전트가 원문을 보고 판단한다."""
    lines = (text or "").splitlines()
    return {"head": "\n".join(lines[:n]), "lines": len(lines)}


# 찾는 파일 → 흔히 두는 위치. GitHub은 .github/ → 루트 → docs/ 순으로 찾는다.
# 이름은 **대소문자·하이픈/언더스코어·확장자 변형을 무시**하고 맞춘다 (CODE-OF-CONDUCT.md, CHANGES.rst 등).
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
    """파일 이름이 건강 파일 `key` 의 변형인지 (대소문자·하이픈·확장자 무시)."""
    stems, exts = _HEALTH_FILES[key]
    stem, ext = _stem_ext(name)
    return stem in stems and ext in exts


def _find_in(listing: dict, key: str) -> dict | None:
    """한 위치에서 첫 일치를 찾되, 같은 이름의 파일이 폴더보다 우선한다."""
    hits = [(n, t) for n, t in listing.items() if match_health_name(key, n)]
    hits.sort(key=lambda h: (h[1] != "file", h[0]))
    return {"name": hits[0][0], "type": hits[0][1]} if hits else None


def detect_files(root: dict, github: dict, docs: dict, templates: list[str],
                 extra: dict[str, dict] | None = None) -> dict:
    """루트·.github·docs 목록(name → type)에서 건강 파일을 찾는다.

    "있다"와 "작동한다"를 구분한다 — LICENSE가 폴더면 GitHub이 인식하지 못한다(coursebook).
    GitHub community profile API는 yml 이슈 폼을 인식하지 못하므로 폴더를 직접 본다.
    `extra` 는 개인정보처리방침 탐색용 하위 폴더 목록 (경로 → 목록).
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
    # 배포형 앱 점검용 (apps.md). 개인정보처리방침 파일은 이름이 제각각이라 소문자로 훑는다.
    # fastlane 은 Flutter 앱이면 루트가 아니라 android/·ios/ 아래에 있으므로 여기서 단정하지 않고
    # 모바일 폴더 존재만 알린다 — 하위 확인은 에이전트가 한다.
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
    """개인정보처리방침을 한 단계 더 내려가 볼 폴더 (목록에 실제로 있는 것만 — API 호출 최소화)."""
    out = [f"docs/{d}" for d in ("store", "legal", "privacy") if docs.get(d) == "dir"]
    if root.get("store") == "dir":
        out.append("store")
    if root.get("fastlane") == "dir":
        out.append("fastlane/metadata")
    return out


def summarize_labels(names: list[str], capped: bool = False) -> dict:
    """라벨 이름 전체와 개수만 준다. 체계가 좋은지는 에이전트가 이름을 보고 판단한다."""
    return {"count": len(names), "names": names[:150],
            "truncated": len(names) > 150, "capped": capped}
