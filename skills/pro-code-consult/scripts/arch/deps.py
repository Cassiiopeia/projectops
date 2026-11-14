"""deps: classify the import graph into layers > reverse edges, direct repository use across modules, Gradle module graph > cycles

4 layers + common: presentation > application > domain <- infrastructure, common (exceptions, constants — outside direction rules)
Classification order: Java/Kotlin file name suffix > exception/constant folders > folder name (deepest) > Next app router
Imports in test files are only counted, not listed as violations (test_violation_count).
"""
from __future__ import annotations

import re
from pathlib import Path

from .origins import SourceInventory
from .source_files import walk_files

LAYER_BY_DIRECTORY_NAME = {
    **dict.fromkeys(("presentation", "pages", "page", "screens", "screen", "widgets", "ui", "views", "view",
                     "controller", "controllers", "routers", "router", "routes", "components"), "presentation"),
    **dict.fromkeys(("application", "usecases", "usecase", "use_cases", "services", "service"), "application"),
    **dict.fromkeys(("domain", "models", "model", "entity", "entities"), "domain"),
    **dict.fromkeys(("data", "datasources", "sources", "repositories", "repository", "infrastructure", "infra",
                     "clients", "network", "persistence", "dao", "adapters"), "infrastructure"),
}
# Extra folder names per language (JS api folder is the HTTP client, Java object/vo are entities — Spring api packages are controllers, so not in the shared table)
LANGUAGE_LAYER_BY_DIRECTORY_NAME = {
    "javascript": {"api": "infrastructure", "apis": "infrastructure", "http": "infrastructure", "fetchers": "infrastructure",
                   "hooks": "application"},
    "java": {"object": "domain", "objects": "domain", "vo": "domain", "vos": "domain"},
}
LANGUAGE_LAYER_BY_DIRECTORY_NAME["typescript"] = LANGUAGE_LAYER_BY_DIRECTORY_NAME["javascript"]
LANGUAGE_LAYER_BY_DIRECTORY_NAME["kotlin"] = LANGUAGE_LAYER_BY_DIRECTORY_NAME["java"]
# Java/Kotlin file name suffix > layer (before folders: application/exception/XxxExceptionHandler is presentation)
JVM_LAYER_BY_SUFFIX = (
    (re.compile(r"(?:Controller|ControllerAdvice|ExceptionHandler|ControllerDocs|RestController)$"), "presentation"),
    (re.compile(r"(?:Repository|RepositoryImpl|RepositoryCustom|Dao|Mapper)$"), "infrastructure"),
    (re.compile(r"(?:Service|ServiceImpl|UseCase|Facade)$"), "application"),
)
COMMON_DIRECTORY_NAMES = {"exception", "exceptions", "error", "errors", "constant", "constants"}
# Type declaration folders (pure JS/TS types — domain shapes, not infrastructure, even under an api subfolder)
TYPE_DECLARATION_DIRECTORY_NAMES = {"types", "typings", "interfaces", "dto", "dtos", "schemas"}
# State layer (Flutter provider/notifier — whether it may import the data layer is a team decision; see the stack doc)
STATE_DIRECTORY_NAMES = {"providers", "provider", "notifiers", "controllers", "blocs", "bloc", "viewmodels", "stores"}
# Forbidden directions (from layer > layers it must not reach)
FORBIDDEN_LAYER_TARGETS = {
    "presentation": {"infrastructure"},
    "application": {"presentation"},
    "domain": {"presentation", "application", "infrastructure"},
    "infrastructure": {"presentation"},
    "common": set(),
}
# Classify layers only from after this folder in the path (avoids misclassifying top-level folder names, e.g. a client/ project)
SOURCE_ROOT_DIRECTORY_NAMES = {"lib", "src", "java", "kotlin", "app"}

IMPORT_PATTERNS = {
    "dart": re.compile(r"^[ \t]*(?:import|export)\s+['\"]([^'\"]+)['\"]", re.MULTILINE),
    "java": re.compile(r"^[ \t]*import\s+(?:static\s+)?([\w.]+)\s*;", re.MULTILINE),
    "kotlin": re.compile(r"^[ \t]*import\s+([\w.]+)", re.MULTILINE),
    "python": re.compile(r"^[ \t]*(?:from\s+(\.*[\w.]*)\s+import|import\s+([\w.]+))", re.MULTILINE),
    "javascript": re.compile(r"(?:\bfrom\s+|\bimport\s*\(\s*|\brequire\s*\(\s*|^[ \t]*import\s+)['\"]([^'\"]+)['\"]", re.MULTILINE),
}
IMPORT_PATTERNS["typescript"] = IMPORT_PATTERNS["javascript"]
JS_RESOLVE_SUFFIXES = ("", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", "/index.ts", "/index.tsx", "/index.js")


def layer_of(relative: str, language: str | None = None, is_next_module: bool = False) -> str | None:
    directories = relative.split("/")[:-1]
    stem = Path(relative).stem
    if language in ("java", "kotlin"):
        for pattern, layer in JVM_LAYER_BY_SUFFIX:
            if pattern.search(stem):
                return layer
    if COMMON_DIRECTORY_NAMES & {d.lower() for d in directories}:
        return "common"
    if language in ("javascript", "typescript") and (
            TYPE_DECLARATION_DIRECTORY_NAMES & {d.lower() for d in directories} or relative.endswith(".d.ts")):
        return "domain"
    is_next_route = is_next_module and "app" in directories
    for index in range(len(directories) - 1, -1, -1):
        if directories[index] in SOURCE_ROOT_DIRECTORY_NAMES:
            directories = directories[index + 1:]
            break
    extra = LANGUAGE_LAYER_BY_DIRECTORY_NAME.get(language or "", {})
    for name in reversed(directories):
        layer = extra.get(name.lower()) or LAYER_BY_DIRECTORY_NAME.get(name.lower())
        if layer:
            return layer
    return "presentation" if is_next_route else None


def analyze_dependencies(root: Path, limit: int, is_including_all: bool = False) -> dict:
    inventory = SourceInventory(root, is_including_all)
    sources = {relative: (language, text) for relative, language, text, _ in inventory.files}
    test_files = {relative for relative, _, _, origin in inventory.files if origin == "test"}
    resolver = _ImportResolver(root, sources)
    next_modules = _next_module_prefixes(root)
    modules = gradle_module_graph(root)

    def layer(path, language):
        return layer_of(path, language, any(path.startswith(prefix) for prefix in next_modules))

    # Collect layer edges > only forbidden directions are violations (tests are only counted)
    violations, edge_counts, test_violation_count, cross_module = [], {}, 0, []
    unclassified = {}
    aggregators = _aggregator_modules(modules)
    for relative, (language, text) in sources.items():
        from_layer = layer(relative, language)
        # Unclassified areas (JVM is classified by file suffix and packages are deep, so area tallies are meaningless)
        if not from_layer and relative not in test_files and language not in ("java", "kotlin"):
            area = _source_area(relative)
            unclassified[area] = unclassified.get(area, 0) + 1
        for line_number, target in resolver.imports_of(relative, language, text):
            if language in ("java", "kotlin") and relative not in test_files:
                _collect_cross_module(relative, line_number, target, modules["module_directories"], aggregators, cross_module)
            to_layer = layer(target, sources[target][0])
            if not from_layer or not to_layer or to_layer == from_layer:
                continue
            key = f"{from_layer}->{to_layer}"
            edge_counts[key] = edge_counts.get(key, 0) + 1
            if to_layer not in FORBIDDEN_LAYER_TARGETS[from_layer]:
                continue
            if relative in test_files:
                test_violation_count += 1
                continue
            violation = {"from": relative, "line": line_number, "to": target, "from_layer": from_layer, "to_layer": to_layer}
            if STATE_DIRECTORY_NAMES & set(relative.split("/")[:-1]):
                violation["from_role"] = "state"
            violations.append(violation)

    # Violation candidates first: those from shared-module repositories or composition modules go last (often normal by design)
    cross_module.sort(key=lambda c: (c["is_to_common_module"], c["is_from_aggregator_module"]))
    boundary_count = sum(1 for c in cross_module if not c["is_to_common_module"] and not c["is_from_aggregator_module"])
    truncated = {k: len(v) for k, v in (("layer_violations", violations), ("cross_module_repository_imports", cross_module))
                 if len(v) > limit}
    return {
        "layer_edges": edge_counts,
        "layer_violations": violations[:limit],
        "test_violation_count": test_violation_count,
        "cross_module_repository_imports": cross_module[:limit],
        "unclassified_directories": dict(sorted(unclassified.items(), key=lambda pair: -pair[1])[:10]),
        "gradle_modules": modules,
        "excluded": inventory.excluded_summary(),
        "truncated": truncated,
        "summary": f"reverse layer imports {len(violations)} (plus {test_violation_count} in tests), "
                   f"direct cross-module repository use {boundary_count} (plus {len(cross_module) - boundary_count} into common or from composition modules), "
                   f"Gradle modules {len(modules['edges'])} edges, {len(modules['cycles'])} cycles",
    }


def _source_area(relative: str) -> str:
    """Folder directly under a source root (src, lib, etc.) (for tallying unclassified areas)"""
    parts = relative.split("/")[:-1]
    for index in range(len(parts) - 1, -1, -1):
        if parts[index] in SOURCE_ROOT_DIRECTORY_NAMES:
            return "/".join(parts[:index + 2])
    return "/".join(parts[:2]) or "."


def _aggregator_modules(modules: dict) -> set:
    """Composition module: depends on more than half of the other modules (3+) (application/entry point — using several domain repositories may be by design)"""
    outgoing = {}
    for edge in modules["edges"]:
        outgoing.setdefault(edge["from"], set()).add(edge["to"])
    other_module_count = max(len(modules["module_names_by_directory"]) - 1, 1)
    names = {name for name, targets in outgoing.items() if len(targets) >= 3 and len(targets) > other_module_count / 2}
    return {directory for directory, name in modules["module_names_by_directory"].items() if name in names}


def _collect_cross_module(relative, line_number, target, module_directories, aggregators, found):
    """Direct import of another Gradle module's Repository (should go through that module's service or public API)"""
    if not re.search(r"(?:Repository|RepositoryCustom|Dao)$", Path(target).stem):
        return
    from_module, to_module = _module_of(relative, module_directories), _module_of(target, module_directories)
    if from_module and to_module and from_module != to_module:
        found.append({"from": relative, "line": line_number, "to": target, "from_module": from_module,
                      "to_module": to_module, "is_to_common_module": "common" in to_module.lower(),
                      "is_from_aggregator_module": from_module in aggregators})


def _module_of(relative: str, module_directories: list) -> str | None:
    owners = [d for d in module_directories if relative.startswith(d + "/")]
    return max(owners, key=len) if owners else None


def _next_module_prefixes(root: Path) -> list:
    prefixes = []
    for relative, absolute in walk_files(root):
        if absolute.name == "package.json":
            try:
                text = absolute.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if re.search(r'"next"\s*:', text):
                module = Path(relative).parent.as_posix()
                prefixes.append("" if module == "." else module + "/")
    return prefixes


def gradle_module_graph(root: Path) -> dict:
    """settings.gradle(.kts) include + each module's project(':x') dependencies > edges and cycles"""
    edges, module_directories, module_names_by_directory = [], [], {}
    for relative, absolute in walk_files(root):
        if not relative.endswith(("settings.gradle", "settings.gradle.kts")):
            continue
        base = absolute.parent
        text = absolute.read_text(encoding="utf-8", errors="replace")
        names = re.findall(r"['\"]:?([\w\-:]+)['\"]", " ".join(re.findall(r"include\s*\(?([^\n]+)", text)))
        for name in names:
            module_dir = base / name.replace(":", "/")
            if module_dir.is_dir():
                module_directories.append(module_dir.relative_to(root).as_posix())
                module_names_by_directory[module_directories[-1]] = name
            for build_name in ("build.gradle", "build.gradle.kts"):
                build_file = module_dir / build_name
                if build_file.exists():
                    build_text = build_file.read_text(encoding="utf-8", errors="replace")
                    for configuration, target in re.findall(r"(\w+)\s*\(?\s*project\s*\(\s*['\"]:?([\w\-:]+)['\"]", build_text):
                        edges.append({"from": name, "to": target, "configuration": configuration})
    # Test-scope dependencies (testImplementation, etc.) are not on the production classpath, so excluded from cycle detection
    production_edges = [e for e in edges if not e["configuration"].lower().startswith("test")]
    return {"edges": production_edges, "test_edges": [e for e in edges if e not in production_edges],
            "cycles": _find_cycles(production_edges), "module_directories": module_directories,
            "module_names_by_directory": module_names_by_directory}


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
    """Import string > relative path of a file in the repo (dropped if not found — external package)"""

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
