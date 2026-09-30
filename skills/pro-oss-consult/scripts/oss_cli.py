#!/usr/bin/env python3
"""oss_cli — oss-consult skill 전용 CLI (#644).

레포가 오픈소스로서 무엇을 갖췄는지 **사실만** 모은다. 판단(성격·결함 여부·점수·우선순위)은
에이전트가 references/rubric.md를 보고 한다 — 데모가 없는 것이 hey에겐 괜찮고
작은 도구에겐 치명적인 것처럼, 같은 사실이 레포 성격에 따라 다르게 읽히기 때문이다.

여기에 두는 것은 "매번 똑같이 해야 하고 토큰을 아끼는 일"뿐이다: API 호출·페이지 넘김,
README 디코딩과 첫 화면 잘라내기, 파일을 세 위치에서 찾기, 비율 같은 측정.
**참/거짓 판정이나 분류를 여기서 만들지 않는다.** 정규식으로 "비교 절이 있다"고 단정하는 순간
에이전트가 원문을 안 읽고 그 값을 믿는다.

서브커맨드: collect, local-facts, list-repos, get-output-path
"""
from __future__ import annotations

import base64
import itertools
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.emit import emit  # noqa: E402
from common.cli_parser import JSONArgumentParser, run_cli  # noqa: E402

_API = "https://api.github.com"

# ── 순수 함수 (네트워크 없음 — 테스트 대상) ──────────────────────────────

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

# ── 로컬 clone 측정 (2차: 코드 확장성·의존성·비밀 파일) ──────────────────
# 여기도 사실만 낸다. "확장성이 낮다"·"라이선스가 위험하다"는 에이전트가 성격을 보고 판단한다.

_SOURCE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".dart", ".go", ".rs", ".rb", ".php", ".swift", ".vue"}
_CATALOG_DIRS = {"i18n", "locales", "locale", "l10n", "lang", "translations", "messages"}
_SECRET_PATTERNS = (
    re.compile(r"(^|/)\.env(\.[^/]+)?$"), re.compile(r"\.(pem|p12|pfx|jks|keystore|p8)$"),
    re.compile(r"(^|/)id_(rsa|ed25519|ecdsa)$"), re.compile(r"(^|/)(google-services\.json|GoogleService-Info\.plist)$"),
)
# 예시·템플릿 파일은 비밀이 아니다 — 목록에서 뺀다
_SECRET_SAFE = re.compile(r"\.(example|sample|template|dist)$|(^|/)\.env\.(example|sample|template)$", re.I)
# 따옴표 안에 한글·CJK가 들어 있는 문자열 리터럴 (사용자 노출 문구 후보)
_NL_STRING = re.compile(r"""(["'`])(?:(?!\1)[^\n\\]|\\.)*[가-힣぀-ヿ一-鿿](?:(?!\1)[^\n\\]|\\.)*\1""")


def co_change(commits: list[list[str]], top: int = 10) -> dict:
    """커밋별 변경 파일 목록에서 함께 바뀐 파일 쌍을 센다. 커밋 단위 근사이며 PR 단위가 아니다."""
    sizes = sorted(len(c) for c in commits if c)
    pairs: Counter = Counter()
    for files in commits:
        # 대량 변경(포맷팅·초기 커밋)은 쌍을 부풀리므로 쌍 계산에서 제외한다
        if 2 <= len(files) <= 30:
            pairs.update(itertools.combinations(sorted(set(files)), 2))
    n = len(sizes)
    return {
        "commits": n,
        "median_files_per_commit": sizes[n // 2] if n else 0,
        "max_files_per_commit": sizes[-1] if n else 0,
        "top_pairs": [{"a": a, "b": b, "count": c} for (a, b), c in pairs.most_common(top) if c >= 2],
        "unit": "commit",
    }


def natural_language_strings(files: dict[str, str], top: int = 10) -> dict:
    """소스 파일별 한글·CJK 문자열 리터럴 수. 카탈로그 폴더 안의 파일은 세지 않는다."""
    per_file = {}
    for path, text in files.items():
        parts = set(Path(path).parts)
        if parts & _CATALOG_DIRS or Path(path).suffix not in _SOURCE_EXT:
            continue
        n = len(_NL_STRING.findall(text))
        if n:
            per_file[path] = n
    ranked = sorted(per_file.items(), key=lambda kv: kv[1], reverse=True)
    return {"total": sum(per_file.values()), "files_with_strings": len(per_file),
            "top_files": [{"path": k, "count": v} for k, v in ranked[:top]]}


def committed_secret_paths(tracked: list[str]) -> list[str]:
    """추적 중인 파일 중 비밀일 수 있는 경로. 예시 파일은 제외. 내용은 읽지 않는다."""
    return [t for t in tracked if any(p.search(t) for p in _SECRET_PATTERNS) and not _SECRET_SAFE.search(t)]


def dependency_names(manifests: dict[str, str]) -> dict:
    """매니페스트에서 선언된 의존성 이름만 뽑는다 (라이선스 조회는 에이전트가 배포물 기준으로)."""
    out: dict[str, list[str]] = {}
    for path, text in manifests.items():
        name = Path(path).name
        deps: list[str] = []
        if name == "package.json":
            try:
                data = json.loads(text)
            except ValueError:
                data = {}
            for key in ("dependencies", "devDependencies", "peerDependencies"):
                deps += [f"{d}" if key == "dependencies" else f"{d} ({key})" for d in (data.get(key) or {})]
        elif name.startswith("requirements") and name.endswith(".txt"):
            for line in text.splitlines():
                line = line.split("#", 1)[0].strip()
                m = re.match(r"([A-Za-z0-9_.\-]+)", line)
                if m and not line.startswith("-"):
                    deps.append(m.group(1))
        elif name == "pubspec.yaml":
            section = ""
            for line in text.splitlines():
                if re.match(r"^\S", line):
                    section = line.rstrip(":").strip()
                elif section in ("dependencies", "dev_dependencies"):
                    m = re.match(r"^  ([A-Za-z0-9_]+):", line)
                    if m and m.group(1) != "flutter":
                        deps.append(m.group(1) if section == "dependencies" else f"{m.group(1)} (dev)")
        elif name == "go.mod":
            deps += re.findall(r"^\s*([\w.\-]+/[\w./\-]+)\s+v", text, re.M)
        if deps:
            out[path] = deps
    return out


# 첫 화면으로 넘기는 줄 수. 에이전트가 원문을 직접 읽고 판단하되 전문을 싣지는 않는다(토큰).
TOP_LINES = 40


def analyze_readme(text: str | None) -> dict:
    """README를 에이전트가 읽기 좋게 줄인다. 판정은 하지 않는다.

    - `top`: 첫 화면 원문 — 가치 제안·데모·설치 위치는 이걸 읽고 판단한다
    - `headings`: 전체 구조 — 비교·벤치마크·"맞지 않는 경우" 절이 있는지는 이걸 보고 판단한다
    - 나머지는 세기만 한 측정값
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
        "top": "\n".join(lines[:TOP_LINES]),
        "headings": headings[:60],
        # URL 단위로 센다 — shields.io/badge/... 하나에 패턴 두 개가 걸려 두 번 세는 것을 막는다
        "badges": sum(1 for u in re.findall(r"https?://[^\s)\"'<>]+", text) if _BADGE.search(u)),
        "media": media[:30],
        "first_code_block_line": first_code,
        "translations_linked": sorted({m.group(1).lower() for m in _TRANSLATION.finditer(text)}),
        "non_english_ratio": round(foreign / (len(letters) or 1), 3),
    }


# 찾는 파일 → 흔히 두는 위치. GitHub은 .github/ → 루트 → docs/ 순으로 찾는다.
_HEALTH_FILES = {
    "license": ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"),
    "contributing": ("CONTRIBUTING.md",),
    "code_of_conduct": ("CODE_OF_CONDUCT.md",),
    "security": ("SECURITY.md",),
    "support": ("SUPPORT.md",),
    "changelog": ("CHANGELOG.md", "CHANGES.md", "HISTORY.md"),
    "governance": ("GOVERNANCE.md",),
    "roadmap": ("ROADMAP.md",),
    "architecture": ("ARCHITECTURE.md",),
    "agents_md": ("AGENTS.md", "CLAUDE.md"),
    "codeowners": ("CODEOWNERS",),
    "funding": ("FUNDING.yml",),
    "citation": ("CITATION.cff",),
    "pr_template": ("PULL_REQUEST_TEMPLATE.md", "pull_request_template.md"),
    "dependabot": ("dependabot.yml", "dependabot.yaml", "renovate.json", "renovate.json5"),
}


def detect_files(root: dict, github: dict, docs: dict, templates: list[str]) -> dict:
    """루트·.github·docs 목록(name → type)에서 건강 파일을 찾는다.

    "있다"와 "작동한다"를 구분한다 — LICENSE가 폴더면 GitHub이 인식하지 못한다(coursebook).
    GitHub community profile API는 yml 이슈 폼을 인식하지 못하므로 폴더를 직접 본다.
    """
    found: dict = {}
    for key, names in _HEALTH_FILES.items():
        hit = None
        for where, listing in ((".github", github), ("root", root), ("docs", docs)):
            for n in names:
                if n in listing:
                    hit = {"where": where, "name": n, "type": listing[n]}
                    break
            if hit:
                break
        found[key] = hit
    lic = found.get("license")
    if lic and lic["type"] != "file":
        lic["warning"] = "LICENSE가 파일이 아니라 GitHub이 라이선스를 인식하지 못한다"
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
    priv = None
    for where, listing in (("root", root), ("docs", docs), (".github", github)):
        for n, t in listing.items():
            if n.lower().startswith(("privacy", "privacy_policy", "개인정보")):
                priv = {"where": where, "name": n, "type": t}
                break
        if priv:
            break
    found["privacy_policy"] = priv
    found["store_metadata_root"] = "fastlane" in root
    found["mobile_dirs"] = sorted(d for d in ("android", "ios") if d in root)
    return found


def summarize_labels(names: list[str]) -> dict:
    """라벨 이름 전체와 개수만 준다. 체계가 좋은지는 에이전트가 이름을 보고 판단한다."""
    return {"count": len(names), "names": names[:150]}


# ── 네트워크 ─────────────────────────────────────────────────────────────

def _get(path: str, pat: str):
    from common.gh_client import _request
    return _request("GET", f"{_API}{path}", None, pat)


def _listing(owner: str, repo: str, sub: str, pat: str) -> dict:
    from common.gh_client import GitHubAPIError
    try:
        items = _get(f"/repos/{owner}/{repo}/contents/{sub}", pat)
    except GitHubAPIError as e:
        if e.status_code == 404:
            return {}
        raise
    if not isinstance(items, list):
        return {}
    return {it["name"]: it["type"] for it in items}


def _all_labels(owner: str, repo: str, pat: str) -> list[str]:
    names: list[str] = []
    for page in range(1, 6):
        items = _get(f"/repos/{owner}/{repo}/labels?per_page=100&page={page}", pat)
        names += [it["name"] for it in items]
        if len(items) < 100:
            break
    return names


def _pat(owner: str | None, repo: str | None) -> str | None:
    from common.config import get_github_pat
    return get_github_pat(owner, repo)


def _no_pat() -> int:
    return emit({"ok": False, "code": "no_pat",
                 "summary": "GitHub PAT가 없다",
                 "next": "/pro-github 로 PAT를 먼저 등록한다"})


def _split(slug: str) -> tuple[str, str] | None:
    parts = slug.strip().rstrip("/").split("/")
    if len(parts) != 2 or not all(parts):
        return None
    return parts[0], parts[1]


def cmd_collect(args) -> int:
    from common.gh_client import GitHubAPIError
    target = _split(args.target)
    if not target:
        return emit({"ok": False, "code": "bad_args", "summary": "OWNER/REPO 형식으로 넘긴다"})
    owner, repo = target
    pat = _pat(owner, repo)
    if not pat:
        return _no_pat()
    try:
        meta = _get(f"/repos/{owner}/{repo}", pat)
        root = _listing(owner, repo, "", pat)
        gh = _listing(owner, repo, ".github", pat)
        docs = _listing(owner, repo, "docs", pat)
        templates = list(_listing(owner, repo, ".github/ISSUE_TEMPLATE", pat))
        workflows = [n for n in _listing(owner, repo, ".github/workflows", pat)
                     if n.endswith((".yml", ".yaml"))]
        labels = _all_labels(owner, repo, pat)
        try:
            rd = _get(f"/repos/{owner}/{repo}/readme", pat)
            readme = base64.b64decode(rd.get("content", "")).decode("utf-8", "replace")
        except GitHubAPIError as e:
            if e.status_code != 404:
                raise
            readme = None
        releases = _get(f"/repos/{owner}/{repo}/releases?per_page=10", pat)
        issues = _get(f"/repos/{owner}/{repo}/issues?state=all&per_page=30", pat)
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"http_{e.status_code}", "summary": str(e),
                     "next": "401이면 PAT 만료, 404면 레포 이름이나 접근 권한을 확인한다"})

    only_issues = [i for i in issues if "pull_request" not in i]
    lic = meta.get("license") or {}
    data = {
        "repo": f"{owner}/{repo}",
        "meta": {
            "description": meta.get("description"),
            "homepage": meta.get("homepage") or None,
            "topics": meta.get("topics", []),
            "language": meta.get("language"),
            "license_spdx": lic.get("spdx_id"),
            "stars": meta.get("stargazers_count", 0),
            "forks": meta.get("forks_count", 0),
            "open_issues": meta.get("open_issues_count", 0),
            "created_at": meta.get("created_at"),
            "pushed_at": meta.get("pushed_at"),
            "archived": meta.get("archived", False),
            "fork": meta.get("fork", False),
            "private": meta.get("private", False),
            "has_discussions": meta.get("has_discussions", False),
            "has_pages": meta.get("has_pages", False),
            "has_wiki": meta.get("has_wiki", False),
            "default_branch": meta.get("default_branch"),
        },
        "files": detect_files(root, gh, docs, templates),
        "root_entries": sorted(root)[:80],
        "workflows": len(workflows),
        "labels": summarize_labels(labels),
        "readme": analyze_readme(readme),
        "releases": {
            "recent": len(releases),
            "latest": releases[0].get("tag_name") if releases else None,
            "latest_at": releases[0].get("published_at") if releases else None,
            "assets_on_latest": len(releases[0].get("assets", [])) if releases else 0,
        },
        # 이슈 관리 방식은 제목·라벨·작성자 관계를 보고 에이전트가 읽는다
        "issues_sample": [
            {"title": i.get("title", "")[:120], "state": i.get("state"),
             "labels": [lb["name"] for lb in i.get("labels", [])],
             "author": (i.get("user") or {}).get("login"),
             "author_association": i.get("author_association"),
             "comments": i.get("comments", 0)}
            for i in only_issues[:20]
        ],
    }
    return emit({"data": data,
                 "summary": f"{owner}/{repo} 사실 수집 완료",
                 "next": "references/rubric.md 로 성격 판별과 축별 채점을 한다"})


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout if r.returncode == 0 else ""


def cmd_local_facts(args) -> int:
    root = Path(args.path).resolve()
    if not (root / ".git").exists():
        return emit({"code": "not_a_git_repo", "summary": f"git 저장소가 아닙니다: {root}",
                     "next": "clone 한 경로를 넘기세요", "ok": False})
    tracked = [t for t in _git(root, "ls-files", "-z").split("\0") if t]
    # 커밋별 변경 파일 (최근 N개). 구분자는 NUL 로 파일명 공백에 안전하게
    raw = _git(root, "log", f"-{args.commits}", "--name-only", "--format=%x01", "--no-merges")
    commits = [[f for f in chunk.split("\n") if f.strip()] for chunk in raw.split("\x01")[1:]]
    sources: dict[str, str] = {}
    for t in tracked:
        if Path(t).suffix in _SOURCE_EXT:
            try:
                fp = root / t
                if fp.stat().st_size <= 300_000:
                    sources[t] = fp.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                pass
    manifest_names = ("package.json", "pubspec.yaml", "go.mod")
    manifests: dict[str, str] = {}
    for t in tracked:
        n = Path(t).name
        if "node_modules" in t.split("/"):
            continue
        if n in manifest_names or (n.startswith("requirements") and n.endswith(".txt")):
            try:
                manifests[t] = (root / t).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                pass
    catalog = sorted({p for t in tracked for p in Path(t).parts[:-1] if p in _CATALOG_DIRS})
    data = {
        "co_change": co_change(commits),
        "natural_language_strings": natural_language_strings(sources),
        "string_catalog_dirs": catalog,
        "dependency_manifests": dependency_names(manifests),
        "committed_secret_paths": committed_secret_paths(tracked),
        "tracked_files": len(tracked),
    }
    warn = " — 비밀일 수 있는 파일이 추적 중입니다. 다른 항목보다 먼저 알리세요" if data["committed_secret_paths"] else ""
    return emit({"data": data, "summary": f"추적 파일 {len(tracked)}개, 최근 커밋 {data['co_change']['commits']}개 분석{warn}",
                 "next": "references/contributor.md 로 변경 증폭·의존성 라이선스를 판단한다 (판정은 에이전트)"})


def cmd_list_repos(args) -> int:
    from common.gh_client import GitHubAPIError
    pat = _pat(args.owner, None)
    if not pat:
        return _no_pat()
    rows: list[dict] = []
    try:
        if args.owner:
            kind = _get(f"/users/{args.owner}", pat).get("type")
            base = f"/orgs/{args.owner}/repos" if kind == "Organization" else f"/users/{args.owner}/repos"
            query = "type=all"
        else:
            base, query = "/user/repos", "affiliation=owner,organization_member"
        for page in range(1, 11):
            items = _get(f"{base}?per_page=100&page={page}&{query}", pat)
            for r in items:
                rows.append({
                    "repo": r["full_name"], "private": r["private"], "fork": r["fork"],
                    "archived": r["archived"], "stars": r["stargazers_count"],
                    "language": r.get("language"), "pushed_at": r.get("pushed_at"),
                    "has_description": bool(r.get("description")),
                    "license_spdx": (r.get("license") or {}).get("spdx_id"),
                })
            if len(items) < 100:
                break
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"http_{e.status_code}", "summary": str(e)})
    if not args.include_all:
        rows = [r for r in rows if not (r["private"] or r["fork"] or r["archived"])]
    rows.sort(key=lambda r: r["stars"], reverse=True)
    return emit({"data": {"count": len(rows), "repos": rows},
                 "summary": f"레포 {len(rows)}개",
                 "next": "대상마다 collect OWNER/REPO 를 부른다"})


def cmd_get_output_path(args) -> int:
    # 경로 규칙은 common/paths.py가 단일 소유 — 여기서 재구현하지 않는다 (#525)
    from common.paths import resolve_output_path
    return emit(resolve_output_path(args.skill_id, args.title))


def build_parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(prog="oss_cli", description="oss-consult skill CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("collect", help="레포 하나의 오픈소스 준비 사실 수집")
    p.add_argument("target", help="OWNER/REPO")
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("local-facts", help="로컬 clone 의 변경 증폭·문구 하드코딩·의존성·추적 중인 비밀 파일 측정")
    p.add_argument("path", help="clone 한 저장소 경로")
    p.add_argument("--commits", type=int, default=200, help="분석할 최근 커밋 수")
    p.set_defaults(func=cmd_local_facts)

    p = sub.add_parser("list-repos", help="계정·조직의 레포 목록 (기본: 공개·비포크·비보관)")
    p.add_argument("owner", nargs="?", default=None, help="비우면 PAT 주인이 접근하는 전체")
    p.add_argument("--include-all", action="store_true", help="비공개·포크·보관 레포도 포함")
    p.set_defaults(func=cmd_list_repos)

    p = sub.add_parser("get-output-path", help="컨설팅 보고서 저장 경로")
    p.add_argument("skill_id", nargs="?", default="oss-consult")
    p.add_argument("--title")
    p.set_defaults(func=cmd_get_output_path)

    return parser


def main() -> int:
    return run_cli(build_parser())


if __name__ == "__main__":
    sys.exit(main())
