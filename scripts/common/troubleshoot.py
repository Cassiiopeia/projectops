"""Official skill troubleshooting knowledge: entry schema and validation, index build, finding fixes for a failure (#889).

A different layer from user memory (knowledge.json, this machine only): maintainers add entries via PR and plugin updates deliver them to everyone.
  skills/<skill>/troubleshooting/<area>/<id>.json   one entry = one file (source)
  skills/<skill>/troubleshooting/index.json         index (generated, scripts/build_troubleshooting.py)
At runtime only the index is read. A missing or broken index gives an empty result without raising; the main command is never broken.
Writing rules: skills/references/memory-principles.md §6

Standard library only (mac, Windows, air-gapped networks).
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

# Entry fields: name → allowed type
REQUIRED_FIELDS = {"id": str, "area": str, "title": str, "match": dict, "symptom": str,
                   "cause": str, "fix": list, "refs": list, "verified_at": str}
OPTIONAL_FIELDS = {"applies_to": (str, list), "see_also": list}
MATCH_FIELDS = ("codes", "keywords")

ID_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
MAX_TITLE_CHARS = 80
MAX_FIX_ITEM_CHARS = 200
MAX_FIX_ITEMS = 8

# Cap on summaries added to a response, so tokens do not grow as knowledge grows
DEFAULT_FIND_LIMIT = 2
SHORT_FIX_ITEMS = 2
SHORT_FIX_ITEM_CHARS = 160
SHORT_TITLE_CHARS = 80
# Overlap count needed to include a keyword-only match (or the entry's keyword count if smaller)
MIN_KEYWORD_HITS = 2


def troubleshooting_dir(skill_dir: Path) -> Path:
    return Path(skill_dir) / TROUBLESHOOTING_DIR


def index_path(skill_dir: Path) -> Path:
    return troubleshooting_dir(skill_dir) / INDEX_FILE


def entry_files(skill_dir: Path) -> list[Path]:
    """Source entry files (troubleshooting/<area>/*.json). The index file is outside area folders, so it is excluded."""
    base = troubleshooting_dir(skill_dir)
    if not base.is_dir():
        return []
    return sorted(p for p in base.glob("*/*.json") if p.is_file())


def keyword_tokens(keywords: list) -> set[str]:
    """Keywords → distinct words for comparison (reuses common.memory word rules)."""
    tokens: set[str] = set()
    for keyword in keywords or []:
        tokens |= memory.words(str(keyword))
    return tokens


# ── Validation ──────────────────────────────────────────────────────────

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
    """Schema problems for one entry (empty list if none). File location and duplicates are checked by validate_entries."""
    if not isinstance(entry, dict):
        return ["an entry must be a JSON object"]
    problems = []
    # Field presence and type
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
    # Value rules (id, area, title, date, fix, issue number)
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
    """([(file, entry)], read problems). Files with broken JSON are only recorded as problems."""
    rows, problems = [], []
    for path in entry_files(skill_dir):
        try:
            rows.append((path, json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError) as error:
            problems.append(f"{path.name}: could not read JSON ({error})")
    return rows, problems


def validate_entries(skill_dir: Path) -> list[str]:
    """Check all entries: schema > file name/folder match > unique id > secrets. Returns the list of problems."""
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


# ── Index ───────────────────────────────────────────────────────────────

def short_fix(fix: list) -> list[str]:
    return [memory.clip(f, SHORT_FIX_ITEM_CHARS) for f in (fix or [])[:SHORT_FIX_ITEMS]]


def build_index(skill_dir: Path) -> dict:
    """Entry files > index {codes:{code:[id]}, keywords:{word:[id]}, entries:{id:{...}}}.

    Values that change per run, like dates, are left out; the same entries must give the same index for --check to hold.
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
    """The generated index. Empty index if missing or malformed (no exception)."""
    try:
        data = json.loads(index_path(skill_dir).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return _empty_index()
    if not isinstance(data, dict) or not all(isinstance(data.get(k), dict)
                                             for k in ("codes", "keywords", "entries")):
        return _empty_index()
    return data


# ── Find ────────────────────────────────────────────────────────────────

def _summary(entry_id: str, info: dict) -> dict:
    return {"id": entry_id, "title": memory.clip(info.get("title", ""), SHORT_TITLE_CHARS),
            "fix": [memory.clip(f, SHORT_FIX_ITEM_CHARS) for f in (info.get("fix_short") or [])
                    if isinstance(f, str)][:SHORT_FIX_ITEMS]}


def find_known_fixes(skill_dir: Path, code: str | None = None, text: str | None = None,
                     limit: int = DEFAULT_FIND_LIMIT, areas=None) -> list[dict]:
    """Summaries of entries matching a failure code or message (at most limit). Exact code match > keyword overlap.

    areas: only these areas + general (so android entries do not show for iOS failures). None means no filtering.
    Never lets any error escape; official knowledge is auxiliary.
    """
    try:
        index = load_index(skill_dir)
        entries = index["entries"]
        code_hits = set(index["codes"].get(code) or []) if code else set()
        keyword_hits: dict[str, int] = {}
        for token in memory.words(text or ""):
            for entry_id in index["keywords"].get(token) or []:
                keyword_hits[entry_id] = keyword_hits.get(entry_id, 0) + 1

        # Keyword-only matches only when they overlap enough (so one common word does not pull in unrelated entries)
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
    except Exception:   # noqa: BLE001 — the main command proceeds even if the index is hand-broken
        return []


def load_entry(skill_dir: Path, entry_id: str) -> dict | None:
    """The full entry. Check the index path first, else scan area folders (finds it even if the index is stale)."""
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
    """Index entry list [{id, area, title}], filtered by area."""
    entries = load_index(skill_dir)["entries"]
    return [{"id": i, "area": info.get("area"), "title": info.get("title")}
            for i, info in entries.items()
            if isinstance(info, dict) and (area is None or info.get("area") == area)]
