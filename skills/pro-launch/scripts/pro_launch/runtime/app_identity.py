"""Reading app identifiers (Flutter root · Android applicationId · iOS bundle id) — shared by detect and get-output-path."""
from __future__ import annotations

import re
from pathlib import Path


def find_flutter_root(start: Path) -> Path | None:
    """Directory whose pubspec.yaml has the flutter dependency. In monorepos it is under a subfolder like client/."""
    for p in sorted(start.rglob("pubspec.yaml")):
        if "build" in p.parts or ".dart_tool" in p.parts:
            continue
        if len(p.relative_to(start).parts) > 4:
            continue
        try:
            if "flutter:" in p.read_text(encoding="utf-8", errors="ignore"):
                return p.parent
        except OSError:
            continue
    return None


def android_package(root: Path) -> str | None:
    for name in ("build.gradle.kts", "build.gradle"):
        f = root / "android" / "app" / name
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'applicationId\s*=?\s*["\']([\w.]+)["\']', text)
        if m:
            return m.group(1)
    return None


def ios_bundle_id(root: Path) -> str | None:
    f = root / "ios" / "Runner.xcodeproj" / "project.pbxproj"
    if not f.exists():
        return None
    text = f.read_text(encoding="utf-8", errors="ignore")
    # Pick only real values, not variable references ($(...))
    for m in re.finditer(r'PRODUCT_BUNDLE_IDENTIFIER\s*=\s*([^;]+);', text):
        v = m.group(1).strip().strip('"')
        if "$" not in v and "RunnerTests" not in v:
            return v
    return None


def detected_app_package(root: Path) -> str | None:
    """App package the project files declare: Android applicationId > iOS bundle id. None if not a Flutter app."""
    app_root = find_flutter_root(root)
    if app_root is None:
        return None
    return android_package(app_root) or ios_bundle_id(app_root)
