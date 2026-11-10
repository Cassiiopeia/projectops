"""덱 폴더 읽기: deck.json · 장 폴더 · 녹화 > 화면과 검사가 쓰는 한 덩어리 dict
읽기만 한다. 한 장이 깨져도 그 장에 error 를 달고 나머지는 그대로 돌려준다
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from pro_presentation.settings import (DECK_FILE_NAME, DEFAULT_CHARACTERS_PER_SECOND, IMAGE_SUFFIXES, MEMO_FILE_NAME,
                                       MEMORY_FILE_NAME, NOTES_FILE_NAME, RANGES_FILE_NAME,
                                       RECORDING_META_FILE_NAME, RECORDINGS_DIR_NAME, SCRIPT_FILE_NAME,
                                       SLIDE_HTML_FILE_NAME, SLIDE_IMAGE_NAMES, SLIDE_TEXT_FILE_NAMES,
                                       SLIDES_DIR_NAME, TAKES_FILE_NAME, THEME_FILE_NAME, THUMBNAIL_STEMS,
                                       TRANSCRIPT_FILE_NAME, VERSION_SKIPPED_DIRS)

SECTION_HEADING_PATTERN = re.compile(r"^##\s+(.*)$")
TRANSCRIPT_LINE_PATTERN = re.compile(r"^\[(\d+):(\d+)\]\s*(.*)$")
# 시간 계산에서 빼는 것: 무대 지시 ( ) · 공백 · 문장부호
STAGE_DIRECTION_PATTERN = re.compile(r"\([^)]*\)")
NOT_SPOKEN_PATTERN = re.compile(r"[\s.,!?·'\"‘’“”~:;\-]")
SPOKEN_LABEL = "spoken:"
FEEDBACK_LABEL = "feedback:"
SAFE_SLIDE_ID_PATTERN = re.compile(r"^[^/\\]+$")


def read_text(path: Path) -> str:
    """없는 파일은 빈 글. 깨진 인코딩은 대체 문자로"""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def split_sections(markdown: str) -> list[dict]:
    """'## 제목' 하나 > {title, body}. 첫 제목 앞 글은 버림"""
    sections: list[dict] = []
    for line in markdown.splitlines():
        heading = SECTION_HEADING_PATTERN.match(line)
        if heading:
            sections.append({"title": heading.group(1).strip(), "lines": []})
        elif sections:
            sections[-1]["lines"].append(line)
    return [{"title": section["title"], "body": "\n".join(section["lines"]).strip()} for section in sections]


def parse_takes(markdown: str) -> list[dict]:
    """takes.md (차수마다 '## 라벨' > 'Spoken:' 문단 > 'Feedback:' 목록) > 최신 차수 먼저"""
    takes = []
    for section in split_sections(markdown):
        spoken_lines: list[str] = []
        feedback: list[str] = []
        mode = None
        for line in section["body"].splitlines():
            lowered = line.strip().lower()
            if lowered.startswith(SPOKEN_LABEL):
                mode = "spoken"
                rest = line.strip()[len(SPOKEN_LABEL):].strip()
                if rest:
                    spoken_lines.append(rest)
            elif lowered.startswith(FEEDBACK_LABEL):
                mode = "feedback"
            elif mode == "feedback" and line.strip().startswith("- "):
                feedback.append(line.strip()[2:].strip())
            elif mode == "spoken" and line.strip():
                spoken_lines.append(line.strip())
        takes.append({"label": section["title"], "spoken": " ".join(spoken_lines), "feedback": feedback})
    return list(reversed(takes))


def parse_table(body: str) -> list[list[str]]:
    """마크다운 표 > 칸 목록 (머리줄·구분줄 제외)"""
    rows = [line.strip() for line in body.splitlines() if line.strip().startswith("|")]
    cells = [[cell.strip() for cell in row.strip("|").split("|")] for row in rows]
    return [row for row in cells[1:] if not all(set(cell) <= set("-: ") for cell in row)]


def count_spoken_characters(text: str) -> int:
    return len(NOT_SPOKEN_PATTERN.sub("", STAGE_DIRECTION_PATTERN.sub("", text)))


def estimate_seconds(script: str, characters_per_second: float) -> int:
    return round(count_spoken_characters(script) / characters_per_second) if characters_per_second > 0 else 0


def read_memory(deck_dir: Path) -> dict:
    """memory.md > 용어 표(쓰지 않는다 | 대신 | 이유) · 받아쓰기 보정 표(들린 말 | 실제 말)"""
    sections = {section["title"].lower(): section["body"] for section in split_sections(read_text(deck_dir / MEMORY_FILE_NAME))}
    glossary = [{"avoid": row[0], "instead": row[1] if len(row) > 1 else "", "why": row[2] if len(row) > 2 else ""}
                for row in parse_table(sections.get("glossary", "")) if row and row[0]]
    fixes = [(row[0], row[1]) for row in parse_table(sections.get("transcript fixes", "")) if len(row) > 1 and row[0]]
    return {"glossary": glossary, "transcript_fixes": fixes}


def read_deck_settings(deck_dir: Path) -> tuple[dict, list[str]]:
    """deck.json > 설정. 장 목록은 문자열 또는 {id, kind}"""
    try:
        settings = json.loads((deck_dir / DECK_FILE_NAME).read_text(encoding="utf-8"))
    except OSError:
        return {}, ["deck.json is missing"]
    except ValueError as error:
        return {}, [f"deck.json is not valid JSON: {error}"]
    return (settings if isinstance(settings, dict) else {}), []


def slide_entries(settings: dict) -> list[dict]:
    entries = []
    for entry in settings.get("slides") or []:
        if isinstance(entry, str):
            entries.append({"id": entry, "kind": ""})
        elif isinstance(entry, dict) and entry.get("id"):
            entries.append({"id": str(entry["id"]), "kind": str(entry.get("kind") or "")})
    return entries


def slide_body_version(folder: Path) -> int:
    """장 본체(slide.html · 그림 등)의 가장 늦은 수정 시각 + 파일 수. 대본 · 카드 · 메모 글은 뺌"""
    latest = count = 0
    try:
        for entry in os.scandir(folder):
            if entry.name not in SLIDE_TEXT_FILE_NAMES and entry.is_file():
                latest = max(latest, entry.stat().st_mtime_ns)
                count += 1
    except OSError:
        return 0
    return latest + count


def load_slide(deck_dir: Path, entry: dict, number: int, characters_per_second: float) -> dict:
    """장 폴더 하나 > SlideView (없거나 깨지면 error)"""
    slide = {"id": entry["id"], "number": number, "kind": entry["kind"], "title": entry["id"], "html": None,
             "image": None, "script": "", "notes": [], "takes": [], "memo": "", "estimate_seconds": 0, "error": None,
             "version": 0}
    folder = deck_dir / SLIDES_DIR_NAME / entry["id"]
    if not SAFE_SLIDE_ID_PATTERN.match(entry["id"]) or not folder.is_dir():
        slide["error"] = "missing_folder"
        return slide
    slide["version"] = slide_body_version(folder)
    thumbnail = next((path.name for name in THUMBNAIL_STEMS for path in sorted(folder.glob(f"{name}.*"))
                      if path.suffix.lower() in IMAGE_SUFFIXES), None)
    slide["thumbnail"] = f"deck/{SLIDES_DIR_NAME}/{entry['id']}/{thumbnail}" if thumbnail else None
    html_file = folder / SLIDE_HTML_FILE_NAME
    if html_file.is_file():
        slide["html"] = read_text(html_file)
    else:
        image = next((name for name in SLIDE_IMAGE_NAMES if (folder / name).is_file()), None)
        if image:
            slide["image"] = f"deck/{SLIDES_DIR_NAME}/{entry['id']}/{image}"
        else:
            slide["error"] = "missing_slide_body"
    slide["script"] = read_text(folder / SCRIPT_FILE_NAME).strip()
    slide["notes"] = split_sections(read_text(folder / NOTES_FILE_NAME))
    title_note = next((note for note in slide["notes"] if note["title"].lower() == "title"), None)
    if title_note and title_note["body"]:
        slide["title"] = title_note["body"].splitlines()[0]
        slide["notes"] = [note for note in slide["notes"] if note is not title_note]
    slide["takes"] = parse_takes(read_text(folder / TAKES_FILE_NAME))
    slide["memo"] = read_text(folder / MEMO_FILE_NAME).strip()
    slide["estimate_seconds"] = estimate_seconds(slide["script"], characters_per_second)
    return slide


def read_transcript(path: Path, fixes: list[tuple[str, str]]) -> list[dict]:
    """'[mm:ss] 문장' 줄 > [{at, text}] (받아쓰기 보정 적용)"""
    lines = []
    for raw_line in read_text(path).splitlines():
        match = TRANSCRIPT_LINE_PATTERN.match(raw_line.strip())
        if not match:
            continue
        text = match.group(3)
        for heard, actual in fixes:
            text = text.replace(heard, actual)
        lines.append({"at": int(match.group(1)) * 60 + int(match.group(2)), "text": text})
    return lines


def load_recordings(deck_dir: Path, fixes: list[tuple[str, str]]) -> list[dict]:
    """recordings/<label>/ > [{label, url, lines, ranges}] (폴더 이름 순)"""
    root = deck_dir / RECORDINGS_DIR_NAME
    recordings = []
    for folder in sorted(path for path in root.iterdir() if path.is_dir()) if root.is_dir() else []:
        try:
            meta = json.loads(read_text(folder / RECORDING_META_FILE_NAME) or "{}")
            ranges = json.loads(read_text(folder / RANGES_FILE_NAME) or "{}")
        except ValueError:
            meta, ranges = {}, {}
        recordings.append({"label": meta.get("label") or folder.name, "folder": folder.name, "url": meta.get("url", ""),
                           "lines": read_transcript(folder / TRANSCRIPT_FILE_NAME, fixes),
                           "ranges": {key: value for key, value in ranges.items()
                                      if isinstance(value, list) and len(value) == 2}})
    return recordings


def measure_speaking_rate(recordings: list[dict]) -> float:
    """녹화 글자 수 ÷ 말한 시간 (구간 있는 녹화만, 최신 녹화 우선). 없으면 기본값"""
    for recording in reversed(recordings):
        characters = seconds = 0
        for start, end in recording["ranges"].values():
            seconds += max(0, end - start)
            characters += sum(count_spoken_characters(line["text"]) for line in recording["lines"]
                              if start <= line["at"] < end)
        if seconds > 0 and characters > 0:
            return round(characters / seconds, 2)
    return DEFAULT_CHARACTERS_PER_SECOND


def load_deck(deck_dir: Path) -> dict:
    """덱 폴더 전체 > {title, language, time_limit_seconds, characters_per_second, slides, recordings, problems}"""
    deck_dir = Path(deck_dir)
    settings, problems = read_deck_settings(deck_dir)
    memory = read_memory(deck_dir)
    recordings = load_recordings(deck_dir, memory["transcript_fixes"])
    characters_per_second = float(settings.get("characters_per_second") or measure_speaking_rate(recordings))
    slides = [load_slide(deck_dir, entry, number, characters_per_second)
              for number, entry in enumerate(slide_entries(settings), start=1)]
    problems += [f"slide {slide['number']} ({slide['id']}): {slide['error']}" for slide in slides if slide["error"]]
    time_limit = settings.get("time_limit_seconds")
    return {"title": settings.get("title") or deck_dir.name, "language": settings.get("language") or "en",
            "time_limit_seconds": int(time_limit) if isinstance(time_limit, (int, float)) and time_limit > 0 else None,
            "rubric": settings.get("rubric") or "", "characters_per_second": characters_per_second,
            "theme_version": _modified_at(deck_dir / THEME_FILE_NAME),
            "glossary": memory["glossary"], "slides": slides, "recordings": recordings, "problems": problems}


def _modified_at(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def deck_version(deck_dir: Path) -> int:
    """덱 안 파일 · 폴더의 가장 늦은 수정 시각(ns) + 개수. 지우기·추가도 잡는다
    scandir: 폴더를 읽을 때 받은 정보로 수정 시각을 알아 파일마다 다시 묻지 않음 (2초마다 도는 검사)"""
    latest = count = 0
    pending = [(str(deck_dir), True)]
    while pending:
        folder, is_deck_root = pending.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            if is_deck_root and entry.name in VERSION_SKIPPED_DIRS:
                continue
            try:
                latest = max(latest, entry.stat().st_mtime_ns)
                count += 1
                if entry.is_dir(follow_symlinks=False):
                    pending.append((entry.path, False))
            except OSError:
                continue
    return latest + count
