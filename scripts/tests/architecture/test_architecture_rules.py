"""아키텍처 규칙 테스트: docs/architecture/rules/<id>.rule 위반 <-> <id>.allow 대조
규칙은 rules 폴더에서 고친다 (이 파일은 pro-architecture-consult 템플릿 — 판정 로직만)
"""
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

import pytest

# 탐색 제외 폴더 (다른 스택 템플릿과 같은 목록)
SKIPPED_DIRECTORY_NAMES = {
    ".git", "build", "dist", "node_modules", ".dart_tool", "Pods", ".gradle",
    "venv", ".venv", "__pycache__", ".next", "out", "target", ".idea",
}
LIST_KEYS = ("paths", "extensions", "exclude")
# 규칙 파일 자신은 판정 대상에서 늘 제외
ALWAYS_EXCLUDED_PREFIX = "docs/architecture/"


def find_rules_directory(start: Path) -> Optional[Path]:
    """현재 폴더부터 위로 docs/architecture/rules 탐색 (모노레포 서브폴더에서도 동작)"""
    for directory in [start, *start.parents]:
        candidate = directory / "docs" / "architecture" / "rules"
        if candidate.is_dir():
            return candidate
    return None


def parse_rule(path: Path) -> Dict:
    """key=value (첫 = 에서만 자름, # 주석) > 규칙"""
    rule = {"id": path.stem, "pattern": "", "paths": [], "extensions": [], "exclude": []}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if key in LIST_KEYS:
            rule[key] = [item.strip() for item in value.split(",") if item.strip()]
        elif key == "pattern":
            rule[key] = value
    return rule


def read_allow_entries(path: Path) -> List[str]:
    if not path.exists():
        return []
    lines = (raw.strip() for raw in path.read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def find_violating_files(repository_root: Path, rule: Dict) -> List[str]:
    pattern = re.compile(rule["pattern"], re.MULTILINE)
    violating = set()
    for prefix in rule["paths"] or [""]:
        base = repository_root / prefix
        candidates = [base] if base.is_file() else list(_walk(base)) if base.is_dir() else []
        for absolute in candidates:
            relative = absolute.relative_to(repository_root).as_posix()
            if relative.startswith(ALWAYS_EXCLUDED_PREFIX) or any(relative.startswith(excluded) for excluded in rule["exclude"]):
                continue
            if rule["extensions"] and not any(relative.endswith(ext) for ext in rule["extensions"]):
                continue
            if pattern.search(absolute.read_bytes().decode("utf-8", errors="replace")):
                violating.add(relative)
    return sorted(violating)


def _walk(base: Path):
    for directory, subdirectories, filenames in os.walk(base):
        subdirectories[:] = [d for d in subdirectories if d not in SKIPPED_DIRECTORY_NAMES]
        for filename in filenames:
            yield Path(directory) / filename


RULES_DIRECTORY = find_rules_directory(Path(__file__).resolve().parent)
RULE_FILES = sorted(RULES_DIRECTORY.glob("*.rule")) if RULES_DIRECTORY else []


@pytest.mark.parametrize("rule_file", RULE_FILES, ids=lambda p: p.stem)
def test_architecture_rule(rule_file):
    repository_root = RULES_DIRECTORY.parent.parent.parent
    rule = parse_rule(rule_file)
    assert rule["pattern"], f"{rule_file.name}: pattern 키가 없다"
    violating = set(find_violating_files(repository_root, rule))
    allowed = set(read_allow_entries(rule_file.with_suffix(".allow")))

    # 새 위반 (동결 목록에 없는 파일) > 코드를 고친다
    new_violations = sorted(violating - allowed)
    assert not new_violations, f"[{rule['id']}] 새 위반: {new_violations}"
    # 고쳐진 항목 > 동결 목록에서 지운다 (목록이 느슨해지지 않게)
    fixed_entries = sorted(allowed - violating)
    assert not fixed_entries, f"[{rule['id']}] 고쳐졌으니 {rule_file.stem}.allow 에서 지운다: {fixed_entries}"
