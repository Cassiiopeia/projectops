"""스킬 공식 트러블슈팅 지식: 항목 스키마·검증, 색인 생성, 실패에 맞는 해결 찾기 (#889).

사용자 기억(knowledge.json, 이 컴퓨터만)과 층이 다르다 — 관리자가 PR 로 넣고 플러그인 업데이트로 모두에게 간다.
  skills/<skill>/troubleshooting/<area>/<id>.json   한 항목 = 한 파일 (원본)
  skills/<skill>/troubleshooting/index.json         색인 (생성물, scripts/build_troubleshooting.py)
실행 중에는 색인만 읽는다. 색인이 없거나 깨져도 예외 없이 빈 결과 — 본 명령을 망치지 않는다.
작성 규칙: skills/references/memory-principles.md §6

표준 라이브러리만 쓴다 (mac·Windows·폐쇄망 공통).
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from common import memory

TROUBLESHOOTING_DIR = "troubleshooting"
INDEX_FILE = "index.json"
INDEX_SCHEMA = 1
AREAS = ("web", "android", "ios", "server", "ssh", "general", "desktop")

# 항목 필드: 이름 → 허용 타입
REQUIRED_FIELDS = {"id": str, "area": str, "title": str, "match": dict, "symptom": str,
                   "cause": str, "fix": list, "refs": list, "verified_at": str}
OPTIONAL_FIELDS = {"applies_to": (str, list), "see_also": list}
MATCH_FIELDS = ("codes", "keywords")

ID_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
MAX_TITLE_CHARS = 80
MAX_FIX_ITEM_CHARS = 200
MAX_FIX_ITEMS = 8

# 응답에 싣는 요약 상한 — 지식이 늘어도 토큰은 늘지 않게
DEFAULT_FIND_LIMIT = 2
SHORT_FIX_ITEMS = 2
SHORT_FIX_ITEM_CHARS = 160
SHORT_TITLE_CHARS = 80
# 핵심어만 겹친 항목이 실리려면 필요한 겹침 수 (항목 핵심어가 이보다 적으면 그 수)
MIN_KEYWORD_HITS = 2


def troubleshooting_dir(skill_dir: Path) -> Path:
    return Path(skill_dir) / TROUBLESHOOTING_DIR


def index_path(skill_dir: Path) -> Path:
    return troubleshooting_dir(skill_dir) / INDEX_FILE


def entry_files(skill_dir: Path) -> list[Path]:
    """원본 항목 파일 (troubleshooting/<area>/*.json). 색인 파일은 영역 폴더 밖이라 빠진다."""
    base = troubleshooting_dir(skill_dir)
    if not base.is_dir():
        return []
    return sorted(p for p in base.glob("*/*.json") if p.is_file())


def keyword_tokens(keywords: list) -> set[str]:
    """핵심어 → 비교용 고유어 (common.memory 단어 규칙 재사용)."""
    tokens: set[str] = set()
    for keyword in keywords or []:
        tokens |= memory.words(str(keyword))
    return tokens


# ── 검증 ────────────────────────────────────────────────────────────────

def _is_valid_date(value: str) -> bool:
    try:
        dt.date.fromisoformat(value)
        return len(value) == 10
    except (TypeError, ValueError):
        return False


def _validate_match(match: dict) -> list[str]:
    problems = []
    for field in MATCH_FIELDS:
        values = match.get(field, [])
        if not isinstance(values, list) or not all(isinstance(v, str) and v.strip() for v in values):
            problems.append(f"match.{field} must be a list of non-empty strings")
    codes = match.get("codes") if isinstance(match.get("codes"), list) else []
    keywords = match.get("keywords") if isinstance(match.get("keywords"), list) else []
    bad_codes = [c for c in codes if isinstance(c, str) and not CODE_PATTERN.match(c)]
    if bad_codes:
        problems.append(f"match.codes not in lower_snake form: {bad_codes}")
    if not codes and not keyword_tokens(keywords):
        problems.append("match needs at least one of codes or keywords to be found")
    return problems


def validate_entry(entry: dict) -> list[str]:
    """항목 하나의 스키마 문제 목록 (없으면 빈 목록). 파일 위치·중복은 validate_entries 가 본다."""
    if not isinstance(entry, dict):
        return ["an entry must be a JSON object"]
    problems = []
    # 필드 존재·타입
    for field, kind in REQUIRED_FIELDS.items():
        if field not in entry:
            problems.append(f"missing required field: {field}")
        elif not isinstance(entry[field], kind):
            problems.append(f"{field} must be of type {kind.__name__}")
    for field, kind in OPTIONAL_FIELDS.items():
        if field in entry and not isinstance(entry[field], kind):
            problems.append(f"{field} has the wrong type")
    unknown = set(entry) - set(REQUIRED_FIELDS) - set(OPTIONAL_FIELDS)
    if unknown:
        problems.append(f"unknown fields: {sorted(unknown)}")
    if problems:
        return problems
    # 값 규칙 (id·area·제목·날짜·해결·이슈 번호)
    if not ID_PATTERN.match(entry["id"]):
        problems.append("id must be kebab-case (lowercase letters, digits, hyphens)")
    if entry["area"] not in AREAS:
        problems.append(f"area must be one of {'/'.join(AREAS)}")
    for field in ("title", "symptom", "cause"):
        if not entry[field].strip():
            problems.append(f"{field} is empty")
    if len(entry["title"]) > MAX_TITLE_CHARS:
        problems.append(f"title must be at most {MAX_TITLE_CHARS} characters")
    if not _is_valid_date(entry["verified_at"]):
        problems.append("verified_at must be YYYY-MM-DD")
    fix = entry["fix"]
    if not fix or len(fix) > MAX_FIX_ITEMS:
        problems.append(f"fix must have 1 to {MAX_FIX_ITEMS} items")
    if not all(isinstance(f, str) and f.strip() and len(f) <= MAX_FIX_ITEM_CHARS for f in fix):
        problems.append(f"each fix item must be a non-empty string of at most {MAX_FIX_ITEM_CHARS} characters")
    if not all(isinstance(r, int) and not isinstance(r, bool) and r > 0 for r in entry["refs"]):
        problems.append("refs must be a list of issue numbers (positive integers)")
    problems += _validate_match(entry["match"])
    return problems


def read_entries(skill_dir: Path) -> tuple[list[tuple[Path, dict]], list[str]]:
    """([(파일, 항목)], 읽기 문제). JSON 이 깨진 파일은 문제로만 남긴다."""
    rows, problems = [], []
    for path in entry_files(skill_dir):
        try:
            rows.append((path, json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError) as error:
            problems.append(f"{path.name}: could not read JSON ({error})")
    return rows, problems


def validate_entries(skill_dir: Path) -> list[str]:
    """모든 항목 검사: 스키마 > 파일명·폴더 일치 > id 유일 > 비밀값. 문제 목록을 돌려준다."""
    from common.access import find_secrets

    rows, problems = read_entries(skill_dir)
    seen_ids: dict[str, str] = {}
    for path, entry in rows:
        label = f"{path.parent.name}/{path.name}"
        found = validate_entry(entry)
        problems += [f"{label}: {p}" for p in found]
        if found:
            continue
        if entry["id"] != path.stem:
            problems.append(f"{label}: id ({entry['id']}) does not match the file name")
        if entry["area"] != path.parent.name:
            problems.append(f"{label}: area ({entry['area']}) does not match the folder")
        if entry["id"] in seen_ids:
            problems.append(f"{label}: duplicate id ({seen_ids[entry['id']]})")
        seen_ids[entry["id"]] = label
        secrets = find_secrets(json.dumps(entry, ensure_ascii=False))
        if secrets:
            problems.append(f"{label}: looks like a secret {secrets}")
    return problems


# ── 색인 ────────────────────────────────────────────────────────────────

def short_fix(fix: list) -> list[str]:
    return [memory.clip(f, SHORT_FIX_ITEM_CHARS) for f in (fix or [])[:SHORT_FIX_ITEMS]]


def build_index(skill_dir: Path) -> dict:
    """항목 파일 > 색인 {codes:{code:[id]}, keywords:{word:[id]}, entries:{id:{...}}}.

    날짜 같은 실행마다 바뀌는 값은 넣지 않는다 — 같은 항목이면 같은 색인이어야 --check 가 선다.
    """
    rows, _ = read_entries(skill_dir)
    codes: dict[str, set] = {}
    keywords: dict[str, set] = {}
    entries: dict[str, dict] = {}
    base = troubleshooting_dir(skill_dir)
    for path, entry in rows:
        if validate_entry(entry):
            continue
        entry_id = entry["id"]
        match = entry["match"]
        for code in match.get("codes", []):
            codes.setdefault(code, set()).add(entry_id)
        tokens = keyword_tokens(match.get("keywords", []))
        for token in tokens:
            keywords.setdefault(token, set()).add(entry_id)
        entries[entry_id] = {"area": entry["area"], "title": entry["title"],
                             "fix_short": short_fix(entry["fix"]), "keyword_count": len(tokens),
                             "path": path.relative_to(base).as_posix()}
    return {"schema": INDEX_SCHEMA,
            "codes": {k: sorted(v) for k, v in sorted(codes.items())},
            "keywords": {k: sorted(v) for k, v in sorted(keywords.items())},
            "entries": dict(sorted(entries.items()))}


def render_index(index: dict) -> str:
    return json.dumps(index, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def _empty_index() -> dict:
    return {"schema": INDEX_SCHEMA, "codes": {}, "keywords": {}, "entries": {}}


def load_index(skill_dir: Path) -> dict:
    """생성된 색인. 없거나 모양이 틀리면 빈 색인 (예외 없음)."""
    try:
        data = json.loads(index_path(skill_dir).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return _empty_index()
    if not isinstance(data, dict) or not all(isinstance(data.get(k), dict)
                                             for k in ("codes", "keywords", "entries")):
        return _empty_index()
    return data


# ── 찾기 ────────────────────────────────────────────────────────────────

def _summary(entry_id: str, info: dict) -> dict:
    return {"id": entry_id, "title": memory.clip(info.get("title", ""), SHORT_TITLE_CHARS),
            "fix": [memory.clip(f, SHORT_FIX_ITEM_CHARS) for f in (info.get("fix_short") or [])
                    if isinstance(f, str)][:SHORT_FIX_ITEMS]}


def find_known_fixes(skill_dir: Path, code: str | None = None, text: str | None = None,
                     limit: int = DEFAULT_FIND_LIMIT, areas=None) -> list[dict]:
    """실패 코드·문구에 맞는 항목 요약 (최대 limit 건). 코드 정확 일치 > 핵심어 겹침 순.

    areas: 이 영역들 + general 만 (iOS 실패에 android 항목이 실리지 않게). None 이면 거르지 않는다.
    어떤 오류도 밖으로 내지 않는다 — 공식 지식은 보조다.
    """
    try:
        index = load_index(skill_dir)
        entries = index["entries"]
        code_hits = set(index["codes"].get(code) or []) if code else set()
        keyword_hits: dict[str, int] = {}
        for token in memory.words(text or ""):
            for entry_id in index["keywords"].get(token) or []:
                keyword_hits[entry_id] = keyword_hits.get(entry_id, 0) + 1

        # 핵심어만 맞은 항목은 충분히 겹칠 때만 (흔한 한 단어로 엉뚱한 항목이 실리지 않게)
        def is_keyword_match(entry_id: str) -> bool:
            info = entries.get(entry_id) or {}
            need = min(MIN_KEYWORD_HITS, int(info.get("keyword_count") or MIN_KEYWORD_HITS))
            return keyword_hits.get(entry_id, 0) >= max(need, 1)

        candidates = code_hits | {i for i in keyword_hits if is_keyword_match(i)}
        if areas:
            allowed_areas = {*areas, "general"}
            candidates = {i for i in candidates if (entries.get(i) or {}).get("area") in allowed_areas}
        ranked = sorted((i for i in candidates if i in entries),
                        key=lambda i: (i not in code_hits, -keyword_hits.get(i, 0), i))
        return [_summary(i, entries[i]) for i in ranked[:max(limit, 0)]]
    except Exception:   # noqa: BLE001 — 색인이 손으로 망가져도 본 명령은 그대로
        return []


def load_entry(skill_dir: Path, entry_id: str) -> dict | None:
    """항목 전체. 색인의 경로를 먼저 보고, 없으면 영역 폴더를 훑는다 (색인이 낡았어도 찾게)."""
    if not entry_id or not ID_PATTERN.match(entry_id):
        return None
    base = troubleshooting_dir(skill_dir)
    info = load_index(skill_dir)["entries"].get(entry_id) or {}
    candidates = [base / info["path"]] if isinstance(info.get("path"), str) else []
    candidates += sorted(base.glob(f"*/{entry_id}.json")) if base.is_dir() else []
    for path in candidates:
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(entry, dict) and entry.get("id") == entry_id:
            return entry
    return None


def list_entries(skill_dir: Path, area: str | None = None) -> list[dict]:
    """색인의 항목 목록 [{id, area, title}] — area 로 거른다."""
    entries = load_index(skill_dir)["entries"]
    return [{"id": i, "area": info.get("area"), "title": info.get("title")}
            for i, info in entries.items()
            if isinstance(info, dict) and (area is None or info.get("area") == area)]
