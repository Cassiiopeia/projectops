"""Freeze list (ledger): docs/architecture/rules/<id>.rule violations <-> <id>.allow

2 verdicts (same as the 4 rule test templates):
- violations - allowed = new violations > fail
- allowed - violations = fixed entries > fail asking to remove them (keeps the list from loosening)
"""
from __future__ import annotations

import re
from pathlib import Path

from .source_files import walk_files

RULES_DIRECTORY_PARTS = ("docs", "architecture", "rules")
RULE_SUFFIX = ".rule"
ALLOW_SUFFIX = ".allow"
# .rule required key: pattern / optional: description, paths, extensions, exclude (comma-separated values)
LIST_KEYS = ("paths", "extensions", "exclude")
LIST_DELIMITER = ","
# Rule files themselves are always excluded (so pattern examples do not match themselves)
ALWAYS_EXCLUDED_PREFIX = "docs/architecture/"


def rules_directory(root: Path) -> Path:
    return root.joinpath(*RULES_DIRECTORY_PARTS)


def parse_rule_file(path: Path) -> dict:
    """key=value (split on the first = only, # comments) > rule dict"""
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
    """Violating file > first violating line number"""
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
            results.append({"id": rule["id"], "error": "missing pattern key"})
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
    """Initial freeze: current violations become the allow list (refused if the list exists — there is no way to add lines)"""
    rule_path = rules_directory(root) / f"{rule_id}{RULE_SUFFIX}"
    if not rule_path.exists():
        return {"ok": False, "code": "rule_not_found", "summary": f"Rule file not found: {rule_path}"}
    allow_path = _allow_path(root, rule_id)
    if allow_path.exists():
        return {"ok": False, "code": "allow_exists",
                "summary": "The freeze list already exists. Lines cannot be added to a freeze list (only removed)",
                "next": "Fix the code for new violations. Remove fixed entries with `ledger PATH tighten`"}
    violations = sorted(find_violations(root, parse_rule_file(rule_path)))
    header = [f"# {rule_id} freeze list: lines can only be removed, never added",
              "# Remove a file from this list once it is fixed (the rule test flags leftover lines)"]
    allow_path.write_text("\n".join(header + violations) + "\n", encoding="utf-8")
    return {"ok": True, "rule": rule_id, "frozen": len(violations), "allow_file": str(allow_path),
            "summary": f"{rule_id}: froze {len(violations)} current violations"}


def tighten_rules(root: Path) -> dict:
    """Remove fixed entries from the allow list (comment lines kept)"""
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
    return {"removed": removed, "summary": f"removed {sum(len(v) for v in removed.values())} lines"}


def _allow_path(root: Path, rule_id: str) -> Path:
    return rules_directory(root) / f"{rule_id}{ALLOW_SUFFIX}"


def _is_rule_target(relative: str, rule: dict) -> bool:
    if relative.startswith(ALWAYS_EXCLUDED_PREFIX) or any(relative.startswith(prefix) for prefix in rule["exclude"]):
        return False
    return not rule["extensions"] or any(relative.endswith(ext) for ext in rule["extensions"])
