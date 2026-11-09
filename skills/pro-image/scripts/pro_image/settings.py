"""설정: ~/.projectops/config/config.json 의 image 섹션 (없으면 기본값) + 레포 위치 판별"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

CONFIG_SECTION = "image"
# 레포 하네스 위치 (레포 루트 기준 상대경로)
DEFAULT_HARNESS_DIR = "docs/image-harness"
# 후보 그림 보관: ~/.projectops/image/{owner__repo}/runs/{yyyyMMdd_HHmmss}_{이름}
RUNS_PARTS = (".projectops", "image")


def _section() -> dict:
    path = Path.home() / ".projectops" / "config" / "config.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    section = loaded.get(CONFIG_SECTION) if isinstance(loaded, dict) else None
    return section if isinstance(section, dict) else {}


def configured_providers() -> dict:
    providers = _section().get("providers")
    return providers if isinstance(providers, dict) else {}


def configured_priority() -> list[str] | None:
    """image.priority (사용자가 정한 도구 순서), 없으면 None > 처음 쓸 때 사용자에게 물음"""
    priority = _section().get("priority")
    if isinstance(priority, list) and priority and all(isinstance(item, str) for item in priority):
        return list(priority)
    return None


def is_subscription_required() -> bool:
    # require_subscription: 기본 true, 명시적 false 일 때만 Codex API 키 로그인 허용
    return _section().get("require_subscription") is not False


def _git(*arguments: str) -> str:
    try:
        completed = subprocess.run(["git", *arguments], capture_output=True, encoding="utf-8", errors="replace",
                                   timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def repository_root() -> Path:
    top_level = _git("rev-parse", "--show-toplevel")
    return Path(top_level) if top_level else Path.cwd()


def repository_key(root: Path) -> str:
    """origin 주소 > owner__repo, 없으면 폴더 이름 (프로젝트별 후보 폴더 분리)"""
    origin = _git("-C", str(root), "remote", "get-url", "origin")
    matched = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?/?$", origin)
    if matched:
        return f"{matched.group(1)}__{matched.group(2)}"
    return root.name or "workspace"


def harness_dir(root: Path) -> Path:
    configured = _section().get("harness_dir")
    relative = str(configured) if isinstance(configured, str) and configured.strip() else DEFAULT_HARNESS_DIR
    return (root / relative).resolve()


def new_run_dir(root: Path, name: str) -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return Path.home().joinpath(*RUNS_PARTS, repository_key(root), "runs", f"{stamp}_{name}")
