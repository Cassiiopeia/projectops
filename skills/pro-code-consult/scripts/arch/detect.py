"""detect: stacks and module roots, rule documents, things to carry over (previous audits, exception lists, rule tests)"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .source_files import walk_files

RULE_DOCUMENT_NAMES = {"CLAUDE.md", "claude.md", "AGENTS.md", "GEMINI.md", ".cursorrules", "copilot-instructions.md"}
RULE_DOCUMENT_DIRECTORY_PARTS = ("/.claude/rules/", "/.cursor/rules/", "/docs/architecture/")
# This skill's audit report folder (where get-output-path writes — past audits, not rule documents)
AUDITS_DIRECTORY = "docs/architecture/audits"
# Docs directly under agent config folders are team rules too (e.g. .cursor/guide.md)
RULE_DOCUMENT_TOP_DIRECTORIES = {".cursor", ".claude", ".agents"}
RULE_DOCUMENT_EXTENSIONS = (".md", ".mdc")
# Installed skill/plugin/command docs are not repo rules (external tool manuals)
NOT_RULE_DOCUMENT_DIRECTORY_NAMES = {"skills", "plugins", "commands", "agents", "node_modules"}
PRIOR_AUDIT_PATTERN = re.compile(r"audit", re.IGNORECASE)
# Content that marks setup.py as a package root (excludes ordinary modules with the same name)
PACKAGING_SETUP_PATTERN = re.compile(r"^\s*(?:from|import)\s+(?:setuptools|distutils)\b", re.MULTILINE)
ALLOWLIST_PATTERN = re.compile(r"(?:allow(?:ed|list)?|baseline|frozen)[\w.-]*\.(?:txt|allow|json)$|\.allow$", re.IGNORECASE)
# Same-named files that are not exception lists (projectops install records)
NOT_ALLOWLIST_PATHS = (".github/.projectops/",)
# Rule test traces (file path or content)
RULE_TEST_PATH_PATTERN = re.compile(r"(?:^|/)(?:test|tests|spec)/.*(?:architecture|layer|arch_|rules?_test|design_token)", re.IGNORECASE)
RULE_TEST_CONFIG_NAMES = {".importlinter", ".dependency-cruiser.js", ".dependency-cruiser.cjs", "importlinter.ini"}
MAXIMUM_LISTED = 40


def detect_project(root: Path) -> dict:
    stacks, rule_documents, skill_audits, other_audits, allowlists, rule_tests = [], [], [], [], [], []
    gradle_settings_directories = set()
    for relative, absolute in walk_files(root):
        name = absolute.name
        probe = "/" + relative
        if name in ("settings.gradle", "settings.gradle.kts"):
            gradle_settings_directories.add(str(Path(relative).parent.as_posix()))

        # Stack markers
        stack = _stack_of_marker(name, absolute)
        if stack:
            stacks.append({"stack": stack[0], "module": str(Path(relative).parent.as_posix()), "marker": name, **stack[1]})

        # Rule documents and material to carry over
        if _is_rule_document(relative, name, probe):
            rule_documents.append(relative)
        if name.endswith(".md") and relative.startswith(AUDITS_DIRECTORY + "/"):
            skill_audits.append(relative)
        elif name.endswith(".md") and PRIOR_AUDIT_PATTERN.search(name) and not _is_tool_document(relative):
            other_audits.append(relative)
        if ALLOWLIST_PATTERN.search(name) and not any(p in probe for p in NOT_ALLOWLIST_PATHS):
            allowlists.append(relative)
        if name in RULE_TEST_CONFIG_NAMES or RULE_TEST_PATH_PATTERN.search(relative) and _is_code(name):
            rule_tests.append(relative)
        elif name in ("build.gradle", "build.gradle.kts", "pyproject.toml", "setup.cfg", "package.json"):
            if _mentions_rule_tool(absolute):
                rule_tests.append(relative)

    # This skill's audits first (newest first), other audit docs after
    prior_audits = sorted(skill_audits, reverse=True) + other_audits
    stacks = _collapse_gradle_submodules(stacks, gradle_settings_directories)
    # A Flutter app's android/ is a host, not a separate stack (the flutter module is audited)
    flutter_modules = {s["module"] for s in stacks if s["stack"] == "flutter"}
    for stack in stacks:
        parent = str(Path(stack["module"]).parent.as_posix())
        if stack["stack"] == "jvm" and Path(stack["module"]).name == "android" and parent in flutter_modules:
            stack["flutter_host_of"] = parent
    return {
        "root": str(root),
        "stacks": stacks,
        "rule_documents": rule_documents[:MAXIMUM_LISTED],
        "prior_audits": prior_audits[:MAXIMUM_LISTED],
        "allowlists": allowlists[:MAXIMUM_LISTED],
        "rule_tests": rule_tests[:MAXIMUM_LISTED],
        # True only when this skill installed something (an empty audits folder has nothing to carry over)
        "has_architecture_folder": (root / "docs" / "architecture" / "rules").is_dir()
                                   or (root / "docs" / "architecture" / "CONVENTIONS.md").is_file(),
        "summary": f"stacks {sorted({s['stack'] for s in stacks})}, rule documents {len(rule_documents)}, "
                   f"prior audits {len(prior_audits)}, allowlists {len(allowlists)}, rule test traces {len(rule_tests)}",
    }


def _is_tool_document(relative: str) -> bool:
    return bool(NOT_RULE_DOCUMENT_DIRECTORY_NAMES & set(relative.split("/")[:-1]))


def _is_rule_document(relative: str, name: str, probe: str) -> bool:
    directories = relative.split("/")[:-1]
    if _is_tool_document(relative) or relative.startswith(AUDITS_DIRECTORY + "/"):
        return False
    if name in RULE_DOCUMENT_NAMES:
        return True
    if not name.endswith(RULE_DOCUMENT_EXTENSIONS):
        return False
    return any(p in probe for p in RULE_DOCUMENT_DIRECTORY_PARTS) or \
        (bool(directories) and directories[-1] in RULE_DOCUMENT_TOP_DIRECTORIES)


def _stack_of_marker(name: str, absolute: Path):
    """Marker file > (stack, extra info) or None"""
    if name == "pubspec.yaml":
        text = _read(absolute)
        return ("flutter" if re.search(r"^\s*flutter\s*:", text, re.MULTILINE) else "dart"), {}
    if name in ("build.gradle", "build.gradle.kts", "pom.xml"):
        text = _read(absolute)
        sibling_app = absolute.parent / "app" / name
        is_android = "com.android" in text or (sibling_app.is_file() and "com.android" in _read(sibling_app))
        return ("spring" if "springframework" in text else "jvm"), {"is_android": is_android}
    if name in ("pyproject.toml", "requirements.txt"):
        return "python", {}
    if name == "setup.py" and PACKAGING_SETUP_PATTERN.search(_read(absolute)):
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
    """Gradle submodules under a settings.gradle root > grouped into the root entry's modules"""
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
    for owner, children in submodules.items():  # multi-module with no build.gradle at the root
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
