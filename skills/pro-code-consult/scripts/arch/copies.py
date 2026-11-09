"""copies: 고치기 전 사본 전수 조사 — 같은 이름·같은 값·같은 파일 내용을 플랫폼 폴더까지 (코딩 규칙 §9.1)

위치 종류 7개: code, native, web, asset, docs, config, test. 생성 파일과 제외 폴더만 뺀다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .assets import ASSET_EXTENSIONS, file_sha256, normalized_asset_name
from .origins import is_test_path
from .source_files import MAXIMUM_SOURCE_BYTES, is_generated_file, tracked_files, write_outside_repo

LOCATION_KINDS = ("code", "native", "web", "config", "docs", "asset", "test")
NATIVE_DIRECTORY_NAMES = {"android", "ios", "macos", "windows", "linux"}
NATIVE_EXTENSIONS = {".swift", ".m", ".mm", ".kt", ".kts", ".gradle", ".plist", ".xcconfig", ".pbxproj", ".storyboard"}
WEB_DIRECTORY_NAMES = {"web", "public", "static", "templates", "wwwroot"}
WEB_EXTENSIONS = {".html", ".htm", ".css", ".scss"}
DOCS_EXTENSIONS = {".md", ".mdx", ".txt", ".rst", ".adoc"}
CONFIG_EXTENSIONS = {".json", ".yml", ".yaml", ".toml", ".properties", ".ini", ".xml", ".env", ".cfg", ".arb"}
# 스토어 메타데이터 폴더 (fastlane 문구·스크린샷)
STORE_DIRECTORY_NAMES = {"fastlane", "metadata"}
# 종류별 표본 줄 길이 (긴 줄은 잘라 토큰 절약)
MAXIMUM_LINE_CHARACTERS = 160


def find_copies(root: Path, names: list, values: list, files: list, limit: int, out: str | None) -> dict:
    tracked = [r for r in tracked_files(root) if not is_generated_file(r)]
    searches = ([("name", n, _name_pattern(n)) for n in names]
                + [("value", v, re.compile(re.escape(v))) for v in values])
    results = [_search_text(root, tracked, kind, term, pattern) for kind, term, pattern in searches]
    results += [_search_file(root, tracked, relative) for relative in files]
    full = {"terms": results}
    written = write_outside_repo(root, out, full) if out else None
    if written and written.get("ok") is False:
        return written
    shown = [_trim(result, limit) for result in results]
    summary = "; ".join(f"{r['term']}: not found" if r.get("code") == "file_not_found"
                        else f"{r['term']}: {r['total']} in {len(r['by_kind'])} kind(s)" for r in results)
    return {"terms": shown, "out": written, "summary": summary,
            "next": ("Cite these copies in proposal step 1; fix every kind or say why a kind stays out of scope. "
                     "List what remains as 'remaining copies' at the end (references/refactor.md)")}


def _name_pattern(name: str):
    """식별자 경계 기준 (getUser 가 getUserName 에 걸리지 않게)"""
    return re.compile(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])")


def location_kind(relative: str) -> str:
    parts = relative.split("/")
    directories, extension = set(parts[:-1]), Path(relative).suffix.lower()
    if is_test_path(relative):
        return "test"
    if extension in ASSET_EXTENSIONS:
        return "asset"
    if directories & NATIVE_DIRECTORY_NAMES or extension in NATIVE_EXTENSIONS:
        return "native"
    if directories & STORE_DIRECTORY_NAMES or parts[0] == "docs" or extension in DOCS_EXTENSIONS:
        return "docs"
    if directories & WEB_DIRECTORY_NAMES or extension in WEB_EXTENSIONS:
        return "web"
    if extension in CONFIG_EXTENSIONS or parts[-1].startswith(".env"):
        return "config"
    return "code"


def _search_text(root: Path, tracked: list, kind: str, term: str, pattern) -> dict:
    matches = []
    for relative in tracked:
        if Path(relative).suffix.lower() in ASSET_EXTENSIONS - {".svg"}:
            continue
        path = root / relative
        try:
            if path.stat().st_size > MAXIMUM_SOURCE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            continue   # 바이너리·다른 인코딩
        if not pattern.search(text):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                matches.append({"path": relative, "line": number, "kind": location_kind(relative),
                                "text": line.strip()[:MAXIMUM_LINE_CHARACTERS]})
    return _result(kind, term, matches)


def _search_file(root: Path, tracked: list, relative: str) -> dict:
    source = (root / relative)
    if not source.is_file():
        return {"type": "file", "term": relative, "ok": False, "code": "file_not_found", "total": 0, "by_kind": {},
                "matches": []}
    digest, name, extension = file_sha256(source), normalized_asset_name(relative), Path(relative).suffix.lower()
    matches = []
    for other in tracked:
        if other == Path(relative).as_posix():
            continue
        is_same_name = normalized_asset_name(other) == name and len(name) >= 3
        path = root / other
        try:
            if not is_same_name and path.stat().st_size != source.stat().st_size:
                continue
            is_identical = file_sha256(path) == digest
        except OSError:
            continue
        if is_identical or is_same_name:
            matches.append({"path": other, "kind": location_kind(other),
                            "relation": "identical" if is_identical else
                            ("same_name_different_content" if Path(other).suffix.lower() == extension else "same_name_other_format")})
    return _result("file", relative, matches)


def _result(kind: str, term: str, matches: list) -> dict:
    by_kind = {}
    for match in matches:
        by_kind[match["kind"]] = by_kind.get(match["kind"], 0) + 1
    return {"type": kind, "term": term, "total": len(matches), "files": len({m["path"] for m in matches}),
            "by_kind": by_kind, "matches": matches}


def _trim(result: dict, limit: int) -> dict:
    """종류별로 돌아가며 표본을 골라 limit 개 (한 종류가 목록을 독차지하지 않게)"""
    queues = {kind: [m for m in result["matches"] if m["kind"] == kind] for kind in LOCATION_KINDS}
    picked = []
    while len(picked) < limit and any(queues.values()):
        for kind in LOCATION_KINDS:
            if queues[kind] and len(picked) < limit:
                picked.append(queues[kind].pop(0))
    return {**result, "matches": picked, "truncated": result["total"] - len(picked)}
