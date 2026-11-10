"""pro-presentation 공용 값: 덱 폴더 파일 이름, 상태 폴더, 첫 실행 질문, 말하기 속도 기본값"""
from __future__ import annotations

from pathlib import Path

SKILL_ID = "presentation"
SKILL_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = SKILL_ROOT / "assets"
PRACTICE_ASSETS_DIR = ASSETS_DIR / "practice"
DECK_TEMPLATE_DIR = ASSETS_DIR / "deck-template"

# 덱 폴더 구조: deck.json · memory.md · theme.css · slides/<id>/ · recordings/<label>/ · exports/
DECK_FILE_NAME = "deck.json"
MEMORY_FILE_NAME = "memory.md"
THEME_FILE_NAME = "theme.css"
SLIDES_DIR_NAME = "slides"
RECORDINGS_DIR_NAME = "recordings"
EXPORTS_DIR_NAME = "exports"
# 서버 상태(pid·포트·키). 덱 안에 두어 덱마다 서버 하나
STATE_DIR_NAME = ".presentation"
SERVER_INFO_FILE_NAME = "server.json"
SERVER_LOG_FILE_NAME = "server.log"
# 연습 화면 배치 (글자 크기 · 패널 크기): 덱마다 기억
LAYOUT_FILE_NAME = "layout.json"

# 장 폴더 안 파일: 본체(html 또는 가져온 그림) · 대본 · 카드 · 말한 버전 · 메모
SLIDE_HTML_FILE_NAME = "slide.html"
SLIDE_IMAGE_NAMES = ("slide.jpg", "slide.png", "slide.webp")
SCRIPT_FILE_NAME = "script.md"
NOTES_FILE_NAME = "notes.md"
TAKES_FILE_NAME = "takes.md"
MEMO_FILE_NAME = "memo.md"
# 브라우저가 저장할 수 있는 파일 (그 밖은 거부)
SAVABLE_FILES = {"script": SCRIPT_FILE_NAME, "memo": MEMO_FILE_NAME}

# 녹화 폴더 안 파일
RECORDING_META_FILE_NAME = "meta.json"
TRANSCRIPT_FILE_NAME = "transcript.txt"
RANGES_FILE_NAME = "ranges.json"
# 연습 화면 녹음: audio.<webm|mp4|ogg> + 장 넘긴 시각
RECORDING_AUDIO_STEM = "audio"
MARKS_FILE_NAME = "marks.json"

# 버전 계산에서 빼는 폴더 (서버 상태·내보내기 결과는 화면을 다시 그릴 이유가 아님)
VERSION_SKIPPED_DIRS = {STATE_DIR_NAME, EXPORTS_DIR_NAME}

# 말하기 속도 기본값 (초당 글자 수, 공백·문장부호·무대 지시 제외). 녹화가 있으면 녹화로 계산
DEFAULT_CHARACTERS_PER_SECOND = 6.0

# 모든 발표에 쓰는 사용자 발표 메모리: 새 덱 memory.md 의 출발점 (레포 밖)
USER_MEMORY_RELATIVE = Path("presentation") / "memory.md"
LAST_DECK_RELATIVE = Path("presentation") / "last_decks.json"

# 슬라이드 크기 (px) · PPT 크기 (인치, 16:9)
SLIDE_WIDTH_PIXELS = 1920
SLIDE_HEIGHT_PIXELS = 1080
PPT_WIDTH_INCHES = 13.333
PPT_HEIGHT_INCHES = 7.5

# 첫 실행 질문: 하나씩 묻고 답은 deck.json · memory.md 에 적는다 (references/init-questions.md)
INIT_QUESTIONS = (
    {"id": "purpose", "ask": "What is this talk for, and where is it given (event, round, audience)?",
     "writes": "deck.json title + memory.md Directions"},
    {"id": "time_limit", "ask": "How long may the talk run, and is there Q&A after it?",
     "writes": "deck.json time_limit_seconds"},
    {"id": "criteria", "ask": "Are there judging criteria or a rubric? (a pro-judge rubric path works too)",
     "writes": "deck.json rubric + memory.md Directions"},
    {"id": "language", "ask": "Which language will you speak in?", "writes": "deck.json language"},
    {"id": "material", "ask": "What do you already have: nothing, an outline or plan, a PPT, or a PDF?",
     "writes": "next step: build slides, or import"},
    {"id": "terms", "ask": "Any words the team always uses or never uses (names, product terms)?",
     "writes": "memory.md Glossary"},
    {"id": "recording", "ask": "Will you record full run-throughs (for example on YouTube) to compare timing?",
     "writes": "memory.md Directions"},
    {"id": "exports", "ask": "What must you hand in at the end: PDF, PPT, or nothing?",
     "writes": "memory.md Directions"},
)
