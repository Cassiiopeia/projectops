"""디자인 후보 파일 찾기 + 프로젝트 지식(레포 범위 하네스 ui-design) 저장과 읽기
스크립트는 후보와 근거만 낸다. 값 해석과 tokens.css 작성은 에이전트 몫
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from common.emit import emit
from common.state import state_dir

HARNESS_NAME = "ui-design"
TOKENS_FILE_NAME = "tokens.json"
README_FILE_NAME = "README.md"
EXCERPT_MAX_CHARACTERS = 600
MAX_CANDIDATES_PER_KIND = 20
MAX_WALKED_FILES = 50000
IGNORED_FOLDERS = {".git", "node_modules", "build", "dist", "out", ".next", ".nuxt", ".dart_tool", ".gradle", ".idea",
                   ".vscode", "Pods", "DerivedData", "vendor", "target", ".venv", "venv", "__pycache__", "coverage",
                   ".superpowers", ".claude", ".projectops"}
SOURCE_SUFFIXES = r"(dart|ts|tsx|js|jsx|mjs|swift|kt|css|scss|sass|less|json)"
# 규칙 표: (종류, 소문자 상대 경로 정규식, 이유). 위에서부터 첫 일치만 적용. 스택 추가 = 줄 추가
CANDIDATE_RULES = tuple((kind, re.compile(pattern), reason) for kind, pattern, reason in (
    ("font", r"\.(ttf|otf|woff2?)$", "font file"),
    ("document", r"(^|/)(design|brand)\.md$|(^|/)[^/]*design[-_]?system[^/]*\.md$", "design guide document"),
    ("component", r"(^|/)components/ui/[^/]+\.(tsx?|jsx?|vue|svelte)$", "shared UI component"),
    ("component", r"(^|/)design[-_]?system/[^/]+/?.*\.(dart|tsx?|jsx?|vue|swift|kt)$", "design system component"),
    ("component", r"(^|/)presentation/design/.*\.dart$", "design system component"),
    ("theme", r"(^|/)tailwind\.config\.[a-z]+$", "Tailwind theme"),
    ("color", r"(^|/)res/values[^/]*/colors\.xml$", "Android colors"),
    ("theme", r"(^|/)res/values[^/]*/themes?\.xml$", "Android theme"),
    ("color", r"(^|/)[^/]*colou?rs?[^/]*\." + SOURCE_SUFFIXES + "$", "color definitions"),
    ("typography", r"(^|/)[^/]*(typography|text[-_]?styles?|type[-_]?scale)[^/]*\." + SOURCE_SUFFIXES + "$", "type styles"),
    ("spacing", r"(^|/)[^/]*(spacing|dimens)[^/]*\." + SOURCE_SUFFIXES + "$", "spacing values"),
    ("motion", r"(^|/)[^/]*(motion|easing)[^/]*\." + SOURCE_SUFFIXES + "$", "motion values"),
    ("theme", r"(^|/)[^/]*theme[^/]*\." + SOURCE_SUFFIXES + "$", "theme definition"),
    ("token", r"(^|/)[^/]*tokens\." + SOURCE_SUFFIXES + "$", "design tokens"),
    ("theme", r"(^|/)(globals?|variables|_variables)\.(css|scss|sass|less)$", "global styles"),
))
FLUTTER_FONTS_PATTERN = re.compile(r"^\s*fonts\s*:", re.MULTILINE)
README_TEMPLATE = """# ui-design: this project's design notes

## Summary
(One paragraph the agent reads before every mockup: look and feel, what to always follow.)

## Tokens
(Where colors, type, spacing and motion live, and how they map to tokens.css.)

## Fonts
(Families, weights and font files to copy into the session.)

## Components
(Shared components to imitate: button, sheet, card, list row.)

## Render
(How to render real screens with pro-launch render, if it works here.)

## Avoid
(Things this project must not do.)

## Decisions
(Short log of chosen options and why.)
"""


def find_candidates(root: Path) -> list[dict]:
    """레포 훑기: 무시 폴더 제외, 종류별 상한"""
    candidates, per_kind, walked = [], {}, 0
    for folder, subfolders, files in os.walk(root):
        subfolders[:] = sorted(name for name in subfolders if name not in IGNORED_FOLDERS)
        for name in sorted(files):
            walked += 1
            if walked > MAX_WALKED_FILES:
                return candidates
            relative = (Path(folder) / name).relative_to(root).as_posix()
            matched = _classify_file(root, relative)
            if matched and per_kind.get(matched[0], 0) < MAX_CANDIDATES_PER_KIND:
                per_kind[matched[0]] = per_kind.get(matched[0], 0) + 1
                candidates.append({"kind": matched[0], "path": relative, "reason": matched[1]})
    return candidates


def _classify_file(root: Path, relative: str) -> tuple[str, str] | None:
    lowered = relative.lower()
    if lowered.endswith("pubspec.yaml"):
        return ("font", "Flutter font declarations") if _has_flutter_fonts(root / relative) else None
    for kind, pattern, reason in CANDIDATE_RULES:
        if pattern.search(lowered):
            return kind, reason
    return None


def _has_flutter_fonts(path: Path) -> bool:
    try:
        return bool(FLUTTER_FONTS_PATTERN.search(path.read_text(encoding="utf-8", errors="ignore")))
    except OSError:
        return False


def _harness_dir(root: Path) -> Path:
    """pro-launch 레포 범위 하네스와 같은 자리: harness list, show 로도 보임"""
    return state_dir("launch", root) / "harness" / HARNESS_NAME


def _hash_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def save_project_profile(root: Path, candidates: list[dict]) -> dict:
    """근거 파일 해시 저장 + 안내서 뼈대 생성(이미 있으면 그대로)"""
    folder = _harness_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    files = [{"path": item["path"], "sha256": _hash_file(root / item["path"])} for item in candidates]
    (folder / TOKENS_FILE_NAME).write_text(json.dumps({"files": files}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    readme = folder / README_FILE_NAME
    readme_created = not readme.exists()
    if readme_created:
        readme.write_text(README_TEMPLATE, encoding="utf-8")
    return {"folder": str(folder), "readme": str(readme), "readme_created": readme_created, "files": len(files)}


def _read_excerpt(readme: Path) -> str:
    text = readme.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"^## Summary\s*\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    return (match.group(1) if match else text).strip()[:EXCERPT_MAX_CHARACTERS]


def read_project_profile(root: Path) -> dict:
    """start 응답용: 저장된 안내서 요약 + 바뀐 근거 파일"""
    folder = _harness_dir(root)
    readme = folder / README_FILE_NAME
    if not readme.is_file():
        return {"exists": False, "readme": None, "excerpt": "", "changed_files": []}
    changed = []
    try:
        saved = json.loads((folder / TOKENS_FILE_NAME).read_text(encoding="utf-8")).get("files", [])
    except (OSError, ValueError):
        saved = []
    for item in saved:
        if isinstance(item, dict) and item.get("path") and _hash_file(root / item["path"]) != item.get("sha256"):
            changed.append(item["path"])
    return {"exists": True, "readme": str(readme), "excerpt": _read_excerpt(readme), "changed_files": changed}


def cmd_tokens(args) -> int:
    root = Path(args.root).resolve()
    candidates = find_candidates(root)
    payload = {"candidates": candidates, "summary": f"{len(candidates)} design file candidates"}
    if args.save:
        payload["saved"] = save_project_profile(root, candidates)
        payload["next"] = (f"Fill in {payload['saved']['readme']} from what you read, so the next session does not search again. "
                           "Never write secrets there.")
    elif not candidates:
        payload["next"] = "No design files found: use the neutral theme and tell the user the mockup does not reflect a design system."
    else:
        payload["next"] = ("Read these files, copy real values into screens_dir/tokens.css as --ui-* variables, copy fonts into "
                           "screens_dir with @font-face, then ask once whether to save this with tokens --save.")
    return emit(payload)
