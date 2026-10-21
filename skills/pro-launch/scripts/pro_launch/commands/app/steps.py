"""`app run` 의 단계 파일: 읽기 > 엄격한 검증 > Maestro 명령으로 옮기기 > Maestro 출력에서 단계별 결과 읽기.

기기 없이 도는 순수 함수만 둔다. 실행(기기·백엔드)은 actions/run.py.

단계 모양 (JSON 배열, 한 원소에 키 하나):
  {"tap": {"text": "로그인"}} · {"tap": {"id": "login_button"}} · {"tap": {"desc": "닫기", "index": 1}}
  {"tap": {"point": "0.5,0.8"}}                     — 비율 좌표 (요소가 없는 화면만)
  {"swipe": {"direction": "up"}} · {"swipe": {"from": "0.5,0.8", "to": "0.5,0.2", "ms": 300}}
  {"type": {"env": "PW", "submit": true}} · {"type": {"cred": "staging", "field": "account"}}
  {"wait": {"text": "홈", "timeout": 10}}           — 보일 때까지 (초)
  {"gone": {"text": "로드 중"}} · {"wait": {"text": "로드 중", "gone": true}} — 사라질 때까지 (#928)
  {"back": true}                                    — Android 만
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import app_input

# 한 번에 받는 단계 수 상한 — 긴 시나리오는 프로젝트의 Maestro flow 로 돌린다
MAXIMUM_STEP_COUNT = 50
# wait 기본 · 최대 대기 (초)
DEFAULT_WAIT_SECONDS = 10
MAXIMUM_WAIT_SECONDS = 60
# swipe 시간 범위 (ms)
MINIMUM_SWIPE_MILLISECONDS, MAXIMUM_SWIPE_MILLISECONDS = 50, 10000
# 단계별 입력값을 Maestro 에 넘기는 환경변수: MAESTRO_PRO_LAUNCH_STEP_{번호}_TEXT (MAESTRO_ 접두만 flow 로 넘어간다)
STEP_TEXT_ENV_FORMAT = "MAESTRO_PRO_LAUNCH_STEP_{index}_TEXT"
# Maestro 평문 출력의 명령 한 줄: '<설명>... COMPLETED|FAILED|SKIPPED|WARNED'
MAESTRO_STATUS_LINE = re.compile(r"^(?P<description>.*?)\.\.\. (?P<status>COMPLETED|FAILED|SKIPPED|WARNED)\s*$")

# 단계 종류 > 받는 키
STEP_FIELDS = {
    "tap": {"text", "id", "desc", "point", "index"},
    "swipe": {"direction", "from", "to", "ms"},
    "type": {"env", "cred", "field", "submit"},
    "wait": {"text", "id", "desc", "timeout", "gone"},
    "gone": {"text", "id", "desc", "timeout"},
    "back": set(),
}


class StepsError(Exception):
    """단계 파일 거부. step_index 는 몇 번째 단계인지 (파일 전체 문제면 None)."""

    def __init__(self, message: str, step_index: int | None = None):
        super().__init__(message)
        self.step_index = step_index


def load_steps(path: str | None) -> list[dict]:
    """단계 파일 > 정규화된 단계 목록. 무엇이든 어긋나면 StepsError (몇 번째인지 포함)."""
    if not path:
        raise StepsError("--steps <JSON file> is required")
    try:
        raw_steps = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as e:
        raise StepsError(f"Could not read the steps file: {e}") from e
    except ValueError as e:
        raise StepsError(f"Not JSON: {e}") from e
    if not isinstance(raw_steps, list) or not raw_steps:
        raise StepsError("The steps file must be a non-empty JSON array")
    if len(raw_steps) > MAXIMUM_STEP_COUNT:
        raise StepsError(f"At most {MAXIMUM_STEP_COUNT} steps (got {len(raw_steps)})")
    return [_normalize_step(raw_step, index) for index, raw_step in enumerate(raw_steps)]


def _normalize_step(raw_step, index: int) -> dict:
    """단계 하나 검증 > {"kind": ..., 정리된 값}."""
    if not isinstance(raw_step, dict) or len(raw_step) != 1:
        raise StepsError('A step is an object with one key (e.g. {"tap": {"text": "Log in"}})', index)
    (kind, params), = raw_step.items()
    if kind not in STEP_FIELDS:
        raise StepsError(f"Unknown step {kind!r} — accepted: {', '.join(STEP_FIELDS)}", index)
    if kind == "back":
        if params not in (True, {}, None):
            raise StepsError('Write back as {"back": true}', index)
        return {"kind": "back"}
    if not isinstance(params, dict):
        raise StepsError(f"The value of {kind} must be an object", index)
    unknown = set(params) - STEP_FIELDS[kind]
    if unknown:
        raise StepsError(f"Unknown keys in {kind}: {sorted(unknown)} — accepted: {sorted(STEP_FIELDS[kind])}", index)
    if kind == "gone":
        # gone 은 wait + gone 의 줄임 — 실행·Maestro 변환은 wait 한 갈래로 간다
        return {"kind": "wait", **_wait({**params, "gone": True}, index)}
    return {"kind": kind, **_NORMALIZERS[kind](params, index)}


def _selector_of(params: dict, index: int, kind: str) -> tuple[str, str] | None:
    """text·id·desc 중 정확히 하나 > (필드, 값). 하나도 없으면 None."""
    given = [(f, params[f]) for f in app_input.SELECTOR_FIELDS if f in params]
    if len(given) > 1:
        raise StepsError(f"{kind}: use only one of text · id · desc", index)
    if given and (not isinstance(given[0][1], str) or not given[0][1]):
        raise StepsError(f"{kind}: {given[0][0]} must be a non-empty string", index)
    return given[0] if given else None


def _ratio_of(raw, index: int, label: str) -> tuple[float, float]:
    """'0.5,0.8' 또는 [0.5, 0.8] > (x, y). 0~1 밖(픽셀)이면 거부."""
    text = ",".join(str(v) for v in raw) if isinstance(raw, list) else raw
    ratio = app_input.parse_ratio(text) if isinstance(text, str) else None
    if not ratio:
        raise StepsError(f"{label} is a 0–1 ratio coordinate (e.g. \"0.5,0.8\"). Pixels are not accepted", index)
    return ratio


def _tap(params: dict, index: int) -> dict:
    selector = _selector_of(params, index, "tap")
    has_point = "point" in params
    if bool(selector) == has_point:
        raise StepsError("tap: needs one of text · id · desc, or one point", index)
    tap_index = params.get("index", 0)
    if not isinstance(tap_index, int) or isinstance(tap_index, bool) or tap_index < 0:
        raise StepsError("tap: index must be an integer of 0 or more", index)
    if has_point:
        if "index" in params:
            raise StepsError("tap: index is only used with text · id · desc", index)
        return {"point": _ratio_of(params["point"], index, "tap.point")}
    return {"field": selector[0], "value": selector[1], "index": tap_index}


def _swipe(params: dict, index: int) -> dict:
    milliseconds = params.get("ms", 300)
    if (not isinstance(milliseconds, int) or isinstance(milliseconds, bool)
            or not MINIMUM_SWIPE_MILLISECONDS <= milliseconds <= MAXIMUM_SWIPE_MILLISECONDS):
        raise StepsError(f"swipe: ms must be an integer from {MINIMUM_SWIPE_MILLISECONDS} to {MAXIMUM_SWIPE_MILLISECONDS}", index)
    if "direction" in params:
        if "from" in params or "to" in params:
            raise StepsError("swipe: do not use direction together with from/to", index)
        if params["direction"] not in app_input.SWIPE_DIRS:
            raise StepsError(f"swipe: direction must be one of {sorted(app_input.SWIPE_DIRS)}", index)
        start, end = app_input.SWIPE_DIRS[params["direction"]]
        return {"start": start, "end": end, "ms": milliseconds, "label": params["direction"]}
    if "from" not in params or "to" not in params:
        raise StepsError("swipe: needs direction or from+to", index)
    start, end = _ratio_of(params["from"], index, "swipe.from"), _ratio_of(params["to"], index, "swipe.to")
    return {"start": start, "end": end, "ms": milliseconds, "label": f"{params['from']}→{params['to']}"}


def _type(params: dict, index: int) -> dict:
    # 값은 파일에 적지 않는다 — 환경변수 이름이나 저장된 자격증명 이름만 받는다
    has_env, has_cred = "env" in params, "cred" in params
    if has_env == has_cred:
        raise StepsError("type: needs env (environment variable name) or cred (saved credential name) "
                         "— do not write the value into the steps file", index)
    source = params["env"] if has_env else params["cred"]
    if not isinstance(source, str) or not source:
        raise StepsError("type: env · cred must be a non-empty name", index)
    if has_env and "field" in params:
        raise StepsError("type: field is only used with cred", index)
    if not isinstance(params.get("submit", False), bool):
        raise StepsError("type: submit must be true/false", index)
    return {"env": source if has_env else None, "cred": None if has_env else source,
            "field": params.get("field"), "submit": params.get("submit", False)}


def _wait(params: dict, index: int) -> dict:
    selector = _selector_of(params, index, "wait")
    if not selector:
        raise StepsError("wait: needs one of text · id · desc", index)
    timeout = params.get("timeout", DEFAULT_WAIT_SECONDS)
    if (not isinstance(timeout, (int, float)) or isinstance(timeout, bool)
            or not 0 < timeout <= MAXIMUM_WAIT_SECONDS):
        raise StepsError(f"wait: timeout must be seconds above 0 and at most {MAXIMUM_WAIT_SECONDS}", index)
    if not isinstance(params.get("gone", False), bool):
        raise StepsError("wait: gone must be true/false", index)
    return {"field": selector[0], "value": selector[1], "timeout": timeout, "gone": params.get("gone", False)}


_NORMALIZERS = {"tap": _tap, "swipe": _swipe, "type": _type, "wait": _wait}


def step_label(step: dict) -> str:
    """사람이 읽을 단계 이름. type 은 값이 아니라 출처 이름만 보인다."""
    kind = step["kind"]
    if kind == "wait" and step.get("gone"):
        return f"wait gone {step['field']}={step['value']!r}"
    if kind in ("tap", "wait") and "field" in step:
        return f"{kind} {step['field']}={step['value']!r}"
    if kind == "tap":
        return f"tap at {step['point'][0]},{step['point'][1]}"
    if kind == "swipe":
        return f"swipe {step['label']}"
    if kind == "type":
        return f"type env {step['env']}" if step["env"] else f"type cred {step['cred']}"
    return kind


# ── iOS: 단계 > Maestro 명령 ─────────────────────────────────────────────

def maestro_selector(field: str, value: str) -> dict:
    # Maestro 의 text·id 는 정규식이다 — 괄호·물음표가 든 문구도 그대로 맞춘다. desc 는 iOS 에서 문구로 잡힌다
    return {"id" if field == "id" else "text": re.escape(value)}


def to_maestro_commands(step: dict, index: int) -> list[dict]:
    """단계 하나 > Maestro 명령 목록 (type+submit 처럼 둘이 될 수 있다). back 은 iOS 에 없어 부르기 전에 거른다."""
    kind = step["kind"]
    if kind == "tap" and "point" in step:
        return [{"tapOn": {"point": app_input.pct(step["point"])}}]
    if kind == "tap":
        selector = maestro_selector(step["field"], step["value"])
        return [{"tapOn": {**selector, **({"index": step["index"]} if step["index"] else {})}}]
    if kind == "swipe":
        return [{"swipe": {"start": app_input.pct(step["start"]), "end": app_input.pct(step["end"]),
                           "duration": step["ms"]}}]
    if kind == "type":
        commands = [{"inputText": "${" + STEP_TEXT_ENV_FORMAT.format(index=index) + "}"}]
        return commands + ([{"pressKey": "Enter"}] if step["submit"] else [])
    if kind == "wait":
        condition = "notVisible" if step.get("gone") else "visible"
        return [{"extendedWaitUntil": {condition: maestro_selector(step["field"], step["value"]),
                                       "timeout": int(step["timeout"] * 1000)}}]
    raise ValueError(f"Step cannot be converted to Maestro: {kind}")


def maestro_statuses(lines: list[str]) -> list[tuple[str, str]]:
    """Maestro 평문 출력 > 명령별 (설명, 상태) 순서대로."""
    found = []
    for line in lines:
        match = MAESTRO_STATUS_LINE.match(line.strip())
        if match:
            found.append((match.group("description"), match.group("status")))
    return found


def step_statuses(command_counts: list[int], statuses: list[tuple[str, str]]) -> list[str]:
    """명령별 상태 > 단계별 상태 (completed · failed · not_run). 명령 수로 단계 경계를 나눈다."""
    results, cursor = [], 0
    for count in command_counts:
        own = [status for _, status in statuses[cursor:cursor + count]]
        cursor += count
        if "FAILED" in own:
            results.append("failed")
        elif len(own) == count and all(s in ("COMPLETED", "WARNED") for s in own):
            results.append("completed")
        else:
            results.append("not_run")
    return results
