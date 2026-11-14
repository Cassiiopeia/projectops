"""Image tool (provider) definitions: 3 defaults + config overrides/additions > run definition, installed or not, priority
3 kinds: codex (Codex-specific args, subscription check), command (placeholder substitution run), agent (agent draws directly, no run)
"""
from __future__ import annotations

import shutil
from pathlib import Path

from . import settings

# Limit per tool run (seconds)
DEFAULT_TIMEOUT_SECONDS = 900
# Default priority: by image quality (user-set priority wins)
DEFAULT_PRIORITY = ["codex", "antigravity", "claude-vector"]

# Default tool definitions (same keys in config providers.<name> override them)
BUILTIN_PROVIDERS = {
    # OpenAI Codex CLI, ChatGPT subscription login (Plus or higher). Makes transparent PNG directly, runs without approvals or sandbox (YOLO)
    "codex": {
        "kind": "codex",
        "command": "codex",
        "args": ["exec", "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check", "--enable",
                 "image_generation"],
        "prompt_via_stdin": True,
        "supports_alpha": True,
        "attaches_references": True,
        "harvest_globs": ["~/.codex/generated_images/*/*.png"],
    },
    # Google Antigravity CLI (agy), free and Pro accounts alike. No transparent background (draws a checkerboard) > key-color background then remove
    # Headless cannot ask for permissions > auto-approve everything (YOLO, user decision); run folder is a candidate-only folder outside the repo
    "antigravity": {
        "kind": "command",
        "command": "agy",
        "args": ["-p", "{prompt_text}", "--dangerously-skip-permissions", "--print-timeout", "{timeout_seconds}s"],
        "prompt_via_stdin": False,
        "supports_alpha": False,
        "attaches_references": False,
        "harvest_globs": ["~/.gemini/antigravity-cli/brain/*/*.png", "~/.gemini/antigravity-cli/brain/*/*.jpg",
                          "~/.gemini/antigravity-cli/brain/*/*.jpeg", "~/.gemini/antigravity-cli/brain/*/*.webp"],
        # Conversation log that keeps the failure cause (quota exhausted, time until reset)
        "failure_log_globs": ["~/.gemini/antigravity-cli/brain/*/.system_generated/logs/transcript.jsonl"],
    },
    # Last resort: the agent draws SVG directly (only for simple icons and shapes)
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
    """Tool name > run definition (None for unknown names)"""
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
        "failure_log_globs": [str(item) for item in merged.get("failure_log_globs") or []],
        "timeout_seconds": int(timeout) if isinstance(timeout, (int, float)) and timeout > 0 else DEFAULT_TIMEOUT_SECONDS,
        "source": merged["source"],
    }


def executable_of(definition: dict) -> str | None:
    return shutil.which(definition["command"]) if definition["command"] else None


def is_available(definition: dict) -> bool:
    return definition["kind"] == "agent" or executable_of(definition) is not None


def priority() -> tuple[list[str], str]:
    """(tool order, source) source: config user-set / default (user not asked yet)"""
    configured = settings.configured_priority()
    return (configured, "config") if configured else (list(DEFAULT_PRIORITY), "default")


def expand_globs(patterns: list[str]) -> list[Path]:
    found = []
    for pattern in patterns:
        expanded = Path(pattern).expanduser()
        anchor = Path(expanded.anchor)
        found += [path for path in anchor.glob(str(expanded.relative_to(anchor))) if path.is_file()]
    return found
