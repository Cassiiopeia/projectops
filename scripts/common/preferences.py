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


# 스킬 이름 > 옛 이름 (설정 키 skills.<옛 이름> 폴백 — 새 이름 키가 있으면 그쪽 우선)
PREVIOUS_SKILL_IDS = {"pro-code-consult": ("pro-architecture-consult",)}


def _skill_layer(skills: object, skill_id: str) -> tuple:
    """skills 맵 > (설정 층, 실제 키): 새 이름 먼저, 없으면 옛 이름 (#912)"""
    skills = _as_dict(skills)
    for key in (skill_id, *PREVIOUS_SKILL_IDS.get(skill_id, ())):
        if key in skills:
            return skills[key], key
    return None, skill_id


# 형식을 정하는 키 쌍. 한 층이 둘 중 하나라도 정하면 앞 층의 쌍을 통째로 버린다 —
# 그렇지 않으면 레포 층의 preset 이 전역 template 에 늘 져서 "레포마다 다른 형식"을 쓸 수 없다.
FORMAT_KEYS = ("template", "preset")


def _valid(key: str, val: object, allowed: tuple) -> bool:
    typ = _TYPES.get(key)
    if key not in allowed or typ is None or not isinstance(val, typ):
        return False
    return not (typ is list and not all(isinstance(x, str) for x in val))


def _take(layer: object, allowed: tuple, label: str, values: dict, sources: dict, ignored: list) -> None:
    if not isinstance(layer, dict):
        return
    if any(k in FORMAT_KEYS and _valid(k, v, allowed) for k, v in layer.items()):
        for k in FORMAT_KEYS:
            values.pop(k, None)
            sources.pop(k, None)
    for key, val in layer.items():
        if not _valid(key, val, allowed):
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
    config_status 는 "ok" · "missing" · "unreadable" (data 를 직접 넘기면 "ok").
    """
    status = "ok"
    if data is None and load:
        data, status = config.load_with_status()
    values: dict = {}
    sources: dict = {}
    ignored: list = []
    if not isinstance(data, dict):
        if data is None:
            status = "missing" if status == "ok" else status
        else:
            status = "unreadable"  # 최상위가 객체가 아닌 JSON 도 읽을 수 없는 설정이다
        return {"values": values, "sources": sources, "ignored": ignored, "config_status": status}

    skill_allowed = COMMON_KEYS + SKILL_KEYS
    _take(data.get("preferences"), COMMON_KEYS, "preferences", values, sources, ignored)
    layer, key = _skill_layer(data.get("skills"), skill_id)
    _take(layer, skill_allowed, f"skills.{key}", values, sources, ignored)

    entry = _find_repo(data, owner, repo)
    if entry is not None:
        tag = f"repos[{entry.get('owner')}/{entry.get('repo')}]"
        _take(entry.get("preferences"), COMMON_KEYS, f"{tag}.preferences", values, sources, ignored)
        layer, key = _skill_layer(entry.get("skills"), skill_id)
        _take(layer, skill_allowed, f"{tag}.skills.{key}", values, sources, ignored)
    return {"values": values, "sources": sources, "ignored": ignored, "config_status": status}


def is_legacy_commit_user(data: Optional[dict]) -> bool:
    """예전부터 pro-commit 을 써 온 사람인가 — 승인 설정(github.commit 또는 repos[].commit)이 남아 있다.

    이런 사람에게 새 기본값(conventional)을 조용히 적용하면 어느 날 커밋 형식이 바뀐다 (spec S1).
    """
    gh = _as_dict(_as_dict(data).get("github"))
    if isinstance(gh.get("commit"), dict):
        return True
    repos = gh.get("repos")
    return isinstance(repos, list) and any(isinstance(r, dict) and isinstance(r.get("commit"), dict)
                                           for r in repos)


# ssh://git@github.com:22/o/r 처럼 포트가 붙는 형태가 있다. 포트는 owner 가 아니므로 건너뛴다
# (scp 형식 git@github.com:1234/r 은 뒤에 두 마디가 없어 포트로 오인되지 않는다).
_REMOTE = re.compile(r"github\.com(?::\d+(?=/))?[:/]+([^/]+)/([^/]+?)(?:\.git)?/?$")


def detect_repo(cwd: Optional[str] = None) -> tuple:
    """origin remote 에서 owner/repo 를 뽑는다. git 이 없거나 remote 가 없으면 (None, None)."""
    try:
        url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=cwd,
                             capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None, None
    m = _REMOTE.search(url)
    return (m.group(1), m.group(2)) if m else (None, None)
