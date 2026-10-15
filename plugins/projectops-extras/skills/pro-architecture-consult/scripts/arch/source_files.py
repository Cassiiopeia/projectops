"""소스 파일 탐색 공통: 제외 폴더, 언어 판별, 주석 줄 분류"""
from __future__ import annotations

import os
import re
from pathlib import Path

# 탐색 제외 폴더 (규칙 테스트 템플릿 4종과 같은 목록 — ledger 판정이 같아야 한다)
SKIPPED_DIRECTORY_NAMES = {
    ".git", "build", "dist", "node_modules", ".dart_tool", "Pods", ".gradle",
    "venv", ".venv", "__pycache__", ".next", "out", "target", ".idea",
}

# 생성 파일 (scan·deps·diff에서만 제외 — 사람이 쓰지 않은 코드라 규칙 대상 아님)
GENERATED_FILE_PATTERN = re.compile(
    r"(\.g\.dart|\.freezed\.dart|\.gr\.dart|\.mocks\.dart|\.gen\.\w+|\.min\.js|\.pb\.\w+|_pb2\.py)$"
)

LANGUAGE_BY_EXTENSION = {
    ".dart": "dart", ".java": "java", ".kt": "kotlin", ".py": "python",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
}
SLASH_COMMENT_LANGUAGES = {"dart", "java", "kotlin", "javascript", "typescript"}

# 한 파일 최대 읽기 크기 (2MB — 그 이상은 생성물·데이터로 보고 건너뜀)
MAXIMUM_SOURCE_BYTES = 2 * 1024 * 1024


def walk_files(root: Path, start: Path | None = None):
    """root 기준 상대경로(posix)와 절대경로 쌍을 낸다 (제외 폴더는 내려가지 않음)"""
    base = start or root
    for directory, subdirectories, filenames in os.walk(base):
        subdirectories[:] = sorted(d for d in subdirectories if d not in SKIPPED_DIRECTORY_NAMES)
        for filename in sorted(filenames):
            absolute = Path(directory) / filename
            yield absolute.relative_to(root).as_posix(), absolute


def language_of(relative_path: str) -> str | None:
    return LANGUAGE_BY_EXTENSION.get(Path(relative_path).suffix.lower())


def is_generated_file(relative_path: str) -> bool:
    return bool(GENERATED_FILE_PATTERN.search(relative_path))


def iter_source_files(root: Path):
    """사람이 쓴 소스만: (상대경로, 언어, 본문)"""
    for relative, absolute in walk_files(root):
        language = language_of(relative)
        if not language or is_generated_file(relative):
            continue
        try:
            if absolute.stat().st_size > MAXIMUM_SOURCE_BYTES:
                continue
            text = absolute.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        yield relative, language, text


def classify_lines(text: str, language: str):
    """줄마다 (번호, 종류, 주석 내용) — 종류: comment / code / blank

    주석 2종: 줄 전체 주석, 블록 주석(/* */, 파이썬 docstring). 코드 뒤 주석은 code로 세고 내용만 넘긴다.
    """
    result = []
    is_inside_block = False
    block_terminator = ""
    block_kind = "comment"
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if is_inside_block:
            result.append((number, block_kind, stripped if block_kind == "comment" else ""))
            if (block_terminator == "*/" and "*/" in stripped) or \
                    (block_terminator != "*/" and stripped.count(block_terminator) % 2 == 1):
                is_inside_block = False
            continue
        if not stripped:
            result.append((number, "blank", ""))
            continue
        if language in SLASH_COMMENT_LANGUAGES:
            if stripped.startswith("//"):
                result.append((number, "comment", stripped))
            elif stripped.startswith("/*"):
                result.append((number, "comment", stripped))
                if "*/" not in stripped[2:]:
                    is_inside_block, block_terminator, block_kind = True, "*/", "comment"
            else:
                result.append((number, "code", _trailing_slash_comment(raw)))
            continue
        # 파이썬: # 주석, 줄 첫머리 삼중따옴표 = docstring(주석), 그 외 삼중따옴표 = 여러 줄 문자열(코드)
        opened_quote = next((q for q in ('"""', "'''") if stripped.count(q) % 2 == 1), None)
        if stripped.startswith("#") and not stripped.startswith("#!"):
            result.append((number, "comment", stripped))
        elif stripped.startswith(('"""', "'''")):
            result.append((number, "comment", stripped))
            if opened_quote:
                is_inside_block, block_terminator, block_kind = True, opened_quote, "comment"
        else:
            trailing = raw.split("  #", 1)[1].strip() if "  #" in raw and not opened_quote else ""
            result.append((number, "code", trailing))
            if opened_quote:
                is_inside_block, block_terminator, block_kind = True, opened_quote, "code"
    return result


def _trailing_slash_comment(raw: str) -> str:
    """코드 뒤 // 주석 내용 (문자열 안의 // 는 대충 거름: URL 제외)"""
    index = raw.find(" //")
    if index < 0 or "://" in raw[max(0, index - 6):index + 3]:
        return ""
    return raw[index:].strip()


def comment_blocks(classified):
    """연속된 주석 줄 묶음: [(시작 줄, 길이, 내용 목록)]"""
    blocks, current = [], []
    for number, kind, content in classified:
        if kind == "comment":
            current.append((number, content))
        elif current:
            blocks.append((current[0][0], len(current), [c for _, c in current]))
            current = []
    if current:
        blocks.append((current[0][0], len(current), [c for _, c in current]))
    return blocks


def split_identifier_words(name: str) -> list[str]:
    """camelCase·PascalCase·snake_case > 소문자 단어 목록"""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name.strip("_$"))
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", spaced)
    return [w.lower() for w in re.split(r"[\s_$]+", spaced) if w]
