"""연습 화면 녹음: 장 넘긴 시각(marks) > 장별 구간, 녹음 폴더 만들기
서버(분리 프로세스)와 recording add 가 함께 씀 (common 의존 없음)
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from pro_presentation.settings import (MARKS_FILE_NAME, RANGES_FILE_NAME, RECORDING_AUDIO_STEM,
                                       RECORDING_META_FILE_NAME, RECORDINGS_DIR_NAME)

# 브라우저 녹음 형식 > 저장 확장자 (Chrome·Firefox webm, Safari mp4)
RECORDING_EXTENSIONS = ("webm", "mp4", "ogg")


def next_take_label(recordings_dir: Path) -> str:
    """take-<n>-<날짜> (이미 있는 이름은 건너뜀)"""
    count = len([path for path in recordings_dir.iterdir() if path.is_dir()]) if recordings_dir.is_dir() else 0
    while True:
        count += 1
        label = f"take-{count}-{time.strftime('%Y%m%d')}"
        if not (recordings_dir / label).exists():
            return label


def marks_to_ranges(marks: list[dict], duration_seconds: float) -> dict[str, list[int]]:
    """[{slide, at}] (보여 준 순서) > {slide: [시작, 끝]} 초. 같은 장을 여러 번 보면 가장 긴 방문"""
    ordered = sorted((mark for mark in marks if mark.get("slide")), key=lambda mark: float(mark["at"]))
    ranges: dict[str, list[int]] = {}
    for index, mark in enumerate(ordered):
        start = float(mark["at"])
        end = float(ordered[index + 1]["at"]) if index + 1 < len(ordered) else duration_seconds
        visit = [round(start), round(end)]
        previous = ranges.get(mark["slide"])
        if visit[1] > visit[0] and (previous is None or visit[1] - visit[0] > previous[1] - previous[0]):
            ranges[mark["slide"]] = visit
    return ranges


def parse_marks(raw: str) -> tuple[list[dict], float]:
    """브라우저가 보낸 JSON {marks:[{slide, at}], duration} > (marks, 길이). 형식이 틀리면 ValueError"""
    payload = json.loads(raw)
    duration = float(payload["duration"])
    marks = [{"slide": str(mark["slide"]), "at": max(0.0, min(float(mark["at"]), duration))}
             for mark in payload["marks"]]
    if duration <= 0 or not marks:
        raise ValueError("empty recording")
    return marks, duration


def save_page_recording(deck_dir: Path, extension: str, audio_path: Path, marks: list[dict],
                        duration_seconds: float) -> dict:
    """임시 오디오 파일 > recordings/<label>/ (audio.<ext> · marks.json · ranges.json · meta.json)"""
    recordings_dir = deck_dir / RECORDINGS_DIR_NAME
    recordings_dir.mkdir(parents=True, exist_ok=True)
    label = next_take_label(recordings_dir)
    folder = recordings_dir / label
    folder.mkdir()
    audio_file = folder / f"{RECORDING_AUDIO_STEM}.{extension}"
    audio_path.replace(audio_file)
    ranges = marks_to_ranges(marks, duration_seconds)
    (folder / MARKS_FILE_NAME).write_text(
        json.dumps({"duration_seconds": round(duration_seconds, 2), "marks": marks}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    (folder / RANGES_FILE_NAME).write_text(json.dumps(ranges, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    meta = {"label": label, "url": "", "file": audio_file.name, "source": "page", "added_at": time.strftime("%Y-%m-%d")}
    (folder / RECORDING_META_FILE_NAME).write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"label": label, "duration_seconds": round(duration_seconds), "slide_count": len(ranges)}


def find_page_audio(folder: Path) -> Path | None:
    """녹음 폴더 안 연습 화면 녹음 파일 (audio.webm 등)"""
    for extension in RECORDING_EXTENSIONS:
        candidate = folder / f"{RECORDING_AUDIO_STEM}.{extension}"
        if candidate.is_file():
            return candidate
    return None
