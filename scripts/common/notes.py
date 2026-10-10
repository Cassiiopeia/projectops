"""pro-note 기록 검색 공유 로직 (#840).

note_cli 의 search · get-output-path(related) 와, 실패를 보여 주는 CLI(github_cli actions,
changelog_cli actions, launch logs)가 같은 검색을 쓴다. 원칙: skills/references/memory-principles.md

 - 기록이 없거나 읽기에 실패하면 빈 목록이다. 예외를 밖으로 내지 않는다 — 기억은 보조다.
 - 실패 응답에 싣는 양에는 상한이 있다(2건, 요약 200자). 근거 없는 것(핵심어 1개가 흔한 말)은 싣지 않는다.

표준 라이브러리만 쓴다.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from common.memory import clip

KINDS = ("case", "fact")
HIT_LIMIT = 2          # 실패 응답에 싣는 기록 수 상한
SUMMARY_MAX = 200      # 항목당 요약 길이 상한
_SPLIT = re.compile(r"[\s,./:;_\-\[\]()]+")
_TOKEN = re.compile(r"[0-9A-Za-z가-힣_.#:-]{3,}")
# 실패 로그에 늘 나오는 말 — 이것만 겹쳐서는 같은 문제가 아니다
_COMMON = {
    "error", "errors", "failed", "failure", "exception", "warning", "exit", "code", "line", "the", "and",
    "for", "with", "not", "found", "run", "step", "job", "build", "process", "completed", "null", "true",
    "false", "info", "debug", "at", "in", "of", "to", "from", "file", "path", "command", "failed:",
    "github", "actions", "workflow", "npm", "pip", "python", "node", "bash", "shell",
}
_NOISE = re.compile(r"^[0-9a-f:.\-tz]+$")   # 타임스탬프·해시 조각


def _git_root() -> Path | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                             timeout=10, encoding="utf-8", errors="replace")
        return Path(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None
    except Exception:
        return None


def home_root() -> Path:
    """홈 기록 루트. PROJECTOPS_HOME 을 따라 테스트가 실제 홈을 건드리지 않는다."""
    try:
        from common.state import base_dir
        return base_dir() / "note"
    except Exception:
        return Path.home() / ".projectops" / "note"


def project_note_root(project_root: Path) -> Path:
    """저장소 안 기록 루트. 산출물 루트 설정(output.root)을 따른다."""
    try:
        from common.paths import resolve_output_root
        return Path(resolve_output_root(project_root)) / "note"
    except Exception:
        return project_root / "docs" / "projectops" / "note"


def note_roots(project_root: Path | None = None, home: Path | None = None) -> list[tuple[str, Path]]:
    """검색 대상 루트 (scope, path). project_root 가 None 이면 홈만."""
    roots: list[tuple[str, Path]] = []
    if project_root:
        roots.append(("project", project_note_root(project_root)))
    roots.append(("home", home if home is not None else home_root()))
    return roots


def tokenize(query: str) -> list[str]:
    """검색어를 토큰으로 쪼갠다. 2글자 미만은 잡음이라 버린다."""
    return [p for p in _SPLIT.split((query or "").lower()) if len(p) >= 2]


def iter_notes(root: Path):
    for kind in KINDS:
        d = root / f"{kind}s"
        if not d.exists():
            continue
        for f in sorted(d.glob("*.md"), reverse=True):
            yield kind, f


def _count(text: str, tokens: list[str]) -> int:
    low = text.lower()
    return sum(1 for t in tokens if t in low)


def _title(text: str, fallback: str) -> str:
    return next((l.lstrip("# ").strip() for l in text.split("\n") if l.startswith("# ")), fallback)


def _summary(text: str) -> str:
    """제목 다음의 첫 본문 줄 하나(200자). 머리말·제목·구분선은 건너뛴다."""
    lines = text.split("\n")
    i = 0
    if lines and lines[0].strip() == "---":     # 머리말 블록
        for j in range(1, len(lines)):
            if lines[j].strip() == "---":
                i = j + 1
                break
    for l in lines[i:]:
        s = l.strip().lstrip("-*> ").strip()
        if s and not s.startswith(("#", "---", "|")):
            return clip(s, SUMMARY_MAX)
    return ""


def scan(tokens: list[str], roots: list[tuple[str, Path]], min_matched: int = 1,
         specific: set[str] | None = None) -> list[dict]:
    """토큰이 든 기록을 점수순으로. 제목(파일명) 일치는 본문보다 3배 센다.

    min_matched 미만으로 맞은 기록은 버리되, specific(오류 코드 같은 고유 토큰)이 맞으면 통과한다.
    """
    hits = []
    for scope, root in roots:
        try:
            for kind, path in iter_notes(root):
                try:
                    text = path.read_text(encoding="utf-8")
                except Exception:
                    continue
                matched = _count(text, tokens)
                s = _count(path.stem, tokens) * 3 + matched
                if s <= 0:
                    continue
                if matched < min_matched and not (specific and any(t in text.lower() for t in specific)):
                    continue
                hits.append({"scope": scope, "kind": kind, "title": _title(text, path.stem),
                             "path": str(path), "score": s, "summary": _summary(text)})
        except Exception:
            continue
    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits


def related(title: str, roots: list[tuple[str, Path]], limit: int = 3) -> list[dict]:
    """저장하려는 제목과 비슷한 기존 기록 상위 N건 (점수 포함). 저장은 막지 않는다 — 합칠지는 agent 판단.

    토큰이 둘 이상이면 2개 이상 겹쳐야 한다 (한 단어만 겹쳐서 '비슷하다'고 하면 소음이다).
    """
    try:
        tokens = tokenize(title)
        if not tokens:
            return []
        hits = scan(tokens, roots, min_matched=min(2, len(tokens)))
        return [{k: h[k] for k in ("scope", "kind", "title", "path", "score")} for h in hits[:limit]]
    except Exception:
        return []


def keywords(text: str, limit: int = 6) -> tuple[list[str], set[str]]:
    """오류 텍스트의 핵심어와 그중 고유한 것(오류 코드·긴 식별자).

    흔한 말·타임스탬프는 뺀다. 숫자와 글자가 섞인 코드(ITMS-90062, E1234)를 먼저 둔다.
    """
    seen: dict[str, int] = {}
    for w in _TOKEN.findall(text or ""):
        w = w.lower().strip(".:-#")
        if len(w) < 3 or w in _COMMON or _NOISE.match(w) or w.isdigit():
            continue
        seen[w] = seen.get(w, 0) + 1
    spec = {w for w in seen if re.search(r"\d", w) and re.search(r"[a-z]", w) and len(w) >= 5}
    spec |= {w for w in seen if len(w) >= 12}
    ordered = sorted(seen, key=lambda w: (w not in spec, -seen[w], -len(w)))
    return ordered[:limit], spec


def note_hits(error_text: str, project_root: Path | None = None, roots=None,
              limit: int = HIT_LIMIT) -> list[dict]:
    """오류 텍스트에 맞는 기록 최대 limit 건 [{title, path, summary, scope}]. 없으면 [].

    핵심어가 둘 이상 맞거나 고유 코드가 맞을 때만 싣는다 — 흔한 말 하나로 엉뚱한 기록을 싣지 않는다.
    roots 를 주지 않으면 현재 저장소(git)와 홈을 본다. 어떤 실패도 예외로 내지 않는다.
    """
    try:
        words, spec = keywords(error_text)
        if not words:
            return []
        if roots is None:
            roots = note_roots(project_root or _git_root())
        hits = scan(words, roots, min_matched=2, specific=spec)
        return [{"title": h["title"], "path": h["path"], "summary": h["summary"], "scope": h["scope"]}
                for h in hits[:limit]]
    except Exception:
        return []


def attach_note_hits(data: dict, error_text: str, **kw) -> dict:
    """data 에 note_hits 를 (있을 때만) 붙이고 data 를 돌려준다. 선택 필드라 기존 응답 계약은 그대로다."""
    hits = note_hits(error_text, **kw)
    if hits:
        data["note_hits"] = hits
    return data


def failed_run_text(run: dict) -> str:
    """get_run 결과에서 실패한 job·step 이름을 한 문자열로 — 기록 검색용 핵심어 재료."""
    parts = []
    for j in run.get("jobs", []):
        if j.get("conclusion") == "failure":
            parts.append(str(j.get("name") or ""))
            parts.extend(j.get("failed_steps") or [])
    return " ".join(parts)
