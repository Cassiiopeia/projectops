"""pro-presentation shared values: deck folder file names, state folder, first-run questions, speaking speed default"""
from __future__ import annotations

from pathlib import Path

SKILL_ID = "presentation"
SKILL_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = SKILL_ROOT / "assets"
PRACTICE_ASSETS_DIR = ASSETS_DIR / "practice"
DECK_TEMPLATE_DIR = ASSETS_DIR / "deck-template"

# Deck folder layout: deck.json · memory.md · theme.css · slides/<id>/ · recordings/<label>/ · exports/
DECK_FILE_NAME = "deck.json"
MEMORY_FILE_NAME = "memory.md"
THEME_FILE_NAME = "theme.css"
SLIDES_DIR_NAME = "slides"
RECORDINGS_DIR_NAME = "recordings"
EXPORTS_DIR_NAME = "exports"
# Server state (pid, port, key). Kept inside the deck so there is one server per deck
STATE_DIR_NAME = ".presentation"
SERVER_INFO_FILE_NAME = "server.json"
SERVER_LOG_FILE_NAME = "server.log"
# Practice screen layout (font size · panel size): remembered per deck
LAYOUT_FILE_NAME = "layout.json"
# Screen copies of large images (image_variants.py): .presentation/images/
IMAGE_CACHE_DIR_NAME = "images"

# Files in a slide folder: body (html or imported image) · script · cards · spoken versions · notes
SLIDE_HTML_FILE_NAME = "slide.html"
SLIDE_IMAGE_NAMES = ("slide.jpg", "slide.png", "slide.webp")
SCRIPT_FILE_NAME = "script.md"
NOTES_FILE_NAME = "notes.md"
TAKES_FILE_NAME = "takes.md"
MEMO_FILE_NAME = "memo.md"
# Text-only files: changes do not redraw the slide body
SLIDE_TEXT_FILE_NAMES = {SCRIPT_FILE_NAME, NOTES_FILE_NAME, TAKES_FILE_NAME, MEMO_FILE_NAME}
# Image extensions · thumbnail candidates (imported original image > slide image)
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
THUMBNAIL_STEMS = ("original", "slide")
# Files the browser may save (others rejected)
SAVABLE_FILES = {"script": SCRIPT_FILE_NAME, "memo": MEMO_FILE_NAME}

# Files in a recording folder
RECORDING_META_FILE_NAME = "meta.json"
TRANSCRIPT_FILE_NAME = "transcript.txt"
RANGES_FILE_NAME = "ranges.json"
# Practice screen recording: audio.<webm|mp4|ogg> + slide change times
RECORDING_AUDIO_STEM = "audio"
MARKS_FILE_NAME = "marks.json"

# Folders excluded from version calculation (server state and export results are no reason to redraw)
VERSION_SKIPPED_DIRS = {STATE_DIR_NAME, EXPORTS_DIR_NAME}

# Default speaking speed (characters per second, excluding whitespace, punctuation, stage directions). Computed from recordings when present
DEFAULT_CHARACTERS_PER_SECOND = 6.0

# User talk memory used for every talk: starting point for a new deck's memory.md (outside the repo)
USER_MEMORY_RELATIVE = Path("presentation") / "memory.md"
LAST_DECK_RELATIVE = Path("presentation") / "last_decks.json"

# Slide size (px) · PPT size (inches, 16:9)
SLIDE_WIDTH_PIXELS = 1920
SLIDE_HEIGHT_PIXELS = 1080
PPT_WIDTH_INCHES = 13.333
PPT_HEIGHT_INCHES = 7.5

# First-run questions: asked one at a time; answers written to deck.json · memory.md (references/init-questions.md)
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
