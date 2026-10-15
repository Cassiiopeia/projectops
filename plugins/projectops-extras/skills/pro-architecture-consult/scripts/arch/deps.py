"""deps: import 그래프 계층 분류 > 역방향 간선, Gradle 모듈 그래프 > 순환

계층 4개 (경로 폴더 이름으로 분류, 가장 깊은 것 우선): presentation > application > domain <- infrastructure
"""
from __future__ import annotations

import re
from pathlib import Path

from .source_files import iter_source_files, walk_files

LAYER_BY_DIRECTORY_NAME = {
    **dict.fromkeys(("presentation", "pages", "page", "screens", "screen", "widgets", "ui", "views", "view",
                     "controller", "controllers", "routers", "router", "routes", "components"), "presentation"),
    **dict.fromkeys(("application", "usecases", "usecase", "use_cases", "services", "service"), "application"),
    **dict.fromkeys(("domain", "models", "model", "entity", "entities"), "domain"),
    **dict.fromkeys(("data", "datasources", "sources", "repositories", "repository", "infrastructure", "infra",
                     "clients", "network", "persistence", "dao", "adapters"), "infrastructure"),
}
# 금지 방향 (from 계층 > 가면 안 되는 계층)
FORBIDDEN_LAYER_TARGETS = {
    "presentation": {"infrastructure"},
    "application": {"presentation"},
    "domain": {"presentation", "application", "infrastructure"},
    "infrastructure": {"presentation"},
}
# 경로에서 이 폴더 뒤부터만 계층 판정 (레포 최상위 폴더 이름 오분류 방지: 예 client/ 프로젝트)
SOURCE_ROOT_DIRECTORY_NAMES = {"lib", "src", "java", "kotlin", "app"}

IMPORT_PATTERNS = {
    "dart": re.compile(r"^\s*(?:import|export)\s+['\"]([^'\"]+)['\"]", re.MULTILINE),
    "java": re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;", re.MULTILINE),
    "kotlin": re.compile(r"^\s*import\s+([\w.]+)", re.MULTILINE),
    "python": re.compile(r"^\s*(?:from\s+(\.*[\w.]*)\s+import|import\s+([\w.]+))", re.MULTILINE),
    "javascript": re.compile(r"(?:\bfrom\s+|\bimport\s*\(\s*|\brequire\s*\(\s*|^\s*import\s+)['\"]([^'\"]+)['\"]", re.MULTILINE),
}
IMPORT_PATTERNS["typescript"] = IMPORT_PATTERNS["javascript"]
JS_RESOLVE_SUFFIXES = ("", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", "/index.ts", "/index.tsx", "/index.js")


def layer_of(relative: str) -> str | None:
    directories = relative.split("/")[:-1]
    for index in range(len(directories) - 1, -1, -1):
        if directories[index] in SOURCE_ROOT_DIRECTORY_NAMES:
            directories = directories[index + 1:]
            break
    for name in reversed(directories):
        layer = LAYER_BY_DIRECTORY_NAME.get(name.lower())
        if layer:
            return layer
    return None


def analyze_dependencies(root: Path, limit: int) -> dict:
    sources = {relative: (language, text) for relative, language, text in iter_source_files(root)}
    resolver = _ImportResolver(root, sources)

    # 계층 간선 수집 > 금지 방향만 위반으로
    violations, edge_counts = [], {}
    for relative, (language, text) in sources.items():
        from_layer = layer_of(relative)
        if not from_layer:
            continue
        for line_number, target in resolver.imports_of(relative, language, text):
            to_layer = layer_of(target)
            if not to_layer or to_layer == from_layer:
                continue
            key = f"{from_layer}->{to_layer}"
            edge_counts[key] = edge_counts.get(key, 0) + 1
            if to_layer in FORBIDDEN_LAYER_TARGETS[from_layer]:
                violations.append({"from": relative, "line": line_number, "to": target,
                                   "from_layer": from_layer, "to_layer": to_layer})

    modules = gradle_module_graph(root)
    return {
        "layer_edges": edge_counts,
        "layer_violations": violations[:limit],
        "gradle_modules": modules,
        "truncated": {"layer_violations": len(violations)} if len(violations) > limit else {},
        "summary": f"계층 역방향 {len(violations)}, Gradle 모듈 {len(modules['edges'])}개 간선·순환 {len(modules['cycles'])}",
    }


def gradle_module_graph(root: Path) -> dict:
    """settings.gradle(.kts) include + 각 모듈 project(':x') 의존 > 간선·순환"""
    edges = []
    for relative, absolute in walk_files(root):
        if not relative.endswith(("settings.gradle", "settings.gradle.kts")):
            continue
        base = absolute.parent
        text = absolute.read_text(encoding="utf-8", errors="replace")
        names = re.findall(r"['\"]:?([\w\-:]+)['\"]", " ".join(re.findall(r"include\s*\(?([^\n]+)", text)))
        for name in names:
            module_dir = base / name.replace(":", "/")
            for build_name in ("build.gradle", "build.gradle.kts"):
                build_file = module_dir / build_name
                if build_file.exists():
                    build_text = build_file.read_text(encoding="utf-8", errors="replace")
                    for configuration, target in re.findall(r"(\w+)\s*\(?\s*project\s*\(\s*['\"]:?([\w\-:]+)['\"]", build_text):
                        edges.append({"from": name, "to": target, "configuration": configuration})
    # 테스트 범위 의존(testImplementation 등)은 운영 클래스패스가 아니라 순환 판정에서 제외
    production_edges = [e for e in edges if not e["configuration"].lower().startswith("test")]
    return {"edges": production_edges, "test_edges": [e for e in edges if e not in production_edges],
            "cycles": _find_cycles(production_edges)}


def _find_cycles(edges: list[dict]) -> list[list[str]]:
    graph: dict[str, list[str]] = {}
    for edge in edges:
        graph.setdefault(edge["from"], []).append(edge["to"])
    cycles, seen = [], set()

    def visit(node, stack):
        if node in stack:
            cycle = stack[stack.index(node):] + [node]
            signature = tuple(sorted(set(cycle)))
            if signature not in seen:
                seen.add(signature)
                cycles.append(cycle)
            return
        for neighbor in graph.get(node, []):
            visit(neighbor, stack + [node])

    for start in list(graph):
        visit(start, [])
    return cycles


class _ImportResolver:
    """import 문자열 > 레포 안 파일 상대경로 (못 찾으면 버림 — 외부 패키지)"""

    def __init__(self, root: Path, sources: dict):
        self.root = root
        self.sources = sources
        self.java_files_by_class = {}
        self.dart_package_lib = self._dart_packages()
        for relative, (language, text) in sources.items():
            if language in ("java", "kotlin"):
                package = re.search(r"^\s*package\s+([\w.]+)", text, re.MULTILINE)
                if package:
                    self.java_files_by_class[f"{package.group(1)}.{Path(relative).stem}"] = relative

    def imports_of(self, relative: str, language: str, text: str):
        for match in IMPORT_PATTERNS[language].finditer(text):
            raw = next(group for group in match.groups() if group is not None)
            target = self._resolve(relative, language, raw)
            if target and target != relative:
                yield text.count("\n", 0, match.start()) + 1, target

    def _resolve(self, relative: str, language: str, raw: str) -> str | None:
        here = Path(relative).parent
        if language == "dart":
            if raw.startswith("package:"):
                package, _, rest = raw[len("package:"):].partition("/")
                lib = self.dart_package_lib.get(package)
                return self._existing(f"{lib}/{rest}" if lib else None)
            return self._existing(_normalize(here / raw)) if not raw.startswith("dart:") else None
        if language in ("java", "kotlin"):
            return self.java_files_by_class.get(raw)
        if language == "python":
            return self._resolve_python(here, raw)
        if raw.startswith("."):
            base = _normalize(here / raw)
        elif raw.startswith(("@/", "~/")):
            base = self._js_alias_base(relative) + raw[2:]
        else:
            return None
        return next((c for c in (base + s for s in JS_RESOLVE_SUFFIXES) if c in self.sources), None)

    def _resolve_python(self, here: Path, raw: str) -> str | None:
        dots = len(raw) - len(raw.lstrip("."))
        dotted = raw.lstrip(".").replace(".", "/")
        if dots:
            base = here
            for _ in range(dots - 1):
                base = base.parent
            stems = [_normalize(base / dotted) if dotted else _normalize(base)]
        else:
            stems = [dotted] + [f"{p}/{dotted}" for p in self._python_roots()]
        for stem in stems:
            for candidate in (f"{stem}.py", f"{stem}/__init__.py"):
                if candidate in self.sources:
                    return candidate
        return None

    def _python_roots(self):
        roots = {str(Path(r).parent.as_posix()) for r in self.sources if r.endswith(("pyproject.toml",))}
        roots |= {r.split("/src/")[0] + "/src" for r in self.sources if "/src/" in r and r.endswith(".py")}
        return sorted(roots)

    def _js_alias_base(self, relative: str) -> str:
        parts = relative.split("/")
        if "src" in parts:
            return "/".join(parts[:parts.index("src") + 1]) + "/"
        return ""

    def _dart_packages(self) -> dict:
        packages = {}
        for relative, absolute in walk_files(self.root):
            if relative.endswith("pubspec.yaml"):
                name = re.search(r"^name:\s*([\w]+)", absolute.read_text(encoding="utf-8", errors="replace"), re.MULTILINE)
                if name:
                    module = str(Path(relative).parent.as_posix())
                    packages[name.group(1)] = f"{module}/lib" if module != "." else "lib"
        return packages

    def _existing(self, candidate: str | None) -> str | None:
        return candidate if candidate in self.sources else None


def _normalize(path: Path) -> str:
    parts = []
    for part in path.as_posix().split("/"):
        if part == "..":
            if parts:
                parts.pop()
        elif part not in (".", ""):
            parts.append(part)
    return "/".join(parts)
