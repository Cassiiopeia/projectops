"""사람별 표현 설정(preferences) 병합.

스킬마다 제각각 설정 키를 만들면 사용자가 배울 수 없고 문서가 낡는다. 그래서 모양을 하나로
정하고 모든 스킬이 이 함수 하나로 읽는다. 표현(언어·말투·형식)만 다루며, 승인·dry-run 같은
안전 규칙은 여기서 끌 수 없다 — 허용 목록 밖의 키는 values 에 넣지 않고 ignored 로 알린다.
"""
from __future__ import annotations

import re
import subprocess
from typing import Optional

from common import config

COMMON_KEYS = ("language", "tone", "rules")
SKILL_KEYS = ("template", "preset", "examples", "sections")

# 키별 허용 타입. 잘못된 타입을 조용히 쓰면 스킬마다 다르게 깨지므로 들어오는 곳에서 막는다.
_TYPES = {
    "language": str, "tone": str, "template": str, "preset": str,
    "rules": list, "examples": list, "sections": list,
}


def _as_dict(x: object) -> dict:
    """설정 값이 dict 가 아니면 빈 dict 로 본다. 손으로 고친 config 가 깨져도 기본값으로 떨어지게 한다."""
    return x if isinstance(x, dict) else {}


def _take(layer: object, allowed: tuple, label: str, values: dict, sources: dict, ignored: list) -> None:
    if not isinstance(layer, dict):
        return
    for key, val in layer.items():
        typ = _TYPES.get(key)
        if key not in allowed or typ is None or not isinstance(val, typ):
            ignored.append(f"{label}.{key}")
            continue
        if typ is list and not all(isinstance(x, str) for x in val):
            ignored.append(f"{label}.{key}")
            continue
        values[key] = val
        sources[key] = label


def _find_repo(data: dict, owner: Optional[str], repo: Optional[str]) -> Optional[dict]:
    if not owner or not repo:
        return None
    repos = _as_dict(data.get("github")).get("repos")
    if not isinstance(repos, list):
        return None
    for r in repos:
        if not isinstance(r, dict):
            continue
        # remote URL 과 config 의 대소문자가 다른 경우가 흔하다 (GitHub 은 대소문자를 구분하지 않는다)
        if str(r.get("owner", "")).lower() == owner.lower() and str(r.get("repo", "")).lower() == repo.lower():
            return r
    return None


def resolve(skill_id: str, owner: Optional[str] = None, repo: Optional[str] = None,
            data: Optional[dict] = None, *, load: bool = False) -> dict:
    """층을 순서대로 덮어 최종 값과 출처를 돌려준다.

    data 를 안 넘기고 load=True 면 config 파일을 읽는다. 파일이 없거나 깨졌으면 빈 결과.
    """
    if data is None and load:
        data = config.load()
    values: dict = {}
    sources: dict = {}
    ignored: list = []
    if not isinstance(data, dict):
        return {"values": values, "sources": sources, "ignored": ignored}

    skill_allowed = COMMON_KEYS + SKILL_KEYS
    _take(data.get("preferences"), COMMON_KEYS, "preferences", values, sources, ignored)
    _take(_as_dict(data.get("skills")).get(skill_id), skill_allowed, f"skills.{skill_id}", values, sources, ignored)

    entry = _find_repo(data, owner, repo)
    if entry is not None:
        tag = f"repos[{entry.get('owner')}/{entry.get('repo')}]"
        _take(entry.get("preferences"), COMMON_KEYS, f"{tag}.preferences", values, sources, ignored)
        _take(_as_dict(entry.get("skills")).get(skill_id), skill_allowed, f"{tag}.skills.{skill_id}",
              values, sources, ignored)
    return {"values": values, "sources": sources, "ignored": ignored}


_REMOTE = re.compile(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?/?$")


def detect_repo(cwd: Optional[str] = None) -> tuple:
    """origin remote 에서 owner/repo 를 뽑는다. git 이 없거나 remote 가 없으면 (None, None)."""
    try:
        url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=cwd,
                             capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None, None
    m = _REMOTE.search(url)
    return (m.group(1), m.group(2)) if m else (None, None)
