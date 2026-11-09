"""동작 옵션 정본: 이름, 타입, 허용값, 기본값, 설명 (옵션 추가 = 표 한 줄)"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# config.json 섹션 이름
CONFIG_SECTION = "presentation"

# 값 타입 4개: text, bool, list(쉼표 구분 입력), int
TYPE_TEXT = "text"
TYPE_BOOL = "bool"
TYPE_LIST = "list"
TYPE_INT = "int"


@dataclass(frozen=True)
class OptionDefinition:
    name: str
    value_type: str
    allowed_values: tuple[str, ...]
    default: Any
    description: str
    minimum: int | None = None


OPTION_DEFINITIONS: tuple[OptionDefinition, ...] = (
    OptionDefinition("language", TYPE_TEXT, (), None,
                     "Spoken language for new decks (ko, en, ...); unset = the preferences language, else en"),
    OptionDefinition("time_limit_seconds", TYPE_INT, (), None, "Talk length for new decks", minimum=1),
    OptionDefinition("deck_root", TYPE_TEXT, (), None,
                     "Folder for new decks (relative to the repo or absolute); unset = get-output-path"),
    OptionDefinition("export_formats", TYPE_LIST, ("pdf", "pptx"), ("pdf", "pptx"),
                     "What export makes when no format flag is given"),
    OptionDefinition("whisper_model", TYPE_TEXT, ("tiny", "base", "small", "medium"), "small",
                     "faster-whisper model when a recording has no captions"),
    OptionDefinition("seed_user_memory", TYPE_BOOL, (), True,
                     "Start new decks from ~/.projectops/presentation/memory.md (directions for all talks)"),
    OptionDefinition("auto_open", TYPE_BOOL, (), False, "Open the practice page in the browser on start"),
    OptionDefinition("idle_timeout_minutes", TYPE_INT, (), 120, "Stop the server after this idle time", minimum=1),
)
OPTIONS_BY_NAME = {definition.name: definition for definition in OPTION_DEFINITIONS}
TRUE_WORDS = ("true", "1", "yes", "on")
FALSE_WORDS = ("false", "0", "no", "off")


def default_value(definition: OptionDefinition) -> Any:
    """기본값 > 호출부가 고쳐도 표가 안 바뀌는 사본"""
    return list(definition.default) if isinstance(definition.default, tuple) else definition.default


def is_valid_option_value(name: str, value: Any) -> bool:
    """저장값 검사: 타입, 허용값, 최솟값"""
    definition = OPTIONS_BY_NAME[name]
    if definition.value_type == TYPE_BOOL:
        return isinstance(value, bool)
    if definition.value_type == TYPE_INT:
        is_int = isinstance(value, int) and not isinstance(value, bool)
        return is_int and (definition.minimum is None or value >= definition.minimum)
    if definition.value_type == TYPE_LIST:
        return isinstance(value, list) and bool(value) and all(item in definition.allowed_values for item in value)
    if not isinstance(value, str) or not value.strip():
        return False
    return not definition.allowed_values or value in definition.allowed_values


def parse_option_value(name: str, raw: str) -> Any:
    """명령행 문자열 > 저장값 (잘못되면 ValueError)"""
    definition = OPTIONS_BY_NAME[name]
    text = raw.strip()
    value: Any = text
    if definition.value_type == TYPE_BOOL:
        if text.lower() not in TRUE_WORDS + FALSE_WORDS:
            raise ValueError(f"{name} must be true or false")
        value = text.lower() in TRUE_WORDS
    elif definition.value_type == TYPE_INT:
        try:
            value = int(text)
        except ValueError as error:
            raise ValueError(f"{name} must be a whole number") from error
    elif definition.value_type == TYPE_LIST:
        value = [item.strip() for item in text.split(",") if item.strip()]
    if not is_valid_option_value(name, value):
        allowed = f" ({', '.join(definition.allowed_values)})" if definition.allowed_values else ""
        raise ValueError(f"{name} has an invalid value{allowed}")
    return value


def describe_options() -> list[dict]:
    """config options 응답: 표 전체"""
    return [{**asdict(definition), "default": default_value(definition),
             "allowed_values": list(definition.allowed_values)} for definition in OPTION_DEFINITIONS]
