"""앱 식별자 읽기 (Flutter 루트 · Android applicationId · iOS bundle id) — detect 와 get-output-path 공용."""
from __future__ import annotations

import re
from pathlib import Path


def find_flutter_root(start: Path) -> Path | None:
    """pubspec.yaml에 flutter 의존성이 있는 디렉터리. 모노레포면 client/ 같은 하위에 있다."""
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
    # 변수 참조($(...))가 아닌 실제 값만 고른다
    for m in re.finditer(r'PRODUCT_BUNDLE_IDENTIFIER\s*=\s*([^;]+);', text):
        v = m.group(1).strip().strip('"')
        if "$" not in v and "RunnerTests" not in v:
            return v
    return None


def detected_app_package(root: Path) -> str | None:
    """프로젝트 파일이 말하는 앱 패키지: Android applicationId > iOS bundle id. Flutter 앱이 아니면 None."""
    app_root = find_flutter_root(root)
    if app_root is None:
        return None
    return android_package(app_root) or ios_bundle_id(app_root)
