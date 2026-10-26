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
# 기준 호출(anchor) 창: 기준 결과 원문 상한, 흐름 결과 상한, 에이전트 말 상한, 앞쪽 상태 명령 수 (#1000)
ANCHOR_RESULT_MAX_CHARS = 20000
FLOW_RESULT_MAX_CHARS = 2000
AGENT_NOTE_MAX_CHARS = 500
SETUP_COMMANDS_KEPT = 10


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


def build_excerpt(events: list[dict], last: int = 40, max_chars: int = 4000, around: str | None = None,
                  anchor_tool_use_id: str | None = None, window: int = 8) -> dict:
    """projectops 호출 기준 발췌 (마지막 last 개, 또는 around 글이 나온 곳 중심) + 기준 호출 창(anchor_*). redactions 에 가린 종류별 개수"""
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
    anchor_part = build_anchor_window(events, results_by_id, anchor_tool_use_id, window, redactions)
    return {**anchor_part, "steps": steps, "user_messages": user_messages[-last:] if last > 0 else [],
            "skills_seen": skills_seen, "images": _image_paths(events, start_index),
            "total_projectops_calls": len(calls), "around_matched": is_around_matched, "redactions": redactions}


def build_anchor_window(events: list[dict], results_by_id: dict, anchor_tool_use_id: str | None, window: int,
                        redactions: dict) -> dict:
    """기준 호출 > {anchor_matched, anchor(결과 원문), flow(앞뒤 모든 도구 호출), agent_notes, setup_commands}"""
    tool_uses = [e for e in events if e["kind"] == "tool_use"]
    position = next((i for i, e in enumerate(tool_uses) if anchor_tool_use_id and e["tool_use_id"] == anchor_tool_use_id), None)
    if position is None:
        return {"anchor_matched": False}

    def clipped(text: str, limit: int) -> tuple[str, bool]:
        value, is_truncated, counts = _clip(text, limit)
        _merge_counts(redactions, counts)
        return value, is_truncated

    # 기준 호출 (결과는 원문 그대로, 상한만)
    anchor_event = tool_uses[position]
    command, _ = clipped(anchor_event["text"], ANCHOR_RESULT_MAX_CHARS)
    result, is_truncated = clipped(results_by_id.get(anchor_event["tool_use_id"], ""), ANCHOR_RESULT_MAX_CHARS)
    anchor = {"index": anchor_event["index"], "tool": anchor_event["tool_name"], "command": command,
              "result": result, "truncated": is_truncated}

    # 앞뒤 흐름 (projectops 여부 무관 · 우회 명령 포함)
    flow = []
    for event in tool_uses[max(0, position - window):position + window + 1]:
        flow_command, _ = clipped(event["text"], FLOW_RESULT_MAX_CHARS)
        flow_result, flow_truncated = clipped(results_by_id.get(event["tool_use_id"], ""), FLOW_RESULT_MAX_CHARS)
        flow.append({"index": event["index"], "tool": event["tool_name"], "is_anchor": event is anchor_event,
                     "command": flow_command, "result": flow_result, "truncated": flow_truncated})

    # 같은 구간 에이전트 말 (무엇을 하려 했는지)
    start_index, end_index = flow[0]["index"], flow[-1]["index"]
    agent_notes = []
    for event in events:
        if event["kind"] == "assistant_text" and start_index <= event["index"] <= end_index and event["text"].strip():
            note, _ = clipped(event["text"], AGENT_NOTE_MAX_CHARS)
            agent_notes.append({"index": event["index"], "text": note})

    # 기준 이전 projectops 명령 (상태를 만든 명령: web open · device 등)
    setup_commands = []
    for event in tool_uses[:position]:
        if event["tool_name"] != "Skill" and is_projectops_command(event["text"]):
            setup_command, _ = clipped(event["text"], FLOW_RESULT_MAX_CHARS)
            setup_result, _ = clipped(results_by_id.get(event["tool_use_id"], ""), 300)
            setup_commands.append({"index": event["index"], "command": setup_command, "result_head": setup_result})
    return {"anchor_matched": True, "anchor": anchor, "flow": flow, "agent_notes": agent_notes,
            "setup_commands": setup_commands[-SETUP_COMMANDS_KEPT:]}
