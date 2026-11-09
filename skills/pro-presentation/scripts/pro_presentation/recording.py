"""recording add: 연습 녹화 하나 > recordings/<label>/transcript.txt ('[mm:ss] 문장')
입력 3가지: 로컬 녹음·녹화 파일(whisper) · 영상 주소(자막 먼저, 없으면 whisper) · 자막·받아쓰기 파일(srt·vtt·txt)
장별 구간(ranges.json)은 agent 가 받아쓰기를 읽고 쓴다
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from common.emit import emit

from pro_presentation.config import option_value
from pro_presentation.deck import read_deck_settings
from pro_presentation.settings import (RANGES_FILE_NAME, RECORDING_META_FILE_NAME, RECORDINGS_DIR_NAME,
                                       TRANSCRIPT_FILE_NAME)

TOOL_TIMEOUT_SECONDS = 600
WHISPER_SAMPLE_RATE = 16000
# srt·vtt 시간 줄: 00:01:02,500 --> 00:01:05,000 (시 생략 가능)
CUE_TIME_PATTERN = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})[.,]\d+\s+-->")
TRANSCRIPT_LINE_PATTERN = re.compile(r"^\[\d+:\d{2}\]")
MARKUP_PATTERN = re.compile(r"<[^>]+>")


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace",
                          timeout=TOOL_TIMEOUT_SECONDS)


def _yt_dlp_command() -> list[str] | None:
    """yt-dlp 실행 파일 > 없으면 파이썬 모듈"""
    executable = shutil.which("yt-dlp")
    if executable:
        return [executable]
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        return None
    return [sys.executable, "-m", "yt_dlp"]


def _format_line(seconds: float, text: str) -> str:
    whole = int(seconds)
    return f"[{whole // 60:02d}:{whole % 60:02d}] {text}"


def json3_to_lines(caption_file: Path) -> list[str]:
    """YouTube json3 자막 > 줄"""
    events = json.loads(caption_file.read_text(encoding="utf-8")).get("events") or []
    lines = []
    for event in events:
        text = "".join(segment.get("utf8", "") for segment in event.get("segs") or []).replace("\n", " ").strip()
        if text:
            lines.append(_format_line(int(event.get("tStartMs", 0)) / 1000, text))
    return lines


def subtitle_to_lines(subtitle_file: Path) -> list[str]:
    """srt · vtt > 줄 (이미 '[mm:ss]' 형식인 txt 는 그대로)"""
    raw_lines = subtitle_file.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    if any(TRANSCRIPT_LINE_PATTERN.match(line.strip()) for line in raw_lines):
        return [line.strip() for line in raw_lines if TRANSCRIPT_LINE_PATTERN.match(line.strip())]
    lines, start, texts = [], None, []
    for raw_line in raw_lines + [""]:
        cue = CUE_TIME_PATTERN.match(raw_line.strip())
        if cue:
            start = int(cue.group(1) or 0) * 3600 + int(cue.group(2)) * 60 + int(cue.group(3))
            texts = []
        elif raw_line.strip() and start is not None:
            texts.append(MARKUP_PATTERN.sub("", raw_line.strip()))
        elif start is not None:
            if texts:
                lines.append(_format_line(start, " ".join(texts)))
            start = None
    return lines


def fetch_captions(command: list[str], url: str, language: str, work_dir: Path) -> list[str] | None:
    """원어 자동 자막(<언어>-orig) > 일반 자막. 없으면 None"""
    _run(command + ["-q", "--no-warnings", "--skip-download", "--write-auto-subs", "--write-subs",
                    "--sub-langs", f"{language}-orig,{language}", "--sub-format", "json3", "-o", "captions", url], work_dir)
    for suffix in (f"{language}-orig", language):
        caption_file = work_dir / f"captions.{suffix}.json3"
        if caption_file.is_file():
            return json3_to_lines(caption_file)
    return None


def transcribe_media(media: Path, language: str, model_name: str, work_dir: Path) -> tuple[list[str] | None, str]:
    """오디오·영상 > 16kHz PCM(ffmpeg) > faster-whisper. (줄, 실패 이유)"""
    try:
        import numpy
        from faster_whisper import WhisperModel
    except ImportError:
        return None, "faster-whisper is not installed (pip install faster-whisper)"
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return None, "ffmpeg is not installed"
    pcm = work_dir / "audio.pcm"
    _run([ffmpeg, "-loglevel", "error", "-y", "-i", str(media), "-ac", "1", "-ar", str(WHISPER_SAMPLE_RATE),
          "-f", "s16le", str(pcm)], work_dir)
    if not pcm.is_file() or pcm.stat().st_size == 0:
        return None, "ffmpeg could not read the recording"
    samples = numpy.fromfile(pcm, dtype=numpy.int16).astype(numpy.float32) / 32768.0
    segments, _ = WhisperModel(model_name, device="cpu", compute_type="int8").transcribe(
        samples, language=language, vad_filter=True)
    return [_format_line(segment.start, segment.text.strip()) for segment in segments], ""


def _lines_from_url(url: str, language: str, model_name: str, work_dir: Path) -> tuple[list[str] | None, str, str]:
    command = _yt_dlp_command()
    if command is None:
        return None, "", "yt-dlp is not installed (pip install yt-dlp)"
    lines = fetch_captions(command, url, language, work_dir)
    if lines:
        return lines, "captions", ""
    _run(command + ["-q", "--no-warnings", "-f", "bestaudio", "-o", "audio.%(ext)s", url], work_dir)
    audio = next(iter(sorted(work_dir.glob("audio.*"))), None)
    if audio is None:
        return None, "", "the video could not be downloaded"
    lines, reason = transcribe_media(audio, language, model_name, work_dir)
    return lines, "whisper", reason


def _next_label(recordings_dir: Path) -> str:
    count = len([path for path in recordings_dir.iterdir() if path.is_dir()]) if recordings_dir.is_dir() else 0
    return f"take-{count + 1}-{time.strftime('%Y%m%d')}"


def cmd_recording_add(args) -> int:
    deck_dir = Path(args.deck).expanduser().resolve()
    settings, problems = read_deck_settings(deck_dir)
    if problems:
        return emit({"ok": False, "code": "no_deck", "error": problems[0], "next": "start --deck <folder>"})
    language = args.language or settings.get("language") or "en"
    model_name = option_value(deck_dir, "whisper_model")
    with tempfile.TemporaryDirectory() as temporary:
        work_dir = Path(temporary)
        if args.transcript:
            source_file = Path(args.transcript).expanduser()
            lines, source, reason = (subtitle_to_lines(source_file), "transcript", "") if source_file.is_file() \
                else (None, "", f"{source_file} does not exist")
        elif args.file:
            media = Path(args.file).expanduser()
            lines, reason = transcribe_media(media, language, model_name, work_dir) if media.is_file() \
                else (None, f"{media} does not exist")
            source = "whisper"
        else:
            lines, source, reason = _lines_from_url(args.url, language, model_name, work_dir)
    if not lines:
        return emit({"ok": False, "code": "no_transcript_source", "error": reason or "No speech was found",
                     "next": "Install what the error names, or ask the user for captions or a transcript file "
                             "(--transcript accepts srt, vtt or '[mm:ss] text' lines)"})
    recordings_dir = deck_dir / RECORDINGS_DIR_NAME
    label = args.label or _next_label(recordings_dir)
    folder = recordings_dir / label
    folder.mkdir(parents=True, exist_ok=True)
    (folder / TRANSCRIPT_FILE_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8")
    meta = {"label": label, "url": args.url or "", "file": args.file or args.transcript or "", "source": source,
            "added_at": time.strftime("%Y-%m-%d")}
    (folder / RECORDING_META_FILE_NAME).write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    if not (folder / RANGES_FILE_NAME).exists():
        (folder / RANGES_FILE_NAME).write_text("{}\n", encoding="utf-8")
    return emit({"summary": f"{len(lines)} lines from {source} into {folder.name}", "label": label, "source": source,
                 "transcript": str(folder / TRANSCRIPT_FILE_NAME), "line_count": len(lines), "last_line": lines[-1],
                 "next": (f"Read the transcript, write {RECORDINGS_DIR_NAME}/{label}/{RANGES_FILE_NAME} as "
                          "{\"<slide id>\": [start_seconds, end_seconds]}, then run check and review each slide "
                          "(references/recording.md)")})
