"""실행 중인 스크립트가 속한 projectops 버전 — 실패 응답 · doctor 가 싣는다 (#863).

찾는 순서 3개: 플러그인 루트 version.yml > .claude-plugin/plugin.json > 경로의 버전 폴더
레포 체크아웃·플러그인 캐시(~/.claude/plugins/cache/<마켓>/projectops/<버전>/) 모두 루트에 version.yml 이 있다.
"""
from __future__ import annotations

import functools
import json
import re
from pathlib import Path

# 플러그인 루트: <루트>/skills/pro-launch/scripts/pro_launch/runtime/plugin_version.py
PLUGIN_ROOT_DEPTH = 5
UNKNOWN_VERSION = "unknown"
VERSION_LINE = re.compile(r'^version:\s*["\']?([0-9][^"\'\s#]*)', re.MULTILINE)
VERSION_FOLDER = re.compile(r"^\d+\.\d+\.\d+$")


@functools.lru_cache(maxsize=1)
def plugin_version() -> str:
    """버전 문자열. 못 찾으면 'unknown' (프로세스당 1회만 계산)."""
    here = Path(__file__).resolve()
    if len(here.parents) <= PLUGIN_ROOT_DEPTH:
        return UNKNOWN_VERSION
    plugin_root = here.parents[PLUGIN_ROOT_DEPTH]
    return (_from_version_yml(plugin_root) or _from_manifest(plugin_root)
            or _from_path(here) or UNKNOWN_VERSION)


def _from_version_yml(plugin_root: Path) -> str | None:
    try:
        match = VERSION_LINE.search((plugin_root / "version.yml").read_text(encoding="utf-8"))
    except OSError:
        return None
    return match.group(1) if match else None


def _from_manifest(plugin_root: Path) -> str | None:
    try:
        manifest = json.loads((plugin_root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    version = manifest.get("version") if isinstance(manifest, dict) else None
    return str(version) if version else None


def _from_path(here: Path) -> str | None:
    """경로에서 가장 안쪽의 x.y.z 폴더 이름 (캐시 폴더 구조만 남은 설치)."""
    return next((part for part in reversed(here.parts) if VERSION_FOLDER.match(part)), None)


# 더 새 설치본 안내 {running, installed, use} — launch_cli 가 시작 때 넣고 첫 응답 하나가 가져간다 (#920)
_NEWER_INSTALLED: dict = {}


def set_newer_installed(info: dict | None) -> None:
    """launch_resolver.newer_installed_info 결과 보관 (None 이면 아무것도 안 함)"""
    if info:
        _NEWER_INSTALLED["info"] = dict(info)


def take_newer_installed() -> dict | None:
    """보관한 안내를 꺼냄 — 프로세스당 1회 (두 번째부터 None)"""
    return _NEWER_INSTALLED.pop("info", None)
