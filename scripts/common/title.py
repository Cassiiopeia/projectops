"""worktree 폴더명에서 제목을 추출하고 파일명 안전 형식으로 정규화한다."""

import re
from pathlib import Path
from typing import Optional


_WORKTREE_PATTERN = re.compile(r"\d{8}_\d+_(.+)$")
_ALLOWED = re.compile(r"[^\w가-힣]", re.UNICODE)
_MULTI_UNDERSCORE = re.compile(r"_+")
MAX_LENGTH = 50


def extract_from_path(cwd: str) -> Optional[str]:
    """경로에서 worktree 패턴의 제목 부분을 추출한다."""
    for part in reversed(Path(cwd).parts):
        m = _WORKTREE_PATTERN.search(part)
        if m:
            return m.group(1)
    return None


def normalize(text: str) -> str:
    """
    제목 문자열을 파일명 안전 형식으로 정규화한다.

    - 공백·하이픈 → _ (pro-launch > pro_launch, 단어가 붙어 prolaunch 가 되지 않게)
    - 허용되지 않는 문자 제거 (한글/영문/숫자/_ 외 문자는 삭제)
    - 연속 언더스코어 → 단일 언더스코어
    - 최대 50자
    """
    # 공백·하이픈을 언더스코어로 변환
    text = text.replace(" ", "_").replace("-", "_")
    # 허용되지 않는 문자를 제거 (한글/영문/숫자/_ 만 허용)
    text = _ALLOWED.sub("", text)
    # 연속 언더스코어를 단일 언더스코어로 변환
    text = _MULTI_UNDERSCORE.sub("_", text)
    # 양쪽 언더스코어 제거
    text = text.strip("_")
    # 최대 길이로 자른 후 trailing 언더스코어 제거
    return text[:MAX_LENGTH].strip("_")
