"""conventions·install-tests·get-output-path: 스킬 정본 > 대상 프로젝트 설치 (덮어쓰지 않음)

설치본 머리 표식 1줄: <!-- pro-code-consult:installed sha256=<정본 본문 해시> -->
(옛 스킬 이름 pro-architecture-consult 표식도 같은 설치본으로 읽음)
상태 4종: same(정본과 같음) / outdated(정본이 바뀜) / locally_modified(프로젝트 자체 수정본 — 그 프로젝트의 규칙) / missing
"""
from __future__ import annotations

import hashlib
import re
import shutil
from datetime import date
from pathlib import Path

from .detect import AUDITS_DIRECTORY

SKILL_DIRECTORY = Path(__file__).resolve().parents[2]
CONVENTIONS_SOURCE = SKILL_DIRECTORY / "references" / "conventions.md"
STACK_SOURCES_DIRECTORY = SKILL_DIRECTORY / "references" / "stacks"
RULE_TEST_TEMPLATES_DIRECTORY = SKILL_DIRECTORY / "templates" / "rule-tests"

STACKS = ("flutter", "spring", "python", "javascript")
INSTALLED_MARKER_PATTERN = re.compile(r"^<!-- pro-(?:code|architecture)-consult:installed sha256=([0-9a-f]{64}) -->\n\n?")
# 규칙 테스트 템플릿 > 모듈 안 설치 위치
RULE_TEST_DESTINATIONS = {
    "flutter": ("architecture_rules_test.dart", "test/architecture/architecture_rules_test.dart"),
    "spring": ("ArchitectureRulesTest.java", "src/test/java/architecture/ArchitectureRulesTest.java"),
    "python": ("test_architecture_rules.py.tmpl", "tests/architecture/test_architecture_rules.py"),  # .tmpl: 이 레포 pytest 수집 제외
    "javascript": ("architecture.rules.test.mjs", "test/architecture/architecture.rules.test.mjs"),
}
OUTPUT_TITLE_ALLOWED_PATTERN = re.compile(r"[^\w가-힣\-]+")
MAXIMUM_TITLE_LENGTH = 60


def installed_documents(root: Path, stacks: list[str]) -> list[tuple[Path, Path]]:
    """(정본, 설치 위치) 목록: 규칙 정본 1개 + 지정 스택 문서"""
    architecture = root / "docs" / "architecture"
    pairs = [(CONVENTIONS_SOURCE, architecture / "CONVENTIONS.md")]
    pairs += [(STACK_SOURCES_DIRECTORY / f"{s}.md", architecture / "stacks" / f"{s}.md") for s in stacks]
    return pairs


def check_installed(root: Path, stacks: list[str]) -> dict:
    statuses = [{"source": source.name, "installed": str(target.relative_to(root)), "status": _status(source, target)}
                for source, target in installed_documents(root, stacks)]
    return {"documents": statuses,
            "summary": ", ".join(f"{s['installed']}={s['status']}" for s in statuses)}


def install_documents(root: Path, stacks: list[str], is_force: bool) -> dict:
    written, skipped = [], []
    for source, target in installed_documents(root, stacks):
        status = _status(source, target)
        if status == "same" or (status != "missing" and not is_force):
            skipped.append({"installed": str(target.relative_to(root)), "status": status})
            continue
        body = source.read_text(encoding="utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"<!-- pro-code-consult:installed sha256={_hash(body)} -->\n\n{body}", encoding="utf-8")
        written.append(str(target.relative_to(root)))
    return {"written": written, "skipped": skipped,
            "summary": f"installed {len(written)}, skipped {len(skipped)}",
            "next": "Add the paragraph linking docs/architecture/CONVENTIONS.md to CLAUDE.md and AGENTS.md (references/init.md)"}


def install_rule_test(root: Path, stack: str, module: str, is_force: bool) -> dict:
    template_name, destination = RULE_TEST_DESTINATIONS[stack]
    target = root / module / destination
    rules = root / "docs" / "architecture" / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    readme = rules / "README.md"
    if not readme.exists():
        shutil.copyfile(RULE_TEST_TEMPLATES_DIRECTORY / "rules-README.md", readme)
    if target.exists() and not is_force:
        return {"ok": False, "code": "exists", "summary": f"Already exists: {target.relative_to(root)}",
                "next": "Compare the contents and merge by hand. Use --force to overwrite only when the user asks"}
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(RULE_TEST_TEMPLATES_DIRECTORY / stack / template_name, target)
    return {"installed": str(target.relative_to(root)), "rules_directory": str(rules.relative_to(root)),
            "summary": f"{stack} rule test installed: {target.relative_to(root)}",
            "next": "Add rules as docs/architecture/rules/<id>.rule, then run `ledger PATH freeze --rule <id>`"}


def audit_output_path(root: Path, title: str) -> dict:
    """경로 계산만 (폴더를 만들지 않는다 — 승인 전 호출해도 대상 레포가 바뀌지 않게, 폴더는 보고서를 쓸 때 생긴다)"""
    slug = OUTPUT_TITLE_ALLOWED_PATTERN.sub("_", title.strip()).strip("_")[:MAXIMUM_TITLE_LENGTH] or "audit"
    audits = root / AUDITS_DIRECTORY
    path = audits / f"{date.today().isoformat()}_{slug}.md"
    previous = sorted(p.relative_to(root).as_posix() for p in audits.glob("*.md")) if audits.is_dir() else []
    return {"path": str(path), "exists": path.exists(), "previous_audits": previous, "summary": str(path.relative_to(root))}


def _status(source: Path, target: Path) -> str:
    if not target.exists():
        return "missing"
    text = target.read_text(encoding="utf-8")
    marker = INSTALLED_MARKER_PATTERN.match(text)
    if not marker:
        return "locally_modified"
    body = text[marker.end():]
    if _hash(body) != marker.group(1):
        return "locally_modified"
    return "same" if marker.group(1) == _hash(source.read_text(encoding="utf-8")) else "outdated"


def _hash(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()
