"""Codex CLI: check install, login type and image feature; run once with the subscription account"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

# Keys removed from the environment at run time (blocks the paid API path)
API_KEY_ENVIRONMENT_NAMES = ("OPENAI_API_KEY", "CODEX_API_KEY")
# auth_mode value for subscription login
SUBSCRIPTION_AUTH_MODE = "chatgpt"
# Folder name where Codex built-in image generation saves results (if the log has this path, the model drew it)
GENERATED_IMAGES_MARKER = "generated_images"
# "Cannot generate" reply phrase set by the prompt
IMAGE_UNAVAILABLE_PHRASE = "IMAGE GENERATION UNAVAILABLE"


def codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def find_executable(command: str) -> str | None:
    return shutil.which(command)


def login_facts() -> dict:
    """Reads only the login type from auth.json (token values are never printed)"""
    path = codex_home() / "auth.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"auth_file": str(path), "auth_mode": None, "has_stored_api_key": False}
    return {"auth_file": str(path), "auth_mode": loaded.get("auth_mode"),
            "has_stored_api_key": bool(loaded.get("OPENAI_API_KEY"))}


def _run_quick(executable: str, *arguments: str) -> str:
    try:
        completed = subprocess.run([executable, *arguments], capture_output=True, encoding="utf-8",
                                   errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout or ""


def version(executable: str) -> str:
    return _run_quick(executable, "--version").strip()


def is_image_generation_enabled(executable: str) -> bool | None:
    """image_generation line of codex features list > enabled or not, None if the line is missing"""
    for line in _run_quick(executable, "features", "list").splitlines():
        columns = line.split()
        if columns and columns[0] == "image_generation":
            return columns[-1].lower() == "true"
    return None


def subscription_environment() -> dict:
    environment = dict(os.environ)
    for name in API_KEY_ENVIRONMENT_NAMES:
        environment.pop(name, None)
    return environment


def build_command(executable: str, invocation: dict, run_dir: Path, reference_files: list[Path]) -> list[str]:
    """Codex arguments: configured args + work folder + reference images (-i) + stdin prompt (-)"""
    command = [executable, *invocation["args"], "-C", str(run_dir)]
    for reference in reference_files:
        command += ["-i", str(reference)]
    return command + ["-"]
