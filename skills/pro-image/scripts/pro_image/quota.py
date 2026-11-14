"""Tool quota detection: run log + tool conversation log > quota exhausted or not, time until reset
Separates per-minute limits (retry shortly) from weekly exhaustion (move to the next tool)
"""
from __future__ import annotations

import re
from pathlib import Path

from . import providers

QUOTA_MARKERS = ("429", "RESOURCE_EXHAUSTED", "QUOTA_EXHAUSTED", "Too Many Requests")
# Form "reset after 166h53m17s"
RESET_PATTERN = re.compile(r"reset after ((?:\d+h)?(?:\d+m)?(?:\d+s)?)")
# If more than this remains, go to the next tool instead of retrying (seconds)
WAIT_THRESHOLD_SECONDS = 3600
# Tail length to read from the conversation log (characters)
LOG_TAIL_CHARACTERS = 20000


def _seconds(text: str) -> int:
    hours = re.search(r"(\d+)h", text)
    minutes = re.search(r"(\d+)m", text)
    seconds = re.search(r"(\d+)s", text)
    return sum(int(match.group(1)) * unit for match, unit in ((hours, 3600), (minutes, 60), (seconds, 1)) if match)


def diagnose(definition: dict, run_log_text: str, started_at: float) -> dict | None:
    """{is_quota, reset_in_seconds, reset_in} when quota is exhausted, None if no trace"""
    texts = [run_log_text]
    for path in providers.expand_globs(definition.get("failure_log_globs", [])):
        if path.stat().st_mtime >= started_at:
            texts.append(Path(path).read_text(encoding="utf-8", errors="replace")[-LOG_TAIL_CHARACTERS:])
    joined = "\n".join(texts)
    if not any(marker in joined for marker in QUOTA_MARKERS):
        return None
    resets = [_seconds(match) for match in RESET_PATTERN.findall(joined) if match]
    reset_in_seconds = max(resets) if resets else None
    return {"is_quota": True, "reset_in_seconds": reset_in_seconds,
            "reset_in": RESET_PATTERN.findall(joined)[-1] if resets else None}


def next_hint(diagnosis: dict | None) -> str:
    if diagnosis and diagnosis["reset_in_seconds"] and diagnosis["reset_in_seconds"] > WAIT_THRESHOLD_SECONDS:
        return (f"this tool's quota is used up for {diagnosis['reset_in']}: move to the next provider now "
                "and tell the user when it resets")
    return "free plans hit rate limits (429): retry once after 1-2 minutes, then the next provider"
