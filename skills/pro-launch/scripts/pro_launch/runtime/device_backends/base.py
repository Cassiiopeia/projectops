"""Shared device backend contract: capability table · device facts · lifecycle action interface (#953).

Decisions (device_pool) read only capabilities, never platform names. A new platform adds one file following this contract.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

FORM_PHONE = "phone"
FORM_TABLET = "tablet"
FORMS = (FORM_PHONE, FORM_TABLET)


def _version_tuple(version: str | None) -> tuple[int, ...]:
    return tuple(int(part) for part in (version or "").split(".") if part.isdigit())


def is_os_satisfied(os_version: str | None, os_minimum: str | None) -> bool:
    """os_minimum examples: "17" · ">=17.2". With an unknown version, a set condition does not pass."""
    if not os_minimum:
        return True
    minimum = _version_tuple(os_minimum.lstrip(">= "))
    return bool(os_version) and _version_tuple(os_version) >= minimum


@dataclass(frozen=True)
class Capabilities:
    """What the backend can do. Decisions look only at this (phase 3 experiment results are reflected here as one line too)."""

    can_boot: bool = False
    can_shutdown: bool = False
    can_create: bool = False
    can_clone: bool = False
    can_clone_keep_marks: bool = False
    can_readonly_instance: bool = False
    is_physical: bool = False


@dataclass(frozen=True)
class DeviceFacts:
    """Facts read from the device (not stored in the ledger — they go stale).

    key: ledger key (iOS UDID · Android AVD name · physical device serial) · instance: running id (None when off)
    """

    key: str
    platform: str
    backend: str
    name: str
    form: str
    os_version: str | None
    is_booted: bool
    instance: str | None


@dataclass(frozen=True)
class RawCommandPattern:
    """Commands the raw-command blocking hook blocks (regex) · launch_cli command to use instead (#954)."""

    pattern: str
    instead: str


def folder_bytes(folder: Path | None) -> int:
    """Bytes the folder actually takes on disk (by blocks — does not inflate sparse files·APFS clones). 0 if missing."""
    if not folder or not folder.is_dir():
        return 0
    total = 0
    for root, _, files in os.walk(folder):
        for name in files:
            try:
                stat = os.lstat(os.path.join(root, name))
            except OSError:
                continue
            total += getattr(stat, "st_blocks", 0) * 512 or stat.st_size
    return total


def default_device_name(now_text: str) -> str:
    """When create gets no name: pro-launch YYYYMMDD-HHMM (so people can recognize it in lists)."""
    return f"pro-launch {now_text}"


class DeviceBackend(Protocol):
    """Device lifecycle actions for one platform. Unsupported actions are blocked via capabilities."""

    name: str
    platform: str
    capabilities: Capabilities

    def list_devices(self) -> list[DeviceFacts]: ...

    def boot(self, key: str, window: str, scale: float | None) -> dict:
        """> {is_ok, instance, already_booted, detail}"""

    def shutdown(self, key: str, instance: str | None) -> dict:
        """> {is_ok, detail}"""

    def key_of_instance(self, instance: str) -> str | None: ...

    # Only when can_create
    def create(self, name: str, form: str, os_minimum: str | None) -> dict:
        """> {is_ok, key, detail}"""

    # Only when can_clone — the source must be powered off
    def clone(self, key: str, name: str) -> dict:
        """> {is_ok, key, detail}"""

    def erase(self, key: str) -> dict:
        """Erase the data of a powered-off device > {is_ok, detail}"""

    def delete(self, key: str) -> dict:
        """Delete the device > {is_ok, detail}"""

    def raw_command_patterns(self) -> tuple[RawCommandPattern, ...]: ...

    def disk_bytes(self, key: str) -> int:
        """Bytes the device data takes on disk (for cleanup reports)."""
