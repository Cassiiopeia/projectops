"""detect: 스택·모듈 루트, 규칙 문서, 이어받을 것(기존 감사 문서·예외 목록·규칙 테스트)"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .source_files import walk_files

RULE_DOCUMENT_NAMES = {"CLAUDE.md", "claude.md", "AGENTS.md", "GEMINI.md", ".cursorrules", "copilot-instructions.md"}
RULE_DOCUMENT_DIRECTORY_PARTS = ("/.claude/rules/", "/.cursor/rules/", "/docs/architecture/")
# 이 스킬의 감사 보고서 폴더 (get-output-path 가 쓰는 곳 — 규칙 문서가 아니라 지난 감사)
AUDITS_DIRECTORY = "docs/architecture/audits"
# 에이전트 설정 폴더 바로 아래 문서도 팀 규칙 (.cursor/가이드.md 같은 자리)
RULE_DOCUMENT_TOP_DIRECTORIES = {".cursor", ".claude", ".agents"}
RULE_DOCUMENT_EXTENSIONS = (".md", ".mdc")
# 설치한 스킬·플러그인·명령 문서는 레포 규칙이 아니다 (외부 도구 설명서)
NOT_RULE_DOCUMENT_DIRECTORY_NAMES = {"skills", "plugins", "commands", "agents", "node_modules"}
PRIOR_AUDIT_PATTERN = re.compile(r"audit", re.IGNORECASE)
# setup.py 가 패키지 루트일 때의 본문 (같은 이름의 일반 모듈 제외)
PACKAGING_SETUP_PATTERN = re.compile(r"^\s*(?:from|import)\s+(?:setuptools|distutils)\b", re.MULTILINE)
ALLOWLIST_PATTERN = re.compile(r"(?:allow(?:ed|list)?|baseline|frozen)[\w.-]*\.(?:txt|allow|json)$|\.allow$", re.IGNORECASE)
# 예외 목록이 아닌 같은 이름 파일 (projectops 설치 기록)
NOT_ALLOWLIST_PATHS = (".github/.projectops/",)
# 규칙 테스트 흔적 (파일 경로 또는 본문)
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

        # 스택 표식
        stack = _stack_of_marker(name, absolute)
        if stack:
            stacks.append({"stack": stack[0], "module": str(Path(relative).parent.as_posix()), "marker": name, **stack[1]})

        # 규칙 문서 · 이어받을 자료
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

    # 이 스킬이 남긴 감사 먼저 (최신순), 그 밖의 audit 문서는 뒤
    prior_audits = sorted(skill_audits, reverse=True) + other_audits
    stacks = _collapse_gradle_submodules(stacks, gradle_settings_directories)
    # Flutter 앱의 android/ 는 별도 스택이 아니라 호스트 (감사 대상은 flutter 모듈)
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
        # 이 스킬이 설치한 것이 있을 때만 참 (빈 audits 폴더만으로는 이어받을 것이 없다)
        "has_architecture_folder": (root / "docs" / "architecture" / "rules").is_dir()
                                   or (root / "docs" / "architecture" / "CONVENTIONS.md").is_file(),
        "summary": f"스택 {sorted({s['stack'] for s in stacks})}, 규칙 문서 {len(rule_documents)}, "
                   f"기존 감사 {len(prior_audits)}, 예외 목록 {len(allowlists)}, 규칙 테스트 흔적 {len(rule_tests)}",
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
    """표식 파일 > (스택, 부가 정보) 또는 None"""
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
