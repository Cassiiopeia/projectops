"""`--burst SECONDS[:INTERVAL]` — capture continuously from before the action and keep only changed frames (#928).

Flow: start capture thread before the action > action > capture SECONDS more > drop identical screens > save frame files.
Capture starts first to avoid "the tap ran before the capture". Comparison uses byte hashes (works without Pillow).
"""
from __future__ import annotations

import argparse
import hashlib
import threading
import time

from common.image import to_webp

from pro_launch.runtime.context import project_root
from pro_launch.runtime.shots import shot_folder

# Max extra capture time after the action (seconds), default and minimum capture interval (seconds), max frames collected (interval grows on slow devices)
MAXIMUM_BURST_SECONDS = 30.0
DEFAULT_BURST_INTERVAL_SECONDS = 0.4
MINIMUM_BURST_INTERVAL_SECONDS = 0.1
MAXIMUM_BURST_FRAME_COUNT = 150
# Name of the progress state quietly attached to args (lives only within one call)
BURST_STATE_ATTRIBUTE = "_burst_state"


def burst_spec(raw: str) -> tuple[float, float]:
    """'3' or '5:0.3' > (extra seconds to capture, interval seconds). For argparse type."""
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
    """Start the capture thread if --burst is given. Otherwise do nothing."""
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
    """Only frames that differ from the previous one (the first frame is the baseline and always kept)."""
    kept: list[tuple[float, bytes]] = []
    previous_digest = None
    for at_seconds, data in frames:
        digest = hashlib.sha1(data).hexdigest()
        if digest != previous_digest:
            kept.append((at_seconds, data))
        previous_digest = digest
    return kept


def finish_burst(args) -> dict:
    """Capture SECONDS more after the action and finish > {"burst": {...}} (empty dict without --burst)."""
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
