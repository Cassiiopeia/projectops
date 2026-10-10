"""
사용자 config(`~/.projectops/config/config.json`)를 읽고 쓰는 모듈.

config는 글로벌 단일 파일 하나로만 관리하며, skill_id를 최상위 키로 네임스페이스를 나눈다.
예) config["github"]["global_pat"], config["launch"]["credentials"]

자세한 스키마는 skills/references/config-rules.md 와 skills/config.json.example 참조.
"""

import json
import shutil
from pathlib import Path
from typing import Any, Optional


def config_path() -> Path:
    """
    글로벌 단일 config 파일 경로(`~/.projectops/config/config.json`)를 반환한다.

    #459 네임스페이스 중립화로 config 홈이 `~/.suh-template` → `~/.projectops`로 이주됐다.
    기존 사용자의 config가 구 경로에만 있으면 첫 접근 시 신 경로로 1회 복사한다
    (구 파일은 롤백 대비 남겨둠 — 무손실 이주).
    """
    new = Path.home() / ".projectops" / "config" / "config.json"
    old = Path.home() / ".suh-template" / "config" / "config.json"
    if not new.exists() and old.exists():
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old, new)
    return new


def load() -> Optional[dict]:
    """config.json 전체를 dict로 읽어 반환한다. 파일이 없거나 깨졌으면 None."""
    path = config_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def get_section(skill_id: str) -> Optional[dict]:
    """특정 skill_id 섹션(예: config["github"])을 반환한다. 없으면 None."""
    data = load()
    if not isinstance(data, dict):
        return None
    section = data.get(skill_id)
    return section if isinstance(section, dict) else None


def get_github_pat(owner: Optional[str] = None, repo: Optional[str] = None) -> Optional[str]:
    """
    GitHub PAT를 config에서 결정해 반환한다.

    우선순위(config-rules.md §3):
      1. owner/repo가 주어지면 repos 배열에서 일치하는 항목의 pat(non-null)
      2. 위가 없으면 global_pat
    PAT를 찾을 수 없으면 None.
    """
    section = get_section("github")
    if not section:
        return None

    # 1. repo별 개별 PAT 우선
    if owner and repo:
        for r in section.get("repos", []) or []:
            if r.get("owner") == owner and r.get("repo") == repo and r.get("pat"):
                return r["pat"]

    # 2. 공용 global_pat 폴백
    return section.get("global_pat") or None


def save(data: dict) -> Path:
    """
    config.json 전체를 저장하고 경로를 반환한다.

    주의: 부분 수정 시 반드시 load()로 전체를 먼저 읽어 병합한 뒤 호출한다
    (다른 섹션을 날리지 않도록).
    """
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
