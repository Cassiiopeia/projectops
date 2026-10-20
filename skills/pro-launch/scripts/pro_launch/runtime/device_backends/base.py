"""기기 백엔드 공통 계약: 능력 표 · 기기 사실 · 수명 동작 인터페이스 (#953).

판정(device_pool)은 플랫폼 이름이 아니라 capabilities 만 읽는다. 새 플랫폼은 이 계약을 따르는 파일 하나를 더한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

FORM_PHONE = "phone"
FORM_TABLET = "tablet"
FORMS = (FORM_PHONE, FORM_TABLET)


@dataclass(frozen=True)
class Capabilities:
    """백엔드가 할 수 있는 것. 판정은 이 값만 본다 (3단계 실험 결과도 여기 한 줄로 반영)."""

    can_boot: bool = False
    can_shutdown: bool = False
    can_create: bool = False
    can_clone: bool = False
    can_clone_keep_marks: bool = False
    can_readonly_instance: bool = False
    is_physical: bool = False


@dataclass(frozen=True)
class DeviceFacts:
    """기기에서 읽어 아는 사실 (원장에 저장하지 않는다 — 낡기 때문).

    key: 원장 키 (iOS UDID · Android AVD 이름 · 실기기 시리얼) · instance: 실행 중 id (꺼져 있으면 None)
    """

    key: str
    platform: str
    backend: str
    name: str
    form: str
    os_version: str | None
    is_booted: bool
    instance: str | None


class DeviceBackend(Protocol):
    """플랫폼 하나의 기기 수명 동작. 지원하지 않는 동작은 capabilities 로 막는다."""

    name: str
    platform: str
    capabilities: Capabilities

    def list_devices(self) -> list[DeviceFacts]: ...

    def boot(self, key: str, window: str, scale: float | None) -> dict:
        """> {is_ok, instance, already_booted, detail}"""

    def shutdown(self, key: str, instance: str | None) -> dict:
        """> {is_ok, detail}"""

    def key_of_instance(self, instance: str) -> str | None: ...
