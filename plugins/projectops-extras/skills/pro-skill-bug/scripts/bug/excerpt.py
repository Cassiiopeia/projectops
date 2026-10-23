"""세션 이벤트 > 이슈용 발췌: projectops 명령·결과 짝, 그 뒤 사용자 말, 쓴 스킬, 이미지 경로 (전부 가린 뒤)"""
from __future__ import annotations

import re
from pathlib import Path

from bug.redact import redact_text

# projectops 명령으로 보는 표식 (스킬 CLI · 고정 진입점)
PROJECTOPS_COMMAND_MARKERS = ("launch_cli.py", "projectops_cli.py", "_cli.py", "/.projectops/")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif")
# 왼쪽 경계: URL 조각(//host/…) · 단어 중간 경로 제외
IMAGE_PATH_RE = re.compile(r"(?<![\w/:.])(~?/[^\s\"'<>|;]+?\.(?:png|jpe?g|webp|gif))\b", re.IGNORECASE)
# 결과를 통째로 빼는 명령 (projectops 설정 = PAT · 서버 비밀번호)
OMITTED_COMMAND_MARKERS = (".projectops/config",)
OMITTED_RESULT = "<omitted: projectops config file>"
# --around 창 뒤에 붙일 사용자 반응 수
USER_REACTIONS_AFTER_WINDOW = 3


def is_projectops_command(text: str) -> bool:
    return any(marker in text for marker in PROJECTOPS_COMMAND_MARKERS)


def _clip(text: str, max_chars: int) -> tuple[str, bool, dict]:
    """가리기 > 글자 상한 자르기 > (글, 잘림 여부, 가린 개수)"""
    redacted, counts = redact_text(text or "")
    return redacted[:max_chars], len(redacted) > max_chars, counts


def _merge_counts(total: dict, counts: dict) -> None:
    for kind, hits in counts.items():
        total[kind] = total.get(kind, 0) + hits


def _image_paths(events: list[dict], start_index: int) -> list[dict]:
    """명령 · 결과에 나온 이미지 경로 중 실제 있는 파일만 (캡처 경로는 결과 JSON 에 나온다)"""
    seen, images = set(), []
    for event in events:
        if event["kind"] not in ("tool_use", "tool_result") or event["index"] < start_index:
            continue
        for raw in IMAGE_PATH_RE.findall(event["text"]):
            if raw in seen or not Path(raw).expanduser().is_file():
                continue
            seen.add(raw)
            images.append({"index": event["index"], "path": raw, "exists": True})
    return images


def _user_messages(events: list[dict], start_index: int, end_index: int | None) -> list[dict]:
    """창 안 사용자 말 + 창 뒤 반응 몇 건 (end_index 없으면 start 이후 전부)"""
    picked, after_window = [], 0
    for event in events:
        if event["kind"] != "user" or event["index"] <= start_index:
            continue
        if end_index is not None and event["index"] > end_index:
            if after_window >= USER_REACTIONS_AFTER_WINDOW:
                break
            after_window += 1
        picked.append(event)
    return picked


def _select_calls(calls: list[dict], results_by_id: dict, last: int, around: str | None) -> tuple[list[dict], bool]:
    """around 가 있으면 처음 걸린 호출 앞뒤로 last 개(앞 절반), 없거나 안 걸리면 마지막 last 개"""
    if last <= 0:
        return [], False
    if around:
        for position, call in enumerate(calls):
            if around in call["text"] or around in results_by_id.get(call["tool_use_id"], ""):
                start = max(0, position - last // 2)
                return calls[start:start + last], True
    return calls[-last:], False


def build_excerpt(events: list[dict], last: int = 40, max_chars: int = 4000, around: str | None = None) -> dict:
    """projectops 호출 기준 발췌 (마지막 last 개, 또는 around 글이 나온 곳 중심). redactions 에 가린 종류별 개수"""
    results_by_id = {e["tool_use_id"]: e["text"] for e in events if e["kind"] == "tool_result" and e["tool_use_id"]}
    calls = [e for e in events if e["kind"] == "tool_use" and e["tool_name"] != "Skill" and is_projectops_command(e["text"])]
    recent_calls, is_around_matched = _select_calls(calls, results_by_id, last, around)
    result_index_by_id = {e["tool_use_id"]: e["index"] for e in events if e["kind"] == "tool_result" and e["tool_use_id"]}
    end_index = None
    if is_around_matched:
        last_call = recent_calls[-1]
        end_index = result_index_by_id.get(last_call["tool_use_id"], last_call["index"])
    redactions: dict = {}

    # 명령 · 결과 짝
    steps = []
    for call in recent_calls:
        command, _, counts = _clip(call["text"], max_chars)
        _merge_counts(redactions, counts)
        raw_result = results_by_id.get(call["tool_use_id"], "")
        if any(marker in call["text"] for marker in OMITTED_COMMAND_MARKERS):
            raw_result = OMITTED_RESULT
        result, is_truncated, counts = _clip(raw_result, max_chars)
        _merge_counts(redactions, counts)
        steps.append({"index": call["index"], "command": command, "result": result, "truncated": is_truncated})

    # 첫 명령 이후 사용자 말 (도구 결과 제외)
    start_index = recent_calls[0]["index"] if recent_calls else 0
    user_messages = []
    for event in _user_messages(events, start_index, end_index):
        if event["text"].strip():
            text, _, counts = _clip(event["text"], max_chars)
            _merge_counts(redactions, counts)
            user_messages.append({"index": event["index"], "text": text})

    skills_seen = list(dict.fromkeys(e["text"] for e in events if e["tool_name"] == "Skill" and e["text"]))
    return {"steps": steps, "user_messages": user_messages[-last:] if last > 0 else [],
            "skills_seen": skills_seen, "images": _image_paths(events, start_index),
            "total_projectops_calls": len(calls), "around_matched": is_around_matched, "redactions": redactions}
