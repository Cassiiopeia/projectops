"""녹화 mp4 점검: 재생 가능(moov 상자 유무) · 실제 길이 (#1130)
최상위 상자 훑기(표준 라이브러리) > 길이는 ffprobe > mvhd 순
"""
from __future__ import annotations

import shutil
import struct
import subprocess
from pathlib import Path

# ffprobe 길이 조회 시간 상한 (초)
FFPROBE_TIMEOUT_SECONDS = 30
# 상자 머리: 크기(4) + 종류(4), 크기 1 이면 64비트 크기(8) 추가
BOX_HEADER_BYTES = 8
LARGE_BOX_HEADER_BYTES = 16


def inspect_mp4(path: Path) -> dict:
    """mp4 > {is_playable, duration_seconds, duration_source, problem}. problem 은 재생 불가 사유."""
    try:
        file_size_bytes = path.stat().st_size
        with open(path, "rb") as video:
            top_boxes = list(_iter_boxes(video, 0, file_size_bytes))
            moov = next((box for box in top_boxes if box[0] == b"moov"), None)
            if moov is None:
                kinds = ",".join(box[0].decode("latin-1") for box in top_boxes) or "none"
                return {"is_playable": False, "duration_seconds": None, "duration_source": None,
                        "problem": f"no moov box (top-level boxes: {kinds}) — the recorder was cut off before it finalized the file"}
            mvhd_seconds = _read_mvhd_seconds(video, moov)
    except OSError as e:
        return {"is_playable": False, "duration_seconds": None, "duration_source": None, "problem": str(e)}
    probed_seconds = _probe_seconds(path)
    if probed_seconds is not None:
        return {"is_playable": True, "duration_seconds": probed_seconds, "duration_source": "ffprobe", "problem": None}
    return {"is_playable": True, "duration_seconds": mvhd_seconds,
            "duration_source": "mvhd" if mvhd_seconds is not None else None, "problem": None}


def _iter_boxes(video, start: int, end: int):
    """[start, end) 구간 상자 > (종류, 시작, 머리 길이, 전체 크기). 잘린 상자에서 멈춤."""
    position = start
    while position + BOX_HEADER_BYTES <= end:
        video.seek(position)
        header = video.read(BOX_HEADER_BYTES)
        if len(header) < BOX_HEADER_BYTES:
            return
        size, kind = struct.unpack(">I4s", header)
        header_length = BOX_HEADER_BYTES
        if size == 1:
            large_size = video.read(8)
            if len(large_size) < 8:
                return
            size = struct.unpack(">Q", large_size)[0]
            header_length = LARGE_BOX_HEADER_BYTES
        elif size == 0:   # 0: 파일 끝까지
            size = end - position
        if size < header_length:
            return
        # 끝이 잘린 상자도 종류는 알려 준다 (mdat 만 남은 파일 진단용)
        yield kind, position, header_length, min(size, end - position)
        position += size


def _read_mvhd_seconds(video, moov: tuple) -> float | None:
    """moov 안 mvhd > 길이(초). mvhd 버전 0: 32비트 · 1: 64비트 필드."""
    _, moov_start, moov_header, moov_size = moov
    for kind, start, header_length, _ in _iter_boxes(video, moov_start + moov_header, moov_start + moov_size):
        if kind != b"mvhd":
            continue
        video.seek(start + header_length)
        version = video.read(4)[:1]
        if version == b"\x01":
            body = video.read(28)
            if len(body) < 28:
                return None
            timescale, duration = struct.unpack(">IQ", body[16:28])
        else:
            body = video.read(16)
            if len(body) < 16:
                return None
            timescale, duration = struct.unpack(">II", body[8:16])
        return round(duration / timescale, 1) if timescale else None
    return None


def _probe_seconds(path: Path) -> float | None:
    """ffprobe 가 있으면 컨테이너 길이(초). 없거나 실패면 None."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                                capture_output=True, text=True, errors="replace", timeout=FFPROBE_TIMEOUT_SECONDS)
        return round(float(result.stdout.strip()), 1) if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
