"""브라우저 프로필 고르기: 레포 프로필 · 이 컴퓨터 공용 이름 붙은 프로필 (#956).

레포 프로필은 지금처럼 레포 버킷마다 하나({state_home}/.browser-profile). 레포를 넘어 같은 로그인을 쓰려면
공용 프로필({base}/launch/_machine/browser-profiles/<이름>/)을 쓴다. 고른 프로필은 레포마다 기억한다(web-profile.json).
같은 프로필 폴더는 브라우저 하나만 열 수 있다 — 공용 프로필도 브라우저 하나를 여러 세션이 CDP 로 나눠 쓴다(탭 소유 #878).
로그인 같은 공들인 상태는 기기와 같은 원장에 mark 로 남긴다 (키: browser-profile:<이름> · browser-profile:repo:<버킷>).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from common.state import MACHINE_BUCKET, base_dir

from pro_launch.runtime import device_ledger
from pro_launch.runtime.browser import PROFILE_FOLDER_NAME, WEB_STATE_FILE_NAME, state_path
from pro_launch.runtime.context import state_home

# 공용 프로필을 직접 지정 (레포 기억보다 우선)
PROFILE_ENV_VAR = "LAUNCH_WEB_PROFILE"
# 레포 기억 파일 · 레포 프로필로 돌아가는 이름
PROFILE_CHOICE_FILE = "web-profile.json"
REPO_PROFILE_NAME = "repo"
_PROFILE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,40}$")
MARK_KEY_PREFIX = "browser-profile:"


def shared_profiles_root() -> Path:
    return base_dir() / "launch" / MACHINE_BUCKET / "browser-profiles"


def is_valid_profile_name(name: str) -> bool:
    return bool(_PROFILE_NAME_PATTERN.match(name or "")) and name != REPO_PROFILE_NAME


def chosen_profile(root: Path) -> str | None:
    """이 레포가 쓰는 공용 프로필 이름 (환경변수 > 레포 기억). 레포 프로필이면 None."""
    from_env = (os.environ.get(PROFILE_ENV_VAR) or "").strip()
    if from_env:
        return None if from_env == REPO_PROFILE_NAME else from_env
    try:
        name = json.loads((state_home(root) / PROFILE_CHOICE_FILE).read_text(encoding="utf-8")).get("name")
    except (OSError, json.JSONDecodeError, AttributeError):
        return None
    return name if isinstance(name, str) and is_valid_profile_name(name) else None


def choose_profile(root: Path, name: str | None) -> None:
    """이 레포가 쓸 프로필을 기억한다 (None · repo 면 레포 프로필로)."""
    choice_file = state_home(root) / PROFILE_CHOICE_FILE
    if not name or name == REPO_PROFILE_NAME:
        choice_file.unlink(missing_ok=True)
        return
    choice_file.parent.mkdir(parents=True, exist_ok=True)
    choice_file.write_text(json.dumps({"name": name}, ensure_ascii=False) + "\n", encoding="utf-8")


def profile_home(root: Path) -> Path:
    """프로필 폴더 · 브라우저 상태 · 표준오류 로그가 놓이는 곳."""
    name = chosen_profile(root)
    if not name:
        return state_home(root)
    folder = shared_profiles_root() / name
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def web_state_path(root: Path) -> Path:
    """web 명령이 읽고 쓰는 브라우저 상태 파일 — 공용 프로필이면 그 프로필 자리."""
    return (profile_home(root) / WEB_STATE_FILE_NAME) if chosen_profile(root) else state_path(root)


def profile_mark_key(root: Path, name: str | None = None) -> str:
    """원장 키: 공용이면 browser-profile:<이름>, 레포 프로필이면 browser-profile:repo:<버킷 이름>."""
    chosen = name if name is not None else chosen_profile(root)
    if chosen and chosen != REPO_PROFILE_NAME:
        return f"{MARK_KEY_PREFIX}{chosen}"
    return f"{MARK_KEY_PREFIX}repo:{state_home(root).name}"


def shared_profile_names() -> list[str]:
    """공용 프로필 이름: 폴더가 있는 것 + 원장에 기록만 있는 것 (아직 한 번도 안 띄운 것)."""
    root = shared_profiles_root()
    folders = {p.name for p in root.iterdir() if p.is_dir()} if root.is_dir() else set()
    recorded = {key[len(MARK_KEY_PREFIX):] for key in device_ledger.read_ledger()["devices"]
                if key.startswith(MARK_KEY_PREFIX) and not key.startswith(f"{MARK_KEY_PREFIX}repo:")}
    return sorted(folders | recorded)


def profile_with_marks(root: Path, needs: list[str]) -> str | None:
    """--need 를 모두 가진 프로필: 레포 프로필 > 공용 프로필(이름순) > None. 레포 프로필이면 'repo'."""
    devices = device_ledger.read_ledger()["devices"]

    def has_all(key: str) -> bool:
        labels = {f"{m.get('kind')}:{m.get('name')}" for m in (devices.get(key) or {}).get("marks") or []}
        return all(need in labels for need in needs)

    if has_all(profile_mark_key(root, REPO_PROFILE_NAME)):
        return REPO_PROFILE_NAME
    return next((name for name in shared_profile_names() if has_all(profile_mark_key(root, name))), None)


def all_web_state_files() -> list[Path]:
    """이 컴퓨터의 모든 브라우저 상태 파일 (레포 버킷 · 공용 프로필) — 세션 종료 정리용."""
    launch_root = base_dir() / "launch"
    if not launch_root.is_dir():
        return []
    return sorted(set(launch_root.glob(f"*/{WEB_STATE_FILE_NAME}")) | set(launch_root.glob(f"*/*/{WEB_STATE_FILE_NAME}"))
                  | set(shared_profiles_root().glob(f"*/{WEB_STATE_FILE_NAME}")))


def other_session_tabs(state: dict, session: str) -> list[str]:
    """상태의 탭 기록 중 다른 세션 것 (키: 탭이름@세션)."""
    return [key for key in (state.get("tab_marks") or {}) if not key.endswith(f"@{session}")]


