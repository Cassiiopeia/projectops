#!/usr/bin/env python3
"""changelog provider 공통 헬퍼 (#455) — stdlib 전용.

모든 provider는 같은 계약을 따른다:
  입력: 환경변수 (COMMIT_RANGE 등)
  출력: 성공 시 cwd에 pr_body.md(Summary by CodeRabbit 고정 구조) + stdout `PROVIDER=<name>` + exit 0
        실패 시 stderr 사유 + exit 1 (ladder가 다음 단계로 폴백)
"""
import re
import subprocess
import sys

HEADER = "<!-- This is an auto-generated comment: release notes by coderabbit.ai -->"
FOOTER = "<!-- end of auto-generated comment: release notes by coderabbit.ai -->"

# 커밋 제목 prefix → 릴리스 노트 섹션
SECTION_ORDER = [
    ("feat", "새 기능"),
    ("fix", "버그 수정"),
    ("improve", "개선"),
    ("docs", "문서"),
    ("etc", "기타"),
]
# 커밋 제목에서 타입을 뽑는 규칙 — 두 컨벤션을 모두 인식한다 (#566).
#   tier-1: "제목 : feat : 내용"        ← projectops 표준 (타입이 중간에 온다)
#   tier-2: "feat: 내용"                ← Conventional Commits
# tier-1을 먼저 본다. tier-2 정규식은 줄 맨 앞만 보므로 tier-1을 통째로 놓쳤고,
# 그 결과 자체 컨벤션을 지킨 커밋이 전부 "기타"로 떨어졌다.
# 판정 규칙은 changelog_manager.classify_bump_level()(#546)과 같은 기준을 쓴다.
_TYPES = "feat|fix|refactor|docs|chore|style|test|perf|ci|build|revert"
_TIER1_RE = re.compile(rf"^(?P<title>.+?)\s:\s*(?P<type>{_TYPES})!?\s*:\s*(?P<body>.+)$")
_TIER2_RE = re.compile(rf"^(?P<type>{_TYPES})(?:\([^)]*\))?!?:\s*(?P<body>.+)$")
_PREFIX_TO_SECTION = {
    "feat": "feat", "fix": "fix",
    "refactor": "improve", "style": "improve", "perf": "improve",
    "docs": "docs",
}


def parse_commit(line):
    """커밋 제목 → (섹션key, 사용자에게 보여줄 내용). 매치 실패 시 ("etc", 원문)."""
    m = _TIER1_RE.match(line) or _TIER2_RE.match(line)
    if not m:
        return "etc", _strip_noise(line) or line.strip()
    section = _PREFIX_TO_SECTION.get(m.group("type"), "etc")
    return section, (_strip_noise(m.group("body")) or line.strip())


def _strip_noise(text):
    """이슈번호(#123)·URL 제거 후 공백 정리 — 사용자에게 의미 없는 토큰."""
    s = re.sub(r"https?://\S+", "", text)
    s = re.sub(r"#[0-9]+", "", s)
    return re.sub(r" {2,}", " ", s).strip()


def collect_commits(range_expr, limit=60, fallback_count=30):
    """지정 range의 커밋 제목 수집([skip ci] 제외). 비면 최근 커밋으로 폴백."""
    def _log(args):
        try:
            out = subprocess.run(
                ["git", "log", *args, "--pretty=format:%s"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if out.returncode != 0:
                return []
            return [s for s in out.stdout.splitlines() if s.strip() and "[skip ci]" not in s]
        except OSError:
            return []

    commits = _log([range_expr])[:limit]
    if not commits:
        commits = _log([f"-{fallback_count}"])
    return commits


def clean_message(line):
    """커밋 제목에서 타입 prefix·이슈번호·URL을 걷어낸 본문만 반환."""
    return parse_commit(line)[1]


def classify(commits):
    """커밋 제목들을 섹션별로 분류해 {섹션key: [메시지…]} 반환."""
    sections = {key: [] for key, _ in SECTION_ORDER}
    for line in commits:
        key, message = parse_commit(line)
        sections[key].append(message)
    return sections


def sections_to_markdown(sections):
    parts = []
    for key, title in SECTION_ORDER:
        items = sections.get(key) or []
        if not items:
            continue
        parts.append(f"* **{title}**")
        parts.extend(f"  * {msg}" for msg in items)
        parts.append("")
    return "\n".join(parts).rstrip("\n")


def write_pr_body(content, path="pr_body.md"):
    """Summary by CodeRabbit 고정 구조로 감싸 pr_body.md 저장 — changelog_manager.py 파싱 계약."""
    body = "\n".join([
        HEADER, "",
        "## Summary by CodeRabbit", "",
        "## 릴리스 노트", "",
        content, "",
        FOOTER, "",
    ])
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)


def fail(reason):
    print(reason, file=sys.stderr)
    sys.exit(1)
