"""도구 한도 판별: 실행 로그 + 도구 대화 기록 > 한도 소진 여부, 재설정까지 남은 시간
분 단위 제한(잠깐 뒤 재시도)과 주 단위 소진(다음 도구로)을 구분하기 위함
"""
from __future__ import annotations

import re
from pathlib import Path

from . import providers

QUOTA_MARKERS = ("429", "RESOURCE_EXHAUSTED", "QUOTA_EXHAUSTED", "Too Many Requests")
# "reset after 166h53m17s" 형태
RESET_PATTERN = re.compile(r"reset after ((?:\d+h)?(?:\d+m)?(?:\d+s)?)")
# 이 시간보다 오래 남았으면 재시도 대신 다음 도구 (초)
WAIT_THRESHOLD_SECONDS = 3600
# 대화 기록에서 읽을 꼬리 길이 (글자)
LOG_TAIL_CHARACTERS = 20000


def _seconds(text: str) -> int:
    hours = re.search(r"(\d+)h", text)
    minutes = re.search(r"(\d+)m", text)
    seconds = re.search(r"(\d+)s", text)
    return sum(int(match.group(1)) * unit for match, unit in ((hours, 3600), (minutes, 60), (seconds, 1)) if match)


def diagnose(definition: dict, run_log_text: str, started_at: float) -> dict | None:
    """한도 소진이면 {is_quota, reset_in_seconds, reset_in}, 흔적이 없으면 None"""
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
