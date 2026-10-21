#!/usr/bin/env python3
# ===================================================================
# template_initializer.py — GitHub 템플릿 초기화 (.sh의 Python 포팅, #448)
# ===================================================================
#
# GitHub "Use this template"로 새 프로젝트가 생성될 때 실행해 프로젝트를
# 초기 상태로 설정한다. 크로스 플랫폼(Windows/macOS/Linux) 표준 라이브러리 전용.
# 기존 template_initializer.sh는 이 파일로 위임하는 shim이다.
#
# 사용법:
#   python template_initializer.py [-v VERSION] [-t TYPE]
#     -v/--version : 초기 버전 (기본 0.0.0)
#     -t/--type    : 프로젝트 타입 (기본 basic)
# ===================================================================

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

VALID_TYPES = ["spring", "flutter", "react", "react-native", "react-native-expo", "node", "python", "basic"]
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def print_step(msg): print(f"▶ {msg}", file=sys.stderr)
def print_info(msg): print(f"  → {msg}", file=sys.stderr)
def print_success(msg): print(f"✓ {msg}", file=sys.stderr)
def print_warning(msg): print(f"⚠ {msg}", file=sys.stderr)
def print_error(msg): print(f"✗ {msg}", file=sys.stderr)


def run(cmd):
    """git/gh 명령 실행 — 실패 시 빈 문자열 반환 (배포 파이프라인 보호)."""
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=30)
        return (out.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def get_template_version() -> str:
    vf = Path("version.yml")
    if vf.is_file():
        for line in vf.read_text(encoding="utf-8").split("\n"):
            m = re.match(r'^version:\s*"?([^"\s]+)"?', line)
            if m:
                return m.group(1)
    return "unknown"


def validate_version(v: str):
    if not VERSION_RE.match(v):
        print_error(f"Invalid version format: {v}")
        print_error("Expected format: x.y.z (e.g. 1.0.0, 2.1.3)")
        sys.exit(1)


def validate_project_type(t: str):
    if t not in VALID_TYPES:
        print_error(f"Unsupported project type: {t}")
        print_error(f"Supported types: {' '.join(VALID_TYPES)}")
        sys.exit(1)


def detect_default_branch() -> str:
    print_step("Detecting the default branch...")
    if shutil.which("gh"):
        d = run(["gh", "repo", "view", "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name"])
        if d:
            print_info(f"Detected with gh CLI: {d}")
            return d
    d = run(["git", "symbolic-ref", "refs/remotes/origin/HEAD"])
    if d:
        d = d.replace("refs/remotes/origin/", "")
        print_info(f"Detected with git symbolic-ref: {d}")
        return d
    show = run(["git", "remote", "show", "origin"])
    for line in show.split("\n"):
        if "HEAD branch" in line:
            d = line.split(":")[-1].strip()
            if d:
                print_info(f"Detected with git remote show: {d}")
                return d
    print_warning("Auto-detection failed, using the default: main")
    return "main"


def create_version_yml(version, ptype, branch, user, template_version):
    print_step("Creating version.yml...")
    print_info(f"Version: {version}")
    print_info(f"Type: {ptype}")
    print_info(f"Branch: {branch}")
    print_info(f"User: {user}")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    content = f"""# ===================================================================
# 프로젝트 버전 관리 파일
# ===================================================================
#
# 이 파일은 다양한 프로젝트 타입에서 버전 정보를 중앙 관리하기 위한 파일
# GitHub Actions 워크플로우가 이 파일을 읽어 자동으로 버전을 관리
#
# 사용법:
# 1. version: "1.0.0" - 사용자에게 표시되는 버전
# 2. version_code: 1 - Play Store/App Store 빌드 번호 (1부터 자동 증가)
# 3. project_types: 프로젝트 타입 배열 — 첫 항목이 primary
#
# 자동 버전 업데이트:
# - version_code: 매 빌드마다 자동으로 1씩 증가 (아래 판정과 무관)
# - 버전 승격 폭은 metadata.template.options.semver_auto 가 정합니다
#   semver_auto: true  -> 릴리스 구간 커밋 제목으로 판정
#                         "제목 : feat! : 내용" 또는 "feat!:" -> major (x+1.0.0)
#                         "제목 : feat : 내용"  또는 "feat:"  -> minor (x.y+1.0)
#                         그 외(fix/docs/chore/refactor/test) -> patch (x.y.z+1)
#   키 없음 / false     -> 항상 patch +1
# - 위 판정과 무관하게 version 값을 직접 수정해도 됩니다
#
# 프로젝트 타입별 동기화 파일:
# - spring: build.gradle (version = "x.y.z")
# - flutter: pubspec.yaml (version: x.y.z+i, buildNumber 포함)
# - react/node: package.json ("version": "x.y.z")
# - react-native: iOS Info.plist 또는 Android build.gradle
# - react-native-expo: app.json (expo.version)
# - python: pyproject.toml (version = "x.y.z")
# - basic/기타: version.yml 파일만 사용
#
# 주의사항:
# - project_types는 최초 설정 후 변경하지 마세요
# - 버전은 항상 높은 버전으로 자동 동기화됩니다
# ===================================================================

version: "{version}"
version_code: 1  # app build number
project_types: ["{ptype}"]   # 멀티타입 배열 — 첫 항목이 primary, 직접 편집 가능
metadata:
  last_updated: "{now}"
  last_updated_by: "{user}"
  default_branch: "{branch}"
  template:
    source: "projectops"
    version: "{template_version}"
    initialized_date: "{today}"
    options:
      # semver 자동 승격 (#546) — 릴리스 구간 커밋 제목으로 major/minor/patch 결정.
      # npx projectops로 신규 통합할 때와 동일한 기본값이다 (생성 경로에 따라 갈리지 않게).
      semver_auto: true
      # 이슈/PR 템플릿 언어와 상태 라벨 표기 (#769, #776) — 이 레포는 영문 원본으로 만들어졌다.
      # 키를 비워 두면 npx projectops 가 "기존 통합 레포"로 보고 한국어로 되돌린다.
      language: en
      label_style: en
"""
    Path("version.yml").write_text(content, encoding="utf-8", newline="\n")
    print_success("version.yml created.")


def update_workflow_triggers(branch):
    if branch == "main":
        print_info("The branch is main, so no workflow changes are needed")
        print_info("All workflows use the main branch as their trigger by default")
        return

    print_step(f"Changing workflow trigger branch: main → {branch}")
    main_branch_workflows = ["PROJECT-VERSION-CONTROL.yaml"]
    updated = 0
    for wf in main_branch_workflows:
        f = Path(".github/workflows") / wf
        if not f.is_file():
            print_warning(f"{wf} does not exist")
            continue
        text = f.read_text(encoding="utf-8")
        if 'branches: ["main"]' in text:
            f.write_text(text.replace('branches: ["main"]', f'branches: ["{branch}"]'), encoding="utf-8", newline="\n")
        elif "branches: ['main']" in text:
            f.write_text(text.replace("branches: ['main']", f"branches: ['{branch}']"), encoding="utf-8", newline="\n")
        else:
            print_warning(f"No main branch trigger found in {wf}")
            continue
        print(f"  ✓ {wf}", file=sys.stderr)
        updated += 1
    if updated > 0:
        print_success(f"Updated {updated} workflow file(s)")
    else:
        print_warning("No workflow files to update")


# 삭제 대상 — (경로, 사람이 읽는 라벨). 파일/폴더 자동 판별.
# ⚠️ 루트에 마켓플레이스/템플릿 전용 파일을 추가하면 여기에도 등록해야 한다 (CLAUDE.md 규칙).
CLEANUP_TARGETS = [
    ("CHANGELOG.md", "Remove CHANGELOG.md"),
    ("CHANGELOG.json", "Remove CHANGELOG.json"),
    ("plugins", "Remove plugins folder (marketplace-only extras plugin)"),
    ("hooks", "Remove hooks folder (Claude Code plugin hooks)"),
    ("LICENSE", "Remove LICENSE"),
    ("CONTRIBUTING.md", "Remove CONTRIBUTING.md"),
    ("SECURITY.md", "Remove SECURITY.md"),
    ("CODE_OF_CONDUCT.md", "Remove CODE_OF_CONDUCT.md (this repository's own report contact)"),
    ("ARCHITECTURE.md", "Remove ARCHITECTURE.md"),
    (".github/CODEOWNERS", "Remove CODEOWNERS (owners of this repository)"),
    (".github/i18n", "Remove i18n overlay folder (Korean templates, this repository only)"),
    (".github/ISSUE_TEMPLATE/projectops-installer-bug.yml", "Remove projectops installer bug form (this repository only)"),
    ("CLAUDE.md", "Remove CLAUDE.md"),
    ("AGENTS.md", "Remove AGENTS.md"),
    ("GEMINI.md", "Remove GEMINI.md"),
    ("llms.txt", "Remove llms.txt (this repository only)"),
    ("gemini-extension.json", "Remove gemini-extension.json"),
    (".github/scripts/test", "Remove .github/scripts/test folder"),
    (".github/workflows/PROJECT-TEMPLATE-PLUGIN-VERSION-SYNC.yaml", "Remove PROJECT-TEMPLATE-PLUGIN-VERSION-SYNC.yaml (marketplace only)"),
    (".github/workflows/PROJECT-TEMPLATE-NPM-PUBLISH.yaml", "Remove PROJECT-TEMPLATE-NPM-PUBLISH.yaml (marketplace only)"),
    (".github/workflows/PROJECT-TEMPLATE-DOCS-DEPLOY.yaml", "Remove PROJECT-TEMPLATE-DOCS-DEPLOY.yaml (marketplace only)"),
    (".github/workflows/PROJECT-TEMPLATE-SYNC-COMMUNITY-LABELS.yaml", "Remove PROJECT-TEMPLATE-SYNC-COMMUNITY-LABELS.yaml (this repository only)"),
    (".github/config/community-labels.yml", "Remove community-labels.yml (this repository's community labels)"),
    ("site", "Remove site folder (docs site settings — this repository only)"),
    (".github/workflows/PROJECT-TEMPLATE-CI.yaml", "Remove PROJECT-TEMPLATE-CI.yaml (marketplace only)"),
    ("docs", "Remove docs folder"),
    (".claude-plugin", "Remove .claude-plugin folder (plugin manifest)"),
    (".codex-plugin", "Remove .codex-plugin folder (plugin manifest)"),
    (".agents", "Remove .agents folder (Codex marketplace metadata)"),
    (".cursor", "Remove .cursor folder (IDE skill copies)"),
    ("skills", "Remove skills folder (marketplace-only skills)"),
    ("scripts", "Remove scripts folder (marketplace-only scripts)"),
    ("package.json", "Remove package.json (pi package manifest)"),
    ("bin", "Remove bin folder (projectops CLI)"),
    ("src", "Remove src folder (projectops CLI)"),
    ("harness", "Remove harness folder (pi Persona Harness)"),
    (".suh-template.example", "Remove .suh-template.example folder (template only)"),
    # 릴리스마다 changelog-deploy가 재생성하는 템플릿 레포 전용 산출물
    ("pr_body.md", "Remove pr_body.md (template repo release artifact)"),
]


def cleanup_template_files():
    print_step("Removing template-only files...")
    # 주의: PROJECTOPS-SETUP-GUIDE.md는 보존한다.
    for rel, label in CLEANUP_TARGETS:
        p = Path(rel)
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
            print(f"  ✓ {label}", file=sys.stderr)
        elif p.is_file():
            p.unlink(missing_ok=True)
            print(f"  ✓ {label}", file=sys.stderr)
    print_success("Template-only files removed")


def ensure_gitignore():
    print_step("Checking and updating .gitignore...")
    required = ["/.idea", "/.claude/settings.local.json"]
    gi = Path(".gitignore")
    if not gi.is_file():
        print_info("No .gitignore found. Creating it.")
        gi.write_text("# IDE Settings\n/.idea\n\n# Claude AI Settings\n/.claude/settings.local.json\n", encoding="utf-8", newline="\n")
        print_success(".gitignore created")
        return

    print_info("Existing .gitignore found. Checking required entries...")
    existing = gi.read_text(encoding="utf-8")
    lines = set(existing.split("\n"))
    to_add = [e for e in required if e not in lines and e.lstrip("/") not in lines]
    if not to_add:
        print_info("All required entries already exist. Skipping.")
        return

    print_info(f"Adding {len(to_add)} entries...")
    suffix = ""
    if existing and not existing.endswith("\n"):
        suffix += "\n"
    suffix += "\n# ====================================================================\n"
    suffix += "# projectops: Auto-added entries\n"
    suffix += "# ====================================================================\n"
    for e in to_add:
        suffix += e + "\n"
        print_info(f"  ✓ {e}")
    gi.write_text(existing + suffix, encoding="utf-8", newline="\n")
    print_success(f".gitignore updated ({len(to_add)} entries added)")


def initialize_readme(project_name, version):
    print_step("Initializing README.md...")
    # KST(=UTC+9) 타임스탬프 — tzdata 의존 없이 고정 오프셋
    from datetime import timedelta
    kst = datetime.now(timezone.utc) + timedelta(hours=9)
    stamp = kst.strftime("%Y-%m-%d %H:%M:%S KST")
    content = f"""# {project_name}

<!-- AUTO-VERSION-SECTION: DO NOT EDIT MANUALLY -->
## 최신 버전 : v{version}

[전체 버전 기록 보기](CHANGELOG.md)

</br>

<!-- Template initialized: {stamp} -->
"""
    Path("README.md").write_text(content, encoding="utf-8", newline="\n")
    print_success("README.md initialized.")


def update_issue_templates(repo_owner):
    print_step("Updating issue template assignees...")
    templates = ["bug_report.md", "design_request.md", "feature_request.md", "qa_request.md"]
    updated = 0
    for t in templates:
        f = Path(".github/ISSUE_TEMPLATE") / t
        if not f.is_file():
            continue
        text = f.read_text(encoding="utf-8")
        new = text.replace("assignees: [Cassiiopeia]", f"assignees: [{repo_owner}]")
        if new != text:
            f.write_text(new, encoding="utf-8", newline="\n")
        print(f"  ✓ {t}", file=sys.stderr)
        updated += 1
    if updated == 0:
        print_warning("No issue templates to update.")
    else:
        print_success(f"Updated {updated} issue template(s)")


def main():
    parser = argparse.ArgumentParser(description="Initialize the GitHub template")
    parser.add_argument("-v", "--version", default="0.0.0")
    parser.add_argument("-t", "--type", default="basic", dest="ptype")
    args = parser.parse_args()

    version = args.version
    ptype = args.ptype
    github_user = os.environ.get("GITHUB_ACTOR") or os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"
    github_repo = os.environ.get("GITHUB_REPOSITORY", "")
    repo_owner = github_repo.split("/")[0] if "/" in github_repo else github_user
    template_version = get_template_version()

    print("", file=sys.stderr)
    print("GitHub template initializer", file=sys.stderr)
    print("", file=sys.stderr)

    validate_version(version)
    validate_project_type(ptype)

    if github_repo:
        project_name = github_repo.split("/", 1)[1]
    else:
        toplevel = run(["git", "rev-parse", "--show-toplevel"])
        project_name = Path(toplevel or os.getcwd()).name

    print(f"Project name: {project_name}", file=sys.stderr)
    print(f"Version: {version}", file=sys.stderr)
    print(f"Type: {ptype}", file=sys.stderr)

    detected_branch = detect_default_branch()

    create_version_yml(version, ptype, detected_branch, github_user, template_version)
    update_workflow_triggers(detected_branch)
    cleanup_template_files()
    ensure_gitignore()
    initialize_readme(project_name, version)
    update_issue_templates(repo_owner)

    print("", file=sys.stderr)
    print("\U0001f389 Template initialized!", file=sys.stderr)
    print(f"  Version: {version} / Type: {ptype} / Branch: {detected_branch}", file=sys.stderr)
    print("  Next: edit README.md → git commit → git push", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    sys.exit(main())
