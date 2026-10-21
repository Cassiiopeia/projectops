"""릴리스 컨텍스트: 앱 심사 신호 수집, config 읽기(읽기 전용), app_release 기록 조회.

detect-release-context(신호 보고)와 create-pr(앱 심사 승인 게이트, #970)이 같은 판정을 쓴다.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

# 앱 스토어 심사로 직결되는 워크플로우 파일명 키워드 (대소문자 무시 부분일치).
# 새 스토어/플랫폼이 생기면 이 목록에 키워드만 추가하면 감지가 확장된다 (SKILL.md·판단 로직 무수정).
_STORE_WORKFLOW_KEYWORDS = ("PLAYSTORE", "TESTFLIGHT", "APPSTORE", "APP-STORE")
# 앱(스토어 배포) 성격이 강한 프로젝트 타입.
_APP_PROJECT_TYPES = ("flutter", "react-native", "react-native-expo")
# 앱 심사 신호가 있다고 보는 hint
APP_SIGNAL_HINTS = ("strong_app", "app_release_likely")


def _read_project_types(project_root: Path) -> list[str]:
    """version.yml에서 project_types 배열을 추출한다 (yaml 의존성 없이 정규식).

    폐쇄망·표준 라이브러리 우선 원칙: PyYAML을 import하지 않고 `project_types: [...]` 라인을
    문자열로 파싱한다. 파일이 없거나 키가 없으면 빈 리스트를 반환한다 (오류 아님)."""
    vy = project_root / "version.yml"
    if not vy.exists():
        return []
    try:
        text = vy.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    # `project_types: ["spring", "react"]` 형태의 한 줄을 찾아 따옴표 안 토큰만 추출.
    m = re.search(r"^\s*project_types\s*:\s*\[([^\]]*)\]", text, re.MULTILINE)
    if m:
        return [t.strip().strip("\"'") for t in m.group(1).split(",") if t.strip()]
    # 배열이 아닌 단수 `project_type: "flutter"` 폴백.
    m2 = re.search(r"^\s*project_type\s*:\s*[\"']?([A-Za-z0-9_-]+)", text, re.MULTILINE)
    return [m2.group(1)] if m2 else []


def _scan_store_workflows(project_root: Path) -> list[str]:
    """.github/workflows 내 파일명을 스캔해 스토어 심사 워크플로우 파일명을 반환한다."""
    wf_dir = project_root / ".github" / "workflows"
    if not wf_dir.is_dir():
        return []
    found = []
    try:
        for entry in sorted(os.listdir(wf_dir)):
            upper = entry.upper()
            if any(kw in upper for kw in _STORE_WORKFLOW_KEYWORDS):
                found.append(entry)
    except OSError:
        return []
    return found


def collect_app_signals(project_root: Path) -> tuple[dict, str]:
    """(signals, hint). hint: strong_app | app_release_likely | backend_only | unknown(신호 없음)"""
    project_types = _read_project_types(project_root)
    store_workflows = _scan_store_workflows(project_root)
    has_store_workflow = bool(store_workflows)
    has_app_type = any(t.lower() in _APP_PROJECT_TYPES for t in project_types)
    # version.yml·workflows를 둘 다 못 읽었으면 신호가 없는 unknown 상태.
    no_signals = not project_types and not (project_root / ".github" / "workflows").is_dir()

    if no_signals:
        hint = "unknown"
    elif has_store_workflow and has_app_type:
        hint = "strong_app"          # 앱 타입 + 스토어 워크플로우 → 앱 심사 거의 확실
    elif has_store_workflow:
        hint = "app_release_likely"  # 스토어 워크플로우는 있으나 타입 신호 약함
    elif has_app_type:
        hint = "app_release_likely"  # 앱 타입은 있으나 스토어 워크플로우 미발견 (TEST 빌드만 등)
    else:
        hint = "backend_only"        # 앱 신호 전무 → 백엔드로 간주
    signals = {
        "project_types": project_types,
        "store_workflows": store_workflows,
        "has_store_workflow": has_store_workflow,
        "has_app_type": has_app_type,
    }
    return signals, hint


def load_config(config_arg: str | None) -> dict | None:
    """config.json을 읽기 전용으로 연다. 경로를 안 주면 PAT 자동 로드와 같은 고정 경로를 쓴다.

    CLI가 config를 읽는 것은 PAT 자동 로드(common.config)와 같은 선례다 — 쓰기는 하지 않는다.
    경로를 Python이 Path.home()으로 직접 풀기 때문에 Windows Git Bash `$HOME` 경로 문제가 없다."""
    if config_arg:
        path = Path(config_arg).expanduser()
    else:
        from common.config import config_path
        path = config_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def read_app_release(config: dict | None, owner: str, repo: str) -> bool | None:
    """레포별 changelog_deploy.app_release (true·false·없으면 None). 전역 기본값은 없다 (config.md §4)"""
    github_section = (config or {}).get("github") if isinstance(config, dict) else None
    if not isinstance(github_section, dict):
        return None
    for repo_entry in github_section.get("repos", []) or []:
        if isinstance(repo_entry, dict) and repo_entry.get("owner") == owner and repo_entry.get("repo") == repo:
            changelog_deploy = repo_entry.get("changelog_deploy")
            value = changelog_deploy.get("app_release") if isinstance(changelog_deploy, dict) else None
            return value if isinstance(value, bool) else None
    return None
