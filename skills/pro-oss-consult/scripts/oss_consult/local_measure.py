"""Local clone measurements (pure functions): co-changed file pairs, hardcoded copy, dependency names, tracked secret files
"""
from __future__ import annotations

import itertools
import json
import re
from collections import Counter
from pathlib import Path

# ── Local clone measurements (round 2: code extensibility, dependencies, secret files) ──────────────────
# Facts only here too. "Low extensibility" or "risky license" is for the agent to judge given the repo's type.

_SOURCE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".dart", ".go", ".rs", ".rb", ".php", ".swift", ".vue"}
_CATALOG_DIRS = {"i18n", "locales", "locale", "l10n", "lang", "translations", "messages"}
_SECRET_PATTERNS = (
    re.compile(r"(^|/)\.env(\.[^/]+)?$"), re.compile(r"\.(pem|p12|pfx|jks|keystore|p8)$"),
    re.compile(r"(^|/)id_(rsa|ed25519|ecdsa)$"), re.compile(r"(^|/)(google-services\.json|GoogleService-Info\.plist)$"),
)
# Example and template files are not secrets — drop them from the list
_SECRET_SAFE = re.compile(r"\.(example|sample|template|dist)$|(^|/)\.env\.(example|sample|template)$", re.I)
# String literals with Korean or other CJK inside quotes (candidates for user-facing copy)
_NL_STRING = re.compile(r"""(["'`])(?:(?!\1)[^\n\\]|\\.)*[가-힣぀-ヿ一-鿿](?:(?!\1)[^\n\\]|\\.)*\1""")
# Comment lines are not user-facing copy (multi-line docstrings cannot be filtered per line; a known limit)
_COMMENT_LINE = re.compile(r"^\s*(#|//|\*|/\*|--)")
_TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs", "__mocks__", "testdata", "fixtures"}
_TEST_FILE = re.compile(r"(^test_|_test\.|\.test\.|\.spec\.|Test\.[a-z]+$|Tests\.[a-z]+$)")
# Version sync, lock and generated files naturally change together and pollute co_change
_NOISE_FILE = re.compile(
    r"(^|/)(CHANGELOG[^/]*|CHANGES[^/]*|version\.ya?ml|plugin\.json|marketplace\.json|package\.json|"
    r"package-lock\.json|pubspec\.lock|yarn\.lock|pnpm-lock\.yaml|Cargo\.lock|poetry\.lock|Gemfile\.lock)$"
    r"|\.lock$|\.min\.[^/]+$", re.I)


def _is_test_path(path: str) -> bool:
    p = Path(path)
    return bool(set(p.parts[:-1]) & _TEST_DIRS) or bool(_TEST_FILE.search(p.name))


def co_change(commits: list[list[str]], top: int = 10, big: int = 30) -> dict:
    """Count file pairs changed together from per-commit changed files. A per-commit approximation, not per PR.

    Version sync and lock files and bulk changes (formatting, initial commit) inflate pairs, so they are left out of pair counting,
    but `excluded` reports how many — so the agent does not read "few pairs" as "no coupling".
    """
    sizes = sorted(len(c) for c in commits if c)
    pairs: Counter = Counter()
    large = 0
    noise_entries = 0
    for files in commits:
        if len(files) > big:
            large += 1
            continue
        kept = [f for f in set(files) if not _NOISE_FILE.search(f)]
        noise_entries += len(set(files)) - len(kept)
        if len(kept) >= 2:
            pairs.update(itertools.combinations(sorted(kept), 2))
    n = len(sizes)
    return {
        "commits": n,
        "median_files_per_commit": sizes[n // 2] if n else 0,
        "max_files_per_commit": sizes[-1] if n else 0,
        "top_pairs": [{"a": a, "b": b, "count": c} for (a, b), c in pairs.most_common(top) if c >= 2],
        "unit": "commit",
        "excluded": {"large_commits": large, "noise_file_entries": noise_entries, "large_threshold": big},
    }


def natural_language_strings(files: dict[str, str], top: int = 10) -> dict:
    """Count of Korean/CJK string literals per source file. Catalog folders, test files and comment lines are not counted."""
    per_file = {}
    excluded_tests = 0
    for path, text in files.items():
        parts = set(Path(path).parts)
        if parts & _CATALOG_DIRS or Path(path).suffix not in _SOURCE_EXT:
            continue
        if _is_test_path(path):
            excluded_tests += 1
            continue
        body = "\n".join(ln for ln in text.splitlines() if not _COMMENT_LINE.match(ln))
        n = len(_NL_STRING.findall(body))
        if n:
            per_file[path] = n
    ranked = sorted(per_file.items(), key=lambda kv: kv[1], reverse=True)
    return {"total": sum(per_file.values()), "files_with_strings": len(per_file),
            "excluded_test_files": excluded_tests,
            "top_files": [{"path": k, "count": v} for k, v in ranked[:top]]}


def committed_secret_paths(tracked: list[str]) -> list[str]:
    """Tracked paths that may be secrets. Example files excluded. Contents are not read."""
    return [t for t in tracked if any(p.search(t) for p in _SECRET_PATTERNS) and not _SECRET_SAFE.search(t)]


# Manifests whose dependency names are read / manifests only reported as present
_MANIFEST_EXACT = {"package.json", "pubspec.yaml", "go.mod", "pyproject.toml", "Cargo.toml", "Gemfile",
                   "composer.json", "build.gradle", "build.gradle.kts", "pom.xml"}
_UNSUPPORTED_EXACT = {"Package.swift", "Podfile", "build.sbt", "mix.exs", "Pipfile", "setup.py",
                      "environment.yml", "vcpkg.json", "conanfile.txt", "packages.config", "libs.versions.toml"}
_GRADLE_DEP = re.compile(
    r"(implementation|api|compileOnly|runtimeOnly|annotationProcessor|kapt|classpath|"
    r"testImplementation|testRuntimeOnly|androidTestImplementation)\s*\(?\s*['\"]([^'\":\s]+:[^'\":\s]+)(?::[^'\"]*)?['\"]")
_POM_DEP = re.compile(r"<dependency>\s*<groupId>([^<]+)</groupId>\s*<artifactId>([^<]+)</artifactId>")


def is_manifest(path: str) -> bool:
    n = Path(path).name
    return n in _MANIFEST_EXACT or (n.startswith("requirements") and n.endswith(".txt"))


def is_unsupported_manifest(path: str) -> bool:
    n = Path(path).name
    return n in _UNSUPPORTED_EXACT or n.endswith(".csproj")


def _toml_section_keys(text: str, header: str) -> list[str]:
    """Key names in the `[header]` section (until the next `[` section). Values are not read."""
    keys: list[str] = []
    inside = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("["):
            inside = s == f"[{header}]"
            continue
        if inside:
            m = re.match(r"^([A-Za-z0-9_.\-]+)\s*=", s)
            if m:
                keys.append(m.group(1))
    return keys


def dependency_names(manifests: dict[str, str]) -> dict:
    """Extract only the declared dependency names from a manifest (license lookup is the agent's job, against the shipped artifact)."""
    out: dict[str, list[str]] = {}
    for path, text in manifests.items():
        name = Path(path).name
        deps: list[str] = []
        if name == "package.json":
            try:
                data = json.loads(text)
            except ValueError:
                data = {}
            for key in ("dependencies", "devDependencies", "peerDependencies"):
                deps += [f"{d}" if key == "dependencies" else f"{d} ({key})" for d in (data.get(key) or {})]
        elif name == "composer.json":
            try:
                data = json.loads(text)
            except ValueError:
                data = {}
            for key in ("require", "require-dev"):
                deps += [d if key == "require" else f"{d} (dev)" for d in (data.get(key) or {})
                         if d != "php" and not d.startswith("ext-")]
        elif name.startswith("requirements") and name.endswith(".txt"):
            for line in text.splitlines():
                line = line.split("#", 1)[0].strip()
                m = re.match(r"([A-Za-z0-9_.\-]+)", line)
                if m and not line.startswith("-"):
                    deps.append(m.group(1))
        elif name == "pubspec.yaml":
            section = ""
            for line in text.splitlines():
                if re.match(r"^\S", line):
                    section = line.rstrip(":").strip()
                elif section in ("dependencies", "dev_dependencies"):
                    m = re.match(r"^  ([A-Za-z0-9_]+):", line)
                    if m and m.group(1) != "flutter":
                        deps.append(m.group(1) if section == "dependencies" else f"{m.group(1)} (dev)")
        elif name == "go.mod":
            deps += re.findall(r"^\s*([\w.\-]+/[\w./\-]+)\s+v", text, re.M)
        elif name == "pyproject.toml":
            m = re.search(r"^\s*dependencies\s*=\s*\[(.*?)\]", text, re.S | re.M)
            if m:
                for item in re.findall(r"['\"]([^'\"]+)['\"]", m.group(1)):
                    mm = re.match(r"([A-Za-z0-9_.\-]+)", item)
                    if mm:
                        deps.append(mm.group(1))
            deps += [k for k in _toml_section_keys(text, "tool.poetry.dependencies") if k != "python"]
        elif name == "Cargo.toml":
            for sec, suffix in (("dependencies", ""), ("dev-dependencies", " (dev)"), ("build-dependencies", " (build)")):
                deps += [f"{k}{suffix}" for k in _toml_section_keys(text, sec)]
                deps += [f"{k}{suffix}" for k in re.findall(rf"^\[{sec}\.([^\]]+)\]", text, re.M)]
        elif name == "Gemfile":
            deps += re.findall(r"^\s*gem\s+['\"]([^'\"]+)['\"]", text, re.M)
        elif name in ("build.gradle", "build.gradle.kts"):
            for conf, coord in _GRADLE_DEP.findall(text):
                deps.append(coord if not conf.lower().startswith(("test", "androidtest")) else f"{coord} (test)")
        elif name == "pom.xml":
            deps += [f"{g.strip()}:{a.strip()}" for g, a in _POM_DEP.findall(text)]
        if deps:
            out[path] = list(dict.fromkeys(deps))
    return out
