"""동결 목록(ledger): docs/architecture/rules/<id>.rule 위반 <-> <id>.allow 대조

판정 2종 (규칙 테스트 템플릿 4종과 동일):
- 위반 - 허용 = 새 위반 > 실패
- 허용 - 위반 = 고쳐진 항목 > 목록에서 지우라고 실패 (목록이 느슨해지지 않게)
"""
from __future__ import annotations

import re
from pathlib import Path

from .source_files import walk_files

RULES_DIRECTORY_PARTS = ("docs", "architecture", "rules")
RULE_SUFFIX = ".rule"
ALLOW_SUFFIX = ".allow"
# .rule 필수 키: pattern / 선택: description, paths, extensions, exclude (값 구분자 쉼표)
LIST_KEYS = ("paths", "extensions", "exclude")
LIST_DELIMITER = ","
# 규칙 파일 자신은 판정 대상에서 늘 제외 (패턴 예시가 자기 자신에 걸리지 않게)
ALWAYS_EXCLUDED_PREFIX = "docs/architecture/"


def rules_directory(root: Path) -> Path:
    return root.joinpath(*RULES_DIRECTORY_PARTS)


def parse_rule_file(path: Path) -> dict:
    """key=value (첫 = 에서만 자름, # 주석) > 규칙 dict"""
    rule = {"id": path.stem, "description": "", "pattern": "", "paths": [], "extensions": [], "exclude": []}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if key in LIST_KEYS:
            rule[key] = [item.strip() for item in value.split(LIST_DELIMITER) if item.strip()]
        elif key in ("description", "pattern"):
            rule[key] = value
    return rule


def parse_allow_file(path: Path) -> list[str]:
    if not path.exists():
        return []
    entries = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            entries.append(line)
    return entries


def load_rules(root: Path) -> list[dict]:
    directory = rules_directory(root)
    if not directory.is_dir():
        return []
    return [parse_rule_file(path) for path in sorted(directory.glob(f"*{RULE_SUFFIX}"))]


def find_violations(root: Path, rule: dict) -> dict[str, int]:
    """위반 파일 > 첫 위반 줄 번호"""
    pattern = re.compile(rule["pattern"], re.MULTILINE)
    violations: dict[str, int] = {}
    for prefix in rule["paths"] or [""]:
        base = root / prefix
        candidates = [(prefix, base)] if base.is_file() else (walk_files(root, base) if base.is_dir() else [])
        for relative, absolute in candidates:
            if relative in violations or not _is_rule_target(relative, rule):
                continue
            text = absolute.read_bytes().decode("utf-8", errors="replace")
            match = pattern.search(text)
            if match:
                violations[relative] = text.count("\n", 0, match.start()) + 1
    return violations


def check_rules(root: Path) -> dict:
    results, failing = [], 0
    for rule in load_rules(root):
        if not rule["pattern"]:
            results.append({"id": rule["id"], "error": "pattern 키가 없다"})
            failing += 1
            continue
        violations = find_violations(root, rule)
        allowed = set(parse_allow_file(_allow_path(root, rule["id"])))
        new = sorted(set(violations) - allowed)
        fixed = sorted(allowed - set(violations))
        failing += 1 if (new or fixed) else 0
        results.append({
            "id": rule["id"], "description": rule["description"], "violations": len(violations),
            "allowed": len(allowed), "new": [{"path": p, "line": violations[p]} for p in new], "fixed": fixed,
        })
    return {"rules": results, "failing_rules": failing}


def freeze_rule(root: Path, rule_id: str) -> dict:
    """최초 동결: 현재 위반을 허용 목록으로 (목록이 이미 있으면 거부 — 줄을 더하는 경로는 없다)"""
    rule_path = rules_directory(root) / f"{rule_id}{RULE_SUFFIX}"
    if not rule_path.exists():
        return {"ok": False, "code": "rule_not_found", "summary": f"규칙 파일 없음: {rule_path}"}
    allow_path = _allow_path(root, rule_id)
    if allow_path.exists():
        return {"ok": False, "code": "allow_exists",
                "summary": "동결 목록이 이미 있다. 동결 목록에는 줄을 더할 수 없다 (지우기만 가능)",
                "next": "새 위반은 코드를 고친다. 고쳐진 항목은 `ledger PATH tighten`"}
    violations = sorted(find_violations(root, parse_rule_file(rule_path)))
    header = [f"# {rule_id} 동결 목록: 줄을 지울 수만 있고 더할 수 없다",
              "# 고친 파일은 이 목록에서 지운다 (규칙 테스트가 남은 줄을 잡는다)"]
    allow_path.write_text("\n".join(header + violations) + "\n", encoding="utf-8")
    return {"ok": True, "rule": rule_id, "frozen": len(violations), "allow_file": str(allow_path),
            "summary": f"{rule_id}: 현재 위반 {len(violations)}개 동결"}


def tighten_rules(root: Path) -> dict:
    """고쳐진 항목을 허용 목록에서 삭제 (주석 줄은 유지)"""
    removed = {}
    for rule in load_rules(root):
        allow_path = _allow_path(root, rule["id"])
        if not allow_path.exists() or not rule["pattern"]:
            continue
        violations = find_violations(root, rule)
        kept, dropped = [], []
        for raw in allow_path.read_text(encoding="utf-8").splitlines():
            entry = raw.strip()
            if entry and not entry.startswith("#") and entry not in violations:
                dropped.append(entry)
            else:
                kept.append(raw)
        if dropped:
            allow_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
            removed[rule["id"]] = dropped
    return {"removed": removed, "summary": f"{sum(len(v) for v in removed.values())}줄 삭제"}


def _allow_path(root: Path, rule_id: str) -> Path:
    return rules_directory(root) / f"{rule_id}{ALLOW_SUFFIX}"


def _is_rule_target(relative: str, rule: dict) -> bool:
    if relative.startswith(ALWAYS_EXCLUDED_PREFIX) or any(relative.startswith(prefix) for prefix in rule["exclude"]):
        return False
    return not rule["extensions"] or any(relative.endswith(ext) for ext in rule["extensions"])
