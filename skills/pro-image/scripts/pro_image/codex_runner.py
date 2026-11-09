"""Codex CLI: 설치·로그인 방식·이미지 기능 확인, 구독 계정으로 1회 실행"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

# 실행 시 환경에서 빼는 키 (API 과금 경로 차단)
API_KEY_ENVIRONMENT_NAMES = ("OPENAI_API_KEY", "CODEX_API_KEY")
# 구독 로그인 auth_mode 값
SUBSCRIPTION_AUTH_MODE = "chatgpt"
# Codex 내장 이미지 생성 결과가 저장되는 폴더 이름 (로그에 이 경로가 있으면 모델로 그린 것)
GENERATED_IMAGES_MARKER = "generated_images"
# 프롬프트가 정한 "생성 불가" 응답 문구
IMAGE_UNAVAILABLE_PHRASE = "IMAGE GENERATION UNAVAILABLE"


def codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def find_executable(command: str) -> str | None:
    return shutil.which(command)


def login_facts() -> dict:
    """auth.json 에서 로그인 방식만 읽음 (토큰 값은 읽어도 출력하지 않음)"""
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
    """codex features list 의 image_generation 줄 > 켜짐 여부, 줄이 없으면 None"""
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
    """Codex 인자: 설정 인자 + 작업 폴더 + 참조 이미지(-i) + stdin 프롬프트(-)"""
    command = [executable, *invocation["args"], "-C", str(run_dir)]
    for reference in reference_files:
        command += ["-i", str(reference)]
    return command + ["-"]
