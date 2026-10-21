"""`--burst SECONDS[:INTERVAL]` — 동작 전부터 연속 캡처해 바뀐 프레임만 남긴다 (#928).

흐름: 동작 전 캡처 스레드 시작 > 동작 > SECONDS 초 더 캡처 > 같은 화면 걸러내기 > 프레임 파일 저장.
"탭이 캡처보다 늦게 실행됨" 을 없애려고 캡처를 먼저 띄운다. 비교는 바이트 해시 (Pillow 없이도 돈다).
"""
from __future__ import annotations

import argparse
import hashlib
import threading
import time

from common.image import to_webp

from pro_launch.runtime.context import project_root
from pro_launch.runtime.shots import shot_folder

# 동작 뒤 더 찍는 시간 상한 (초) · 캡처 간격 기본·하한 (초) · 한 번에 모으는 프레임 상한 (기기가 느리면 간격이 늘어난다)
MAXIMUM_BURST_SECONDS = 30.0
DEFAULT_BURST_INTERVAL_SECONDS = 0.4
MINIMUM_BURST_INTERVAL_SECONDS = 0.1
MAXIMUM_BURST_FRAME_COUNT = 150
# args 에 몰래 얹는 진행 상태 이름 (한 호출 안에서만 산다)
BURST_STATE_ATTRIBUTE = "_burst_state"


def burst_spec(raw: str) -> tuple[float, float]:
    """'3' 또는 '5:0.3' > (뒤로 더 찍을 초, 간격 초). argparse type 용."""
    seconds_text, _, interval_text = raw.partition(":")
    try:
        seconds = float(seconds_text)
        interval = float(interval_text) if interval_text else DEFAULT_BURST_INTERVAL_SECONDS
    except ValueError as e:
        raise argparse.ArgumentTypeError("Must be SECONDS[:INTERVAL] (e.g. 3 · 5:0.3)") from e
    if not 0 < seconds <= MAXIMUM_BURST_SECONDS:
        raise argparse.ArgumentTypeError(f"SECONDS must be above 0 and at most {MAXIMUM_BURST_SECONDS:g}")
    return seconds, max(interval, MINIMUM_BURST_INTERVAL_SECONDS)


def start_burst(args, be, dev_id: str) -> None:
    """--burst 가 있으면 캡처 스레드를 띄운다. 없으면 아무것도 안 한다."""
    spec = getattr(args, "burst", None)
    if not spec:
        return
    stop_event = threading.Event()
    frames: list[tuple[float, bytes]] = []
    began = time.monotonic()

    def capture_loop() -> None:
        while not stop_event.is_set() and len(frames) < MAXIMUM_BURST_FRAME_COUNT:
            data = be.grab(dev_id)
            if data:
                frames.append((round(time.monotonic() - began, 2), data))
            stop_event.wait(spec[1])

    thread = threading.Thread(target=capture_loop, daemon=True)
    thread.start()
    setattr(args, BURST_STATE_ATTRIBUTE, {"stop": stop_event, "thread": thread, "frames": frames, "began": began})


def changed_frames(frames: list[tuple[float, bytes]]) -> list[tuple[float, bytes]]:
    """연속 프레임 중 앞 프레임과 달라진 것만 (첫 프레임은 기준이라 항상 남긴다)."""
    kept: list[tuple[float, bytes]] = []
    previous_digest = None
    for at_seconds, data in frames:
        digest = hashlib.sha1(data).hexdigest()
        if digest != previous_digest:
            kept.append((at_seconds, data))
        previous_digest = digest
    return kept


def finish_burst(args) -> dict:
    """동작 뒤 SECONDS 초 더 찍고 마무리 > {"burst": {...}} (--burst 가 없으면 빈 dict)."""
    state = getattr(args, BURST_STATE_ATTRIBUTE, None)
    if not state:
        return {}
    time.sleep(args.burst[0])
    state["stop"].set()
    state["thread"].join(timeout=35)
    frames = list(state["frames"])
    kept = changed_frames(frames)
    folder = shot_folder(project_root(args)) / time.strftime("burst-%Y%m%d-%H%M%S")
    folder.mkdir(parents=True, exist_ok=True)
    files = []
    for number, (at_seconds, data) in enumerate(kept):
        raw = folder / f"f{number:03d}_{at_seconds:06.2f}s.png"
        raw.write_bytes(data)
        final = to_webp(raw, quality=getattr(args, "quality", 80), max_side=getattr(args, "max_side", None) or None) or raw
        files.append({"file": str(final), "at_seconds": at_seconds})
    delattr(args, BURST_STATE_ATTRIBUTE)
    return {"burst": {"captured": len(frames), "changed": len(kept), "folder": str(folder), "frames": files,
                      "is_truncated": len(frames) >= MAXIMUM_BURST_FRAME_COUNT}}
