"""이미지 도구(provider) 정의: 기본 3종 + config 덮어쓰기·추가 > 호출 정의, 설치 여부, 우선순위
kind 3개: codex (Codex 전용 인자·구독 확인), command (자리표시자 치환 실행), agent (에이전트가 직접 그림, 실행 없음)
"""
from __future__ import annotations

import shutil
from pathlib import Path

from . import settings

# 도구 1회 실행 제한 (초)
DEFAULT_TIMEOUT_SECONDS = 900
# 기본 우선순위: 이미지 품질 순 (사용자가 priority 를 정하면 그쪽 우선)
DEFAULT_PRIORITY = ["codex", "antigravity", "claude-vector"]

# 기본 도구 정의 (config providers.<이름> 의 같은 키가 덮어씀)
BUILTIN_PROVIDERS = {
    # OpenAI Codex CLI, ChatGPT 구독 로그인 (Plus 이상). 투명 PNG 직접 생성 가능
    "codex": {
        "kind": "codex",
        "command": "codex",
        "args": ["exec", "-s", "workspace-write", "--skip-git-repo-check", "--enable", "image_generation"],
        "prompt_via_stdin": True,
        "supports_alpha": True,
        "attaches_references": True,
        "harvest_globs": ["~/.codex/generated_images/*/*.png"],
    },
    # Google Antigravity CLI (agy), 무료·Pro 계정 공통. 투명 배경 불가(체크무늬를 그려 넣음) > 키 컬러 배경 후 제거
    # 헤드리스는 권한 질문 불가 > 터미널 제한(--sandbox) 안에서 자동 승인, 실행 폴더는 후보 전용 폴더
    "antigravity": {
        "kind": "command",
        "command": "agy",
        "args": ["-p", "{prompt_text}", "--sandbox", "--dangerously-skip-permissions", "--print-timeout",
                 "{timeout_seconds}s"],
        "prompt_via_stdin": False,
        "supports_alpha": False,
        "attaches_references": False,
        "harvest_globs": ["~/.gemini/antigravity-cli/brain/*/*.png", "~/.gemini/antigravity-cli/brain/*/*.jpg",
                          "~/.gemini/antigravity-cli/brain/*/*.jpeg", "~/.gemini/antigravity-cli/brain/*/*.webp"],
    },
    # 최후 수단: 에이전트가 SVG 로 직접 그림 (단순 아이콘·도형에만 적합)
    "claude-vector": {"kind": "agent", "supports_alpha": True, "attaches_references": False},
}


def _merged(name: str) -> dict | None:
    builtin = BUILTIN_PROVIDERS.get(name, {})
    configured = settings.configured_providers().get(name)
    configured = configured if isinstance(configured, dict) else {}
    if not builtin and not configured:
        return None
    return {**builtin, **configured, "source": "config" if configured else "builtin"}


def known_names() -> list[str]:
    return list(dict.fromkeys([*BUILTIN_PROVIDERS, *settings.configured_providers()]))


def invocation(name: str) -> dict | None:
    """도구 이름 > 실행 정의 (없는 이름이면 None)"""
    merged = _merged(name)
    if merged is None:
        return None
    timeout = merged.get("timeout_seconds")
    return {
        "name": name,
        "kind": str(merged.get("kind") or "command"),
        "command": str(merged.get("command") or ""),
        "args": [str(item) for item in merged.get("args") or []],
        "prompt_via_stdin": merged.get("prompt_via_stdin") is True,
        "supports_alpha": merged.get("supports_alpha") is True,
        "attaches_references": merged.get("attaches_references") is True,
        "harvest_globs": [str(item) for item in merged.get("harvest_globs") or []],
        "timeout_seconds": int(timeout) if isinstance(timeout, (int, float)) and timeout > 0 else DEFAULT_TIMEOUT_SECONDS,
        "source": merged["source"],
    }


def executable_of(definition: dict) -> str | None:
    return shutil.which(definition["command"]) if definition["command"] else None


def is_available(definition: dict) -> bool:
    return definition["kind"] == "agent" or executable_of(definition) is not None


def priority() -> tuple[list[str], str]:
    """(도구 순서, 출처) 출처: config 사용자 지정 / default 기본값 (사용자에게 아직 안 물음)"""
    configured = settings.configured_priority()
    return (configured, "config") if configured else (list(DEFAULT_PRIORITY), "default")


def expand_globs(patterns: list[str]) -> list[Path]:
    found = []
    for pattern in patterns:
        expanded = Path(pattern).expanduser()
        anchor = Path(expanded.anchor)
        found += [path for path in anchor.glob(str(expanded.relative_to(anchor))) if path.is_file()]
    return found
