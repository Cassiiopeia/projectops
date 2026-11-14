"""File origin detection: separates code the repo owns (production, test) from code it does not (tooling, generated, vendored)

5 origins:
- production: production code (audited)
- test: test code (counted separately — so production numbers are not inflated)
- tooling: installed CI/agent tooling (.github/, .claude/, etc. — fixed in the upstream repo)
  Exception: a .github/ with its own tests is owned by this repo (evidence in owned_tooling)
  Whole copies of other repos (wizard temp downloads, subfolders with their own .git) are always tooling
- generated: generated output (header markers, gen-l10n output)
- vendored: copies of external libraries (vendor/, large static JS with a version header, shadcn ui)
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .source_files import (NOT_ANALYZED_LANGUAGE_BY_EXTENSION, SKIPPED_DIRECTORY_NAMES, is_generated_file,
                           language_of, walk_files, MAXIMUM_SOURCE_BYTES)

OWNED_ORIGINS = ("production", "test")
TOOLING_DIRECTORY_NAMES = {".github", ".cursor", ".claude", ".agents", ".codex", ".gemini", ".pi", ".husky"}
# Tooling folders treated as owned when they have their own tests (installed copies do not ship tests)
SELF_TESTED_TOOLING_DIRECTORY_NAMES = {".github"}
# Folders that are whole copies of other repos (projectops wizard temp downloads — their .github/ tests would make them look owned)
FOREIGN_TREE_DIRECTORY_NAMES = {".template_download_temp"}
VENDORED_DIRECTORY_NAMES = {"vendor", "vendors", "third_party", "thirdparty", "bower_components"}
# Static asset folders (JS here is likely a copy of an external library)
STATIC_DIRECTORY_NAMES = {"static", "public", "assets", "wwwroot"}
# External library header markers (first 600 chars): license, copyright, version number
LIBRARY_HEADER_PATTERN = re.compile(r"@license|\blicense\b|copyright|\(c\)|\bv?\d+\.\d+\.\d+\b", re.IGNORECASE)
# A single JS file over this many lines with a header marker is treated as an external library
LARGE_SINGLE_SCRIPT_LINES = 5000
# @generated is case-sensitive with a word boundary (avoids matching JPA @GeneratedValue)
GENERATED_HEADER_PATTERN = re.compile(
    r"generated (?:code|file|by)|do not (?:edit|modify)|(?-i:@generated\b)|auto-?generated|code generated", re.IGNORECASE)
# shadcn component folder names (checked with the alias path in modules that have components.json)
SHADCN_DIRECTORY_NAMES = {"shadcn"}

TEST_DIRECTORY_NAMES = {"test", "tests", "__tests__", "spec", "specs", "integration_test", "androidTest",
                        "testFixtures", "e2e", "__mocks__"}
TEST_FILE_PATTERN = re.compile(
    r"(?:_test\.(?:dart|py|go)|^test_[\w]+\.py|Tests?\.(?:java|kt)|IT\.java|\.(?:test|spec)\.[cm]?[jt]sx?)$")


class SourceInventory:
    """Target repo source list + origins (one pass to collect markers > classify each file)"""

    def __init__(self, root: Path, is_including_all: bool = False):
        self.root = root
        self.is_including_all = is_including_all
        self.generated_prefixes = []   # gen-l10n output (path prefix + file name prefix)
        self.vendored_prefixes = []    # shadcn ui folders, etc.
        self.shadcn_modules = []       # modules with components.json (shadcn folders other than the alias are excluded too)
        self.files = []                # (relative path, language, content, origin)
        self.excluded = {}             # origin > {count, reasons, examples}
        self.not_analyzed_languages = {}  # languages the CLI cannot read > file count (tooling and external folders excluded)
        self.owned_tooling = {}        # tooling folder prefixes treated as owned > evidence (own tests)
        self.foreign_trees = {}        # prefixes of other-repo copies > evidence (temp download, nested git repo)
        self._collect_foreign_trees()
        self._collect_markers()
        self._collect_files()

    def owned(self):
        return [(r, l, t, o) for r, l, t, o in self.files if o in OWNED_ORIGINS]

    def excluded_summary(self) -> dict:
        return {origin: {"count": e["count"], "reasons": e["reasons"], "examples": e["examples"]}
                for origin, e in self.excluded.items()}

    def _collect_foreign_trees(self):
        """Subfolders that are other-repo copies > record the prefix (no descent below them)"""
        for directory, subdirectories, _ in os.walk(self.root):
            descend = []
            for name in sorted(d for d in subdirectories if d not in SKIPPED_DIRECTORY_NAMES):
                absolute = Path(directory) / name
                prefix = absolute.relative_to(self.root).as_posix() + "/"
                if name in FOREIGN_TREE_DIRECTORY_NAMES:
                    self.foreign_trees[prefix] = prefix
                elif (absolute / ".git").exists():  # both folder (clone) and file (worktree, submodule)
                    self.foreign_trees[prefix] = f"{prefix} (nested git repo)"
                else:
                    descend.append(name)
            subdirectories[:] = descend

    def _foreign_tree_reason(self, relative: str) -> str | None:
        return next((reason for prefix, reason in self.foreign_trees.items() if relative.startswith(prefix)), None)

    # Collect markers (shadcn components.json, Flutter l10n.yaml) — markers inside other-repo copies are ignored
    def _collect_markers(self):
        for relative, absolute in walk_files(self.root):
            if self._foreign_tree_reason(relative):
                continue
            name = absolute.name
            module = Path(relative).parent.as_posix()
            module_prefix = "" if module == "." else module + "/"
            if name == "components.json":
                ui_alias = _read_json(absolute).get("aliases", {}).get("ui")
                if isinstance(ui_alias, str) and ui_alias.startswith(("@/", "~/")):
                    has_src = (absolute.parent / "src").is_dir()
                    self.vendored_prefixes.append(
                        (module_prefix + ("src/" if has_src else "") + ui_alias[2:].strip("/") + "/", "shadcn ui"))
                self.shadcn_modules.append(module_prefix)
            elif language_of(relative) and is_test_path(relative):
                self._mark_self_tested_tooling(relative)
            elif name == "l10n.yaml":
                text = _read_text(absolute)
                output_directory = _yaml_value(text, "output-dir") or _yaml_value(text, "arb-dir") or "lib/l10n"
                output_file = _yaml_value(text, "output-localization-file") or "app_localizations.dart"
                self.generated_prefixes.append((module_prefix + output_directory.strip("/") + "/",
                                                Path(output_file).stem, "gen-l10n"))

    def _mark_self_tested_tooling(self, relative: str):
        """Test files inside a tooling folder > treat that folder as owned (evidence: test count and examples)"""
        parts = relative.split("/")
        for depth, directory in enumerate(parts[:-1]):
            if directory in SELF_TESTED_TOOLING_DIRECTORY_NAMES:
                prefix = "/".join(parts[:depth + 1]) + "/"
                entry = self.owned_tooling.setdefault(prefix, {"reason": "own tests inside the folder", "test_files": 0, "examples": []})
                entry["test_files"] += 1
                if len(entry["examples"]) < 3:
                    entry["examples"].append(relative)
                return

    def _is_owned_tooling(self, relative: str) -> bool:
        return any(relative.startswith(prefix) for prefix in self.owned_tooling)

    def _collect_files(self):
        for relative, absolute in walk_files(self.root):
            language = language_of(relative)
            if not language:
                self._count_not_analyzed(relative)
                continue
            try:
                if absolute.stat().st_size > MAXIMUM_SOURCE_BYTES:
                    self._exclude("vendored", relative, "over 2MB")
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

    def _count_not_analyzed(self, relative: str):
        name = NOT_ANALYZED_LANGUAGE_BY_EXTENSION.get(Path(relative).suffix.lower())
        directories = set(relative.split("/")[:-1])
        is_tooling = ((bool(TOOLING_DIRECTORY_NAMES & directories) and not self._is_owned_tooling(relative))
                      or bool(self._foreign_tree_reason(relative)))
        if name and not is_tooling and not VENDORED_DIRECTORY_NAMES & directories and not is_generated_file(relative):
            self.not_analyzed_languages[name] = self.not_analyzed_languages.get(name, 0) + 1

    def _origin_of(self, relative: str, language: str, text: str):
        directories = relative.split("/")[:-1]
        name = relative.rsplit("/", 1)[-1]
        foreign_tree_reason = self._foreign_tree_reason(relative)
        if foreign_tree_reason:
            return "tooling", foreign_tree_reason
        if TOOLING_DIRECTORY_NAMES & set(directories) and not self._is_owned_tooling(relative):
            return "tooling", next(d for d in directories if d in TOOLING_DIRECTORY_NAMES) + "/"
        if is_generated_file(relative):
            return "generated", "generated file extension"
        for prefix, stem, reason in self.generated_prefixes:
            if relative.startswith(prefix) and name.startswith(stem):
                return "generated", reason
        if GENERATED_HEADER_PATTERN.search(text[:600]):
            return "generated", "generated file header marker"
        if VENDORED_DIRECTORY_NAMES & set(directories):
            return "vendored", "vendor folder"
        for prefix, reason in self.vendored_prefixes:
            if relative.startswith(prefix):
                return "vendored", reason
        if any(relative.startswith(m) for m in self.shadcn_modules) and SHADCN_DIRECTORY_NAMES & set(directories):
            return "vendored", "shadcn folder"
        if language in ("javascript", "typescript") and _looks_like_library_copy(directories, text):
            return "vendored", "third-party library header"
        return ("test", "") if is_test_path(relative) else ("production", "")

    def _exclude(self, origin: str, relative: str, reason: str):
        entry = self.excluded.setdefault(origin, {"count": 0, "reasons": {}, "examples": []})
        entry["count"] += 1
        entry["reasons"][reason] = entry["reasons"].get(reason, 0) + 1
        if len(entry["examples"]) < 5:
            entry["examples"].append(relative)


def is_test_path(relative: str) -> bool:
    """Test path detection (under src/main it is production code even if named test — test code mixed into production is caught separately)"""
    if "/src/main/" in "/" + relative:
        return False
    name = relative.rsplit("/", 1)[-1]
    if TEST_FILE_PATTERN.search(name):
        return True
    directories = relative.split("/")[:-1]
    # A /test page in the Next app router is a production route
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
