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
        print_error(f"잘못된 버전 형식: {v}")
        print_error("올바른 형식: x.y.z (예: 1.0.0, 2.1.3)")
        sys.exit(1)


def validate_project_type(t: str):
    if t not in VALID_TYPES:
        print_error(f"지원하지 않는 프로젝트 타입: {t}")
        print_error(f"지원 타입: {' '.join(VALID_TYPES)}")
        sys.exit(1)


def detect_default_branch() -> str:
    print_step("Default branch 자동 감지 중...")
    if shutil.which("gh"):
        d = run(["gh", "repo", "view", "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name"])
        if d:
            print_info(f"gh CLI로 감지: {d}")
            return d
    d = run(["git", "symbolic-ref", "refs/remotes/origin/HEAD"])
    if d:
        d = d.replace("refs/remotes/origin/", "")
        print_info(f"git symbolic-ref로 감지: {d}")
        return d
    show = run(["git", "remote", "show", "origin"])
    for line in show.split("\n"):
        if "HEAD branch" in line:
            d = line.split(":")[-1].strip()
            if d:
                print_info(f"git remote show로 감지: {d}")
                return d
    print_warning("자동 감지 실패, 기본값 사용: main")
    return "main"


def create_version_yml(version, ptype, branch, user, template_version):
    print_step("version.yml 파일 생성 중...")
    print_info(f"버전: {version}")
    print_info(f"타입: {ptype}")
    print_info(f"브랜치: {branch}")
    print_info(f"사용자: {user}")

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
# - patch: 자동으로 세 번째 자리 증가 (x.x.x -> x.x.x+1)
# - version_code: 매 빌드마다 자동으로 1씩 증가
# - minor/major: 수동으로 직접 수정 필요
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
"""
    Path("version.yml").write_text(content, encoding="utf-8", newline="\n")
    print_success("version.yml 파일이 생성되었습니다.")


def update_workflow_triggers(branch):
    if branch == "main":
        print_info("브랜치가 main이므로 워크플로우 변경 불필요")
        print_info("모든 워크플로우는 기본적으로 main 브랜치를 트리거로 사용합니다")
        return

    print_step(f"워크플로우 트리거 브랜치 변경 중: main → {branch}")
    main_branch_workflows = ["PROJECT-VERSION-CONTROL.yaml"]
    updated = 0
    for wf in main_branch_workflows:
        f = Path(".github/workflows") / wf
        if not f.is_file():
            print_warning(f"{wf} 파일이 존재하지 않습니다")
            continue
        text = f.read_text(encoding="utf-8")
        if 'branches: ["main"]' in text:
            f.write_text(text.replace('branches: ["main"]', f'branches: ["{branch}"]'), encoding="utf-8", newline="\n")
        elif "branches: ['main']" in text:
            f.write_text(text.replace("branches: ['main']", f"branches: ['{branch}']"), encoding="utf-8", newline="\n")
        else:
            print_warning(f"{wf} 파일에서 main 브랜치 트리거를 찾을 수 없습니다")
            continue
        print(f"  ✓ {wf}", file=sys.stderr)
        updated += 1
    if updated > 0:
        print_success(f"{updated} 개 워크플로우 파일 업데이트 완료")
    else:
        print_warning("업데이트할 워크플로우 파일이 없습니다")


# 삭제 대상 — (경로, 사람이 읽는 라벨). 파일/폴더 자동 판별.
# ⚠️ 루트에 마켓플레이스/템플릿 전용 파일을 추가하면 여기에도 등록해야 한다 (CLAUDE.md 규칙).
CLEANUP_TARGETS = [
    ("CHANGELOG.md", "CHANGELOG.md 삭제"),
    ("CHANGELOG.json", "CHANGELOG.json 삭제"),
    ("template_integrator.sh", "template_integrator.sh 삭제 (원격 실행 전용)"),
    ("template_integrator.ps1", "template_integrator.ps1 삭제 (원격 실행 전용)"),
    ("LICENSE", "LICENSE 삭제"),
    ("CONTRIBUTING.md", "CONTRIBUTING.md 삭제"),
    ("CLAUDE.md", "CLAUDE.md 삭제"),
    ("AGENTS.md", "AGENTS.md 삭제"),
    ("GEMINI.md", "GEMINI.md 삭제"),
    ("gemini-extension.json", "gemini-extension.json 삭제"),
    (".github/scripts/test", ".github/scripts/test 폴더 삭제"),
    (".github/workflows/test", ".github/workflows/test 폴더 삭제"),
    (".github/workflows/PROJECT-TEMPLATE-PLUGIN-VERSION-SYNC.yaml", "PROJECT-TEMPLATE-PLUGIN-VERSION-SYNC.yaml 삭제 (마켓플레이스 전용)"),
    (".github/workflows/PROJECT-TEMPLATE-NPM-PUBLISH.yaml", "PROJECT-TEMPLATE-NPM-PUBLISH.yaml 삭제 (마켓플레이스 전용)"),
    (".github/workflows/PROJECT-TEMPLATE-CI.yaml", "PROJECT-TEMPLATE-CI.yaml 삭제 (마켓플레이스 전용)"),
    ("docs", "docs 폴더 삭제"),
    (".claude-plugin", ".claude-plugin 폴더 삭제 (플러그인 매니페스트)"),
    (".codex-plugin", ".codex-plugin 폴더 삭제 (플러그인 매니페스트)"),
    (".agents", ".agents 폴더 삭제 (Codex 마켓플레이스 메타데이터)"),
    (".cursor", ".cursor 폴더 삭제 (IDE 스킬 복사본)"),
    ("skills", "skills 폴더 삭제 (마켓플레이스 전용 스킬)"),
    ("scripts", "scripts 폴더 삭제 (마켓플레이스 전용 스크립트)"),
    ("package.json", "package.json 삭제 (pi 패키지 매니페스트)"),
    ("bin", "bin 폴더 삭제 (projectops CLI)"),
    ("src", "src 폴더 삭제 (projectops CLI)"),
    ("harness", "harness 폴더 삭제 (pi Persona Harness)"),
    (".suh-template.example", ".suh-template.example 폴더 삭제 (템플릿 전용)"),
    # 릴리스마다 changelog-deploy가 재생성하는 템플릿 레포 전용 산출물
    ("pr_body.md", "pr_body.md 삭제 (템플릿 레포 릴리스 작업 산출물)"),
]


def cleanup_template_files():
    print_step("템플릿 관련 파일 삭제 중...")
    # 주의: PROJECTOPS-SETUP-GUIDE.md는 보존한다.
    for rel, label in CLEANUP_TARGETS:
        p = Path(rel)
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
            print(f"  ✓ {label}", file=sys.stderr)
        elif p.is_file():
            p.unlink(missing_ok=True)
            print(f"  ✓ {label}", file=sys.stderr)
    print_success("템플릿 관련 파일 삭제 완료")


def ensure_gitignore():
    print_step(".gitignore 파일 확인 및 업데이트 중...")
    required = ["/.idea", "/.claude/settings.local.json"]
    gi = Path(".gitignore")
    if not gi.is_file():
        print_info(".gitignore 파일이 없습니다. 생성합니다.")
        gi.write_text("# IDE Settings\n/.idea\n\n# Claude AI Settings\n/.claude/settings.local.json\n", encoding="utf-8", newline="\n")
        print_success(".gitignore 파일 생성 완료")
        return

    print_info("기존 .gitignore 파일 발견. 필수 항목 확인 중...")
    existing = gi.read_text(encoding="utf-8")
    lines = set(existing.split("\n"))
    to_add = [e for e in required if e not in lines and e.lstrip("/") not in lines]
    if not to_add:
        print_info("필수 항목이 이미 모두 존재합니다. 건너뜁니다.")
        return

    print_info(f"{len(to_add)} 개 항목 추가 중...")
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
    print_success(f".gitignore 업데이트 완료 ({len(to_add)} 개 항목 추가)")


def initialize_readme(project_name, version):
    print_step("README.md 파일 초기화 중...")
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
    print_success("README.md 파일이 초기화되었습니다.")


def update_issue_templates(repo_owner):
    print_step("이슈 템플릿 assignee 업데이트 중...")
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
        print_warning("업데이트할 이슈 템플릿이 없습니다.")
    else:
        print_success(f"이슈 템플릿 {updated} 개 업데이트 완료")


def main():
    parser = argparse.ArgumentParser(description="GitHub 템플릿 초기화")
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
    print("GitHub 템플릿 초기화 스크립트", file=sys.stderr)
    print("", file=sys.stderr)

    validate_version(version)
    validate_project_type(ptype)

    if github_repo:
        project_name = github_repo.split("/", 1)[1]
    else:
        toplevel = run(["git", "rev-parse", "--show-toplevel"])
        project_name = Path(toplevel or os.getcwd()).name

    print(f"프로젝트명: {project_name}", file=sys.stderr)
    print(f"설정된 버전: {version}", file=sys.stderr)
    print(f"설정된 타입: {ptype}", file=sys.stderr)

    detected_branch = detect_default_branch()

    create_version_yml(version, ptype, detected_branch, github_user, template_version)
    update_workflow_triggers(detected_branch)
    cleanup_template_files()
    ensure_gitignore()
    initialize_readme(project_name, version)
    update_issue_templates(repo_owner)

    print("", file=sys.stderr)
    print("\U0001f389 템플릿 초기화 완료!", file=sys.stderr)
    print(f"  버전: {version} / 타입: {ptype} / 브랜치: {detected_branch}", file=sys.stderr)
    print("  다음: README.md 수정 → git commit → git push", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    sys.exit(main())
