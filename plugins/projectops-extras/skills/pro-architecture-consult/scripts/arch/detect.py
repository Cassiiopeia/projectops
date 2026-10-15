"""detect: 스택·모듈 루트, 규칙 문서, 이어받을 것(기존 감사 문서·예외 목록·규칙 테스트)"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .source_files import walk_files

RULE_DOCUMENT_NAMES = {"CLAUDE.md", "claude.md", "AGENTS.md", "GEMINI.md", ".cursorrules"}
RULE_DOCUMENT_DIRECTORY_PARTS = ("/.claude/rules/", "/.cursor/rules/", "/docs/architecture/")
PRIOR_AUDIT_PATTERN = re.compile(r"audit", re.IGNORECASE)
ALLOWLIST_PATTERN = re.compile(r"(?:allow(?:ed|list)?|baseline|frozen)[\w.-]*\.(?:txt|allow|json)$|\.allow$", re.IGNORECASE)
# 규칙 테스트 흔적 (파일 경로 또는 본문)
RULE_TEST_PATH_PATTERN = re.compile(r"(?:^|/)(?:test|tests|spec)/.*(?:architecture|layer|arch_|rules?_test|design_token)", re.IGNORECASE)
RULE_TEST_CONFIG_NAMES = {".importlinter", ".dependency-cruiser.js", ".dependency-cruiser.cjs", "importlinter.ini"}
MAXIMUM_LISTED = 40


def detect_project(root: Path) -> dict:
    stacks, rule_documents, prior_audits, allowlists, rule_tests = [], [], [], [], []
    gradle_settings_directories = set()
    for relative, absolute in walk_files(root):
        name = absolute.name
        probe = "/" + relative
        if name in ("settings.gradle", "settings.gradle.kts"):
            gradle_settings_directories.add(str(Path(relative).parent.as_posix()))

        # 스택 표식
        stack = _stack_of_marker(name, absolute)
        if stack:
            stacks.append({"stack": stack[0], "module": str(Path(relative).parent.as_posix()), "marker": name, **stack[1]})

        # 규칙 문서 · 이어받을 자료
        if name in RULE_DOCUMENT_NAMES or (name.endswith(".md") and any(p in probe for p in RULE_DOCUMENT_DIRECTORY_PARTS)):
            rule_documents.append(relative)
        if name.endswith(".md") and PRIOR_AUDIT_PATTERN.search(name):
            prior_audits.append(relative)
        if ALLOWLIST_PATTERN.search(name):
            allowlists.append(relative)
        if name in RULE_TEST_CONFIG_NAMES or RULE_TEST_PATH_PATTERN.search(relative) and _is_code(name):
            rule_tests.append(relative)
        elif name in ("build.gradle", "build.gradle.kts", "pyproject.toml", "setup.cfg", "package.json"):
            if _mentions_rule_tool(absolute):
                rule_tests.append(relative)

    stacks = _collapse_gradle_submodules(stacks, gradle_settings_directories)
    return {
        "root": str(root),
        "stacks": stacks,
        "rule_documents": rule_documents[:MAXIMUM_LISTED],
        "prior_audits": prior_audits[:MAXIMUM_LISTED],
        "allowlists": allowlists[:MAXIMUM_LISTED],
        "rule_tests": rule_tests[:MAXIMUM_LISTED],
        "has_architecture_folder": (root / "docs" / "architecture").is_dir(),
        "summary": f"스택 {sorted({s['stack'] for s in stacks})}, 규칙 문서 {len(rule_documents)}, "
                   f"기존 감사 {len(prior_audits)}, 예외 목록 {len(allowlists)}, 규칙 테스트 흔적 {len(rule_tests)}",
    }


def _stack_of_marker(name: str, absolute: Path):
    """표식 파일 > (스택, 부가 정보) 또는 None"""
    if name == "pubspec.yaml":
        text = _read(absolute)
        return ("flutter" if re.search(r"^\s*flutter\s*:", text, re.MULTILINE) else "dart"), {}
    if name in ("build.gradle", "build.gradle.kts", "pom.xml"):
        text = _read(absolute)
        return ("spring" if "springframework" in text else "jvm"), {"is_android": "com.android" in text}
    if name in ("pyproject.toml", "requirements.txt", "setup.py"):
        return "python", {}
    if name == "package.json":
        try:
            manifest = json.loads(_read(absolute) or "{}")
        except ValueError:
            manifest = {}
        dependencies = {**manifest.get("dependencies", {}), **manifest.get("devDependencies", {})}
        frameworks = [f for f in ("react", "next", "vue", "svelte", "express") if f in dependencies]
        return "javascript", {"frameworks": frameworks, "is_typescript": (absolute.parent / "tsconfig.json").exists()}
    return None


def _collapse_gradle_submodules(stacks: list[dict], settings_directories: set) -> list[dict]:
    """settings.gradle 루트 아래 Gradle 하위 모듈 > 루트 항목의 modules 로 묶기"""
    def owner_of(module: str):
        owners = [d for d in settings_directories if d != module and (d == "." or module.startswith(d + "/"))]
        return max(owners, key=len) if owners else None

    collapsed, submodules = [], {}
    for stack in stacks:
        owner = owner_of(stack["module"]) if stack["stack"] in ("spring", "jvm") else None
        if owner is not None:
            submodules.setdefault(owner, []).append(stack)
        else:
            collapsed.append(stack)
    for stack in collapsed:
        children = submodules.pop(stack["module"], [])
        if children:
            stack["modules"] = [c["module"] for c in children]
            if any(c["stack"] == "spring" for c in children):
                stack["stack"] = "spring"
    for owner, children in submodules.items():  # 루트에 build.gradle 이 없는 멀티모듈
        stack_name = "spring" if any(c["stack"] == "spring" for c in children) else "jvm"
        collapsed.append({"stack": stack_name, "module": owner, "marker": "settings.gradle",
                          "modules": [c["module"] for c in children]})
    return collapsed


def _mentions_rule_tool(path: Path) -> bool:
    return bool(re.search(r"archunit|import-linter|importlinter|dependency-cruiser|eslint-plugin-boundaries", _read(path), re.IGNORECASE))


def _is_code(name: str) -> bool:
    return name.endswith((".dart", ".java", ".kt", ".py", ".js", ".mjs", ".ts"))


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
