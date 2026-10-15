"""파일 출처 판별: 레포가 소유한 코드(production·test)와 아닌 코드(tooling·generated·vendored) 구분

출처 5종:
- production: 운영 코드 (감사 대상)
- test: 테스트 코드 (따로 센다 — 운영 수치를 부풀리지 않게)
- tooling: CI·에이전트 도구 설치물 (.github/, .claude/ 등 — 원본 레포에서 고칠 일)
- generated: 생성물 (머리 표식, gen-l10n 출력)
- vendored: 외부 라이브러리 사본 (vendor/, 버전 머리가 있는 큰 정적 JS, shadcn ui)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .source_files import is_generated_file, language_of, walk_files, MAXIMUM_SOURCE_BYTES

OWNED_ORIGINS = ("production", "test")
TOOLING_DIRECTORY_NAMES = {".github", ".cursor", ".claude", ".agents", ".codex", ".gemini", ".pi", ".husky"}
VENDORED_DIRECTORY_NAMES = {"vendor", "vendors", "third_party", "thirdparty", "bower_components"}
# 정적 자원 폴더 (여기 있는 JS는 외부 라이브러리 사본일 가능성이 높다)
STATIC_DIRECTORY_NAMES = {"static", "public", "assets", "wwwroot"}
# 외부 라이브러리 머리 표식 (첫 600자): 라이선스·저작권·버전 번호
LIBRARY_HEADER_PATTERN = re.compile(r"@license|\blicense\b|copyright|\(c\)|\bv?\d+\.\d+\.\d+\b", re.IGNORECASE)
# 이 줄 수를 넘는 JS 한 파일은 머리 표식이 있으면 외부 라이브러리로 본다
LARGE_SINGLE_SCRIPT_LINES = 5000
GENERATED_HEADER_PATTERN = re.compile(
    r"generated (?:code|file|by)|do not (?:edit|modify)|@generated|auto-?generated|code generated", re.IGNORECASE)

TEST_DIRECTORY_NAMES = {"test", "tests", "__tests__", "spec", "specs", "integration_test", "androidTest",
                        "testFixtures", "e2e", "__mocks__"}
TEST_FILE_PATTERN = re.compile(
    r"(?:_test\.(?:dart|py|go)|^test_[\w]+\.py|Tests?\.(?:java|kt)|IT\.java|\.(?:test|spec)\.[cm]?[jt]sx?)$")


class SourceInventory:
    """대상 레포 소스 목록 + 출처 (한 번 훑어 표식 수집 > 파일마다 판정)"""

    def __init__(self, root: Path, is_including_all: bool = False):
        self.root = root
        self.is_including_all = is_including_all
        self.generated_prefixes = []   # gen-l10n 출력 (경로 접두사 + 파일 이름 접두사)
        self.vendored_prefixes = []    # shadcn ui 폴더 등
        self.files = []                # (상대경로, 언어, 본문, 출처)
        self.excluded = {}             # 출처 > {count, reasons, examples}
        self._collect_markers()
        self._collect_files()

    def owned(self):
        return [(r, l, t, o) for r, l, t, o in self.files if o in OWNED_ORIGINS]

    def excluded_summary(self) -> dict:
        return {origin: {"count": e["count"], "reasons": e["reasons"], "examples": e["examples"]}
                for origin, e in self.excluded.items()}

    # 표식 수집 (shadcn components.json, Flutter l10n.yaml)
    def _collect_markers(self):
        for relative, absolute in walk_files(self.root):
            name = absolute.name
            module = Path(relative).parent.as_posix()
            module_prefix = "" if module == "." else module + "/"
            if name == "components.json":
                ui_alias = _read_json(absolute).get("aliases", {}).get("ui")
                if isinstance(ui_alias, str) and ui_alias.startswith(("@/", "~/")):
                    has_src = (absolute.parent / "src").is_dir()
                    self.vendored_prefixes.append(
                        (module_prefix + ("src/" if has_src else "") + ui_alias[2:].strip("/") + "/", "shadcn ui"))
            elif name == "l10n.yaml":
                text = _read_text(absolute)
                output_directory = _yaml_value(text, "output-dir") or _yaml_value(text, "arb-dir") or "lib/l10n"
                output_file = _yaml_value(text, "output-localization-file") or "app_localizations.dart"
                self.generated_prefixes.append((module_prefix + output_directory.strip("/") + "/",
                                                Path(output_file).stem, "gen-l10n"))

    def _collect_files(self):
        for relative, absolute in walk_files(self.root):
            language = language_of(relative)
            if not language:
                continue
            try:
                if absolute.stat().st_size > MAXIMUM_SOURCE_BYTES:
                    self._exclude("vendored", relative, "2MB 초과")
                    continue
                text = absolute.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            origin, reason = self._origin_of(relative, language, text)
            if origin not in OWNED_ORIGINS:
                self._exclude(origin, relative, reason)
                if not self.is_including_all:
                    continue
            self.files.append((relative, language, text, origin))

    def _origin_of(self, relative: str, language: str, text: str):
        directories = relative.split("/")[:-1]
        name = relative.rsplit("/", 1)[-1]
        if TOOLING_DIRECTORY_NAMES & set(directories):
            return "tooling", next(d for d in directories if d in TOOLING_DIRECTORY_NAMES) + "/"
        if is_generated_file(relative):
            return "generated", "생성 파일 확장자"
        for prefix, stem, reason in self.generated_prefixes:
            if relative.startswith(prefix) and name.startswith(stem):
                return "generated", reason
        if GENERATED_HEADER_PATTERN.search(text[:600]):
            return "generated", "생성 머리 표식"
        if VENDORED_DIRECTORY_NAMES & set(directories):
            return "vendored", "vendor 폴더"
        for prefix, reason in self.vendored_prefixes:
            if relative.startswith(prefix):
                return "vendored", reason
        if language in ("javascript", "typescript") and _looks_like_library_copy(directories, text):
            return "vendored", "외부 라이브러리 머리"
        return ("test", "") if is_test_path(relative) else ("production", "")

    def _exclude(self, origin: str, relative: str, reason: str):
        entry = self.excluded.setdefault(origin, {"count": 0, "reasons": {}, "examples": []})
        entry["count"] += 1
        entry["reasons"][reason] = entry["reasons"].get(reason, 0) + 1
        if len(entry["examples"]) < 5:
            entry["examples"].append(relative)


def is_test_path(relative: str) -> bool:
    """테스트 경로 판정 (src/main 아래는 이름이 test여도 운영 코드 — 운영에 섞인 테스트 코드는 따로 잡는다)"""
    if "/src/main/" in "/" + relative:
        return False
    name = relative.rsplit("/", 1)[-1]
    if TEST_FILE_PATTERN.search(name):
        return True
    directories = relative.split("/")[:-1]
    # Next app 라우터의 /test 페이지는 운영 라우트
    if "app" in directories and language_of(relative) in ("javascript", "typescript"):
        directories = directories[:directories.index("app")]
    return bool(TEST_DIRECTORY_NAMES & set(directories))


def _looks_like_library_copy(directories: list, text: str) -> bool:
    is_static = bool(STATIC_DIRECTORY_NAMES & set(directories))
    is_large = text.count("\n") > LARGE_SINGLE_SCRIPT_LINES
    return (is_static or is_large) and bool(LIBRARY_HEADER_PATTERN.search(text[:600]))


def _yaml_value(text: str, key: str) -> str | None:
    match = re.search(rf"^{re.escape(key)}:\s*['\"]?([^'\"\n#]+)", text, re.MULTILINE)
    return match.group(1).strip() if match else None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(_read_text(path) or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}
