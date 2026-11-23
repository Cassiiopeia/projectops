#!/usr/bin/env python3
# ===================================================================
# template_initializer.py — GitHub template initialization (Python port of the .sh, #448)
# ===================================================================
#
# Runs when a new project is created with GitHub "Use this template" and sets the project
# to its initial state. Cross-platform (Windows/macOS/Linux), standard library only.
# The old template_initializer.sh is a shim that delegates here.
#
# Usage:
#   python template_initializer.py [-v VERSION] [-t TYPE]
#     -v/--version : initial version (default 0.0.0)
#     -t/--type    : project type (default basic)
# ===================================================================

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from version_manager import load_project_types  # noqa: E402  registry reader shared with version_manager (#1244)

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def print_step(msg): print(f"▶ {msg}", file=sys.stderr)
def print_info(msg): print(f"  → {msg}", file=sys.stderr)
def print_success(msg): print(f"✓ {msg}", file=sys.stderr)
def print_warning(msg): print(f"⚠ {msg}", file=sys.stderr)
def print_error(msg): print(f"✗ {msg}", file=sys.stderr)


def run(cmd):
    """Run a git/gh command — returns an empty string on failure (protects the deploy pipeline)."""
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
    valid_types = [entry["id"] for entry in load_project_types()]
    if t not in valid_types:
        print_error(f"Unsupported project type: {t}")
        print_error(f"Supported types: {' '.join(valid_types)}")
        sys.exit(1)


def type_sync_comment_lines() -> str:
    """version.yml "Files synced per project type" lines from the registry (same text as the installer)"""
    return "\n".join(f"# - {entry['id']}: {entry['version']['comment']}" for entry in load_project_types())


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
    type_sync_lines = type_sync_comment_lines()
    content = f"""# ===================================================================
# Project version management file
# ===================================================================
#
# This file centrally manages version info across project types
# GitHub Actions workflows read this file to manage versions automatically
#
# Usage:
# 1. version: "1.0.0" - the version shown to users
# 2. version_code: 1 - Play Store/App Store build number (auto-increments from 1)
# 3. project_types: array of project types — the first item is primary
#
# Automatic version updates:
# - version_code: increases by 1 on every build (independent of the rule below)
# - metadata.template.options.semver_auto decides the bump size
#   semver_auto: true  -> decided from commit subjects in the release range
#                         "title : feat! : text" or "feat!:" -> major (x+1.0.0)
#                         "title : feat : text"  or "feat:"  -> minor (x.y+1.0)
#                         anything else (fix/docs/chore/refactor/test) -> patch (x.y.z+1)
#   key missing / false -> always patch +1
# - You may also edit the version value directly, regardless of the rule above
#
# Files synced per project type:
{type_sync_lines}
#
# Notes:
# - Do not change project_types after the initial setup
# - Versions always sync automatically to the higher version
# ===================================================================

version: "{version}"
version_code: 1  # app build number
project_types: ["{ptype}"]   # multi-type array — first item is primary, editable by hand
metadata:
  last_updated: "{now}"
  last_updated_by: "{user}"
  default_branch: "{branch}"
  template:
    source: "projectops"
    version: "{template_version}"
    initialized_date: "{today}"
    options:
      # semver auto bump (#546) — major/minor/patch decided from commit subjects in the release range.
      # Same default as a fresh integration with npx projectops (so it does not differ by creation path).
      semver_auto: true
      # Issue/PR template language and status label style (#769, #776) — this repo was created from the English source.
      # If the keys are left empty, npx projectops treats it as an "existing integrated repo" and reverts to Korean.
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


# Deletion targets — (path, human-readable label). File/folder detected automatically.
# ⚠️ When adding a marketplace/template-only file at the root, register it here too (docs/architecture/agent/scripts.md rule).
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
    (".github/ISSUE_TEMPLATE/projectops-skill-bug.yml", "Remove projectops agent skill bug form (this repository only)"),
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
    (".github/workflows/PROJECT-TEMPLATE-ISSUE-ASSIGNMENT.yaml", "Remove PROJECT-TEMPLATE-ISSUE-ASSIGNMENT.yaml (this repository only)"),
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
    ("knowledge", "Remove knowledge folder (this repository's pro-brain notes)"),
    (".suh-template.example", "Remove .suh-template.example folder (template only)"),
    # Template-repo-only artifacts regenerated by changelog-deploy on every release
    ("pr_body.md", "Remove pr_body.md (template repo release artifact)"),
]


def cleanup_template_files():
    print_step("Removing template-only files...")
    # Note: PROJECTOPS-SETUP-GUIDE.md is kept.
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
    # KST (=UTC+9) timestamp — fixed offset without tzdata
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
