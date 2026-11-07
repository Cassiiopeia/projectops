"""동작 옵션 정본: 이름, 타입, 허용값, 기본값, 설명 (옵션 추가 = 표 한 줄)"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# config.json 섹션: 현재 이름 <-> 읽기만 하는 옛 이름
CONFIG_SECTION = "ui-design"
LEGACY_CONFIG_SECTION = "design_brief"

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
    OptionDefinition("destination", TYPE_TEXT, ("issue", "html", "markdown"), None,
                     "Where a design request goes"),
    OptionDefinition("designer", TYPE_TEXT, (), None, "Designer's GitHub ID or name"),
    OptionDefinition("auto_approve", TYPE_BOOL, (), False, "Skip the confirmation before posting"),
    OptionDefinition("default_fidelity", TYPE_TEXT, ("html", "render", "capture"), "html",
                     "Fidelity to start from when the request does not say"),
    OptionDefinition("devices", TYPE_LIST, ("phone", "tablet", "desktop"), ("phone", "tablet", "desktop"),
                     "Device frames offered in the viewer"),
    OptionDefinition("themes", TYPE_LIST, ("light", "dark"), ("light", "dark"), "Themes offered in the viewer"),
    OptionDefinition("motion_format", TYPE_TEXT, ("gif", "frames"), "gif", "How motion is shared on an issue"),
    OptionDefinition("idle_timeout_minutes", TYPE_INT, (), 240, "Stop the server after this idle time", minimum=1),
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
        return (isinstance(value, list) and bool(value)
                and all(item in definition.allowed_values for item in value))
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
        raise ValueError(describe_allowed_values(definition))
    return value


def describe_allowed_values(definition: OptionDefinition) -> str:
    if definition.allowed_values:
        return f"{definition.name} must use: {', '.join(definition.allowed_values)}"
    if definition.minimum is not None:
        return f"{definition.name} must be at least {definition.minimum}"
    return f"{definition.name} has an invalid value"


def describe_options() -> list[dict]:
    """config options 응답: 표 전체"""
    return [{**asdict(definition), "default": default_value(definition),
             "allowed_values": list(definition.allowed_values)} for definition in OPTION_DEFINITIONS]
