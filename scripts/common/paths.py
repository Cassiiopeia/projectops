"""Compute output md file paths."""

import os
import re
from pathlib import Path
from typing import Optional, Union


def get_next_seq(skill_dir: Path, today: str, strict: bool = False,
                 title: Optional[str] = None) -> str:
    """
    Return the count of files in skill_dir starting with today's date (today) + 1, as 3 digits.
    With title, reuse today's number for an output (file or folder) with the same title (no new folder on every call, #971).

    With strict=True, raise FileNotFoundError when skill_dir does not exist.
    Used when the CLI layer explicitly rejects an invalid skill_id.
    """
    if not skill_dir.exists():
        if strict:
            raise FileNotFoundError(f"skill_dir does not exist: {skill_dir}")
        return "001"
    today_names = [f.name for f in skill_dir.iterdir() if f.name.startswith(today)]
    reused = _find_same_title_seq(today_names, today, title) if title else None
    return reused or f"{len(today_names) + 1:03d}"


def _find_same_title_seq(today_names: list, today: str, title: str) -> Optional[str]:
    """Today's output with the same title > its serial number (`{date}_{NNN}_{title}` folder or `.md`)

    Only reuse within the serial range (up to today's entry count); docs renamed to a real issue number after filing (`_245_`) are not overwritten.
    """
    pattern = re.compile(rf"^{today}_(\d{{3}})_{re.escape(title)}(?:\.md)?$")
    for name in sorted(today_names):
        matched = pattern.match(name)
        if matched and int(matched.group(1)) <= len(today_names):
            return matched.group(1)
    return None


def _drop_repeated_issue_number(title: str, issue_number: Optional[str]) -> str:
    """Strip a leading duplicate issue number from the title: `574_title`·`20261021_574_title` + 574 > `title` (prevents path `574_574_`)"""
    if not issue_number:
        return title
    stripped = re.sub(rf"^(?:\d{{8}}_)?{re.escape(issue_number)}_", "", title)
    return stripped or title


def build_output_path(
    base_dir: Union[str, Path],
    skill_id: str,
    today: str,
    number: str,
    title: str,
) -> Path:
    """Return the final output path."""
    return Path(base_dir) / skill_id / f"{today}_{number}_{title}.md"


# ===================================================================
# Output path resolution (#525): single Layer 1 implementation
# ===================================================================
# Several CLIs (report, review, etc.) used to each carry a copy of this logic,
# and the other output skills had no way to compute it at all ("the agent computes it"). With the rule not
# enforced in code, nobody could notice when file names diverged between skills.
# This function is the only implementation; every skill CLI calls it.

DEFAULT_OUTPUT_ROOT = "docs/projectops"


def resolve_output_root(project_root: Union[str, Path]) -> Path:
    """Decide the output root. Without a setting, keep the existing location.

    `output.root` in the settings (config.json) lets each team use a different location.
    - Relative path: from the repository root (e.g. "docs/dev" → <repo>/docs/dev)
    - Absolute path: used as is (to collect outside the repository)
    - Unset: docs/projectops, i.e. behavior does not change unless the setting is touched
    """
    return _join_output_root(project_root, read_configured_output_root()[0])


def read_configured_output_root() -> tuple[str, Optional[str]]:
    """config.json output.root > (value, warning). For an unusable setting, an empty value (default location) + what is wrong"""
    from common.config import config_path, load_with_status
    try:
        data, status = load_with_status()
        location = config_path()
    except OSError as error:   # e.g. failed copy while migrating from the old path
        return "", f"could not open config.json; ignoring output.root and using the default location ({DEFAULT_OUTPUT_ROOT}): {error}"
    if status == "unreadable":
        return "", (f"config.json is broken (JSON syntax or encoding); ignoring output.root and "
                    f"using the default location ({DEFAULT_OUTPUT_ROOT}): {location}")
    if not isinstance(data, dict):
        return "", None
    output = data.get("output")
    if output is None:
        return "", None
    configured = output.get("root") if isinstance(output, dict) else None
    if not isinstance(output, dict) or not isinstance(configured, (str, type(None))):
        return "", f"output.root in config.json is not a string; using the default location ({DEFAULT_OUTPUT_ROOT})"
    return (configured or "").strip(), None


def _join_output_root(project_root: Union[str, Path], configured: str) -> Path:
    """Setting value > output root (empty means default, relative means from the repository)"""
    root = Path(project_root)
    if not configured:
        return root / DEFAULT_OUTPUT_ROOT
    p = Path(configured).expanduser()
    return p if p.is_absolute() else root / p


# ===================================================================
# Untracked outputs (#621): evidence must not pile up in the repository
# ===================================================================
# Skill outputs come in two kinds. Mixing them makes one side wrong.
#
#   Docs     — read by people and referenced from issues. **Must be tracked.**
#           Reports, plans, analyses, reviews, issues, test cases …
#   Evidence — screenshots, screen dumps, renders, diff images. Regenerated and heavy.
#           **Must not be tracked.** Measured: one repo's agent-test was 9.3MB.
#
# Each folder carries its own ignore rule (same approach as #561); touching the repo root
# .gitignore conflicts with rules from other sessions and tools.
#
# **When you add a new output skill, put it in the set below.** If missed, evidence
# starts getting committed silently, and by the time anyone notices it is already in history.
EVIDENCE_SKILLS = frozenset({
    "agent-test",     # screenshots · device logs
    # Dumps, mockup exports, app renders, diff images. Renamed figma-verify → figma in #854.
    # Old figma-verify/ folders are left alone: evidence is rebuilt every round so nothing re-reads it,
    # and it carries its own .gitignore so it is never committed. Hence no read fallback.
    "figma",
    "launch",         # app·web captures · http responses (#629)
    "ui-design",   # request boards · per-state captures (#634)
})

# Removed skills (note·analyze·plan·implement·design-analyze·refactor-analyze·ppt·troubleshoot·pr) were dropped (#822).
# If kept, output folders would still be created under nonexistent skill names.
DOCUMENT_SKILLS = frozenset({
    "issue", "oss-consult", "presentation", "report", "review", "testcase",
})


def gitignore_body(skill_id: str) -> str:
    return (f"# {skill_id} 증거물은 추적하지 않는다 (#621)\n"
            "# 이 폴더는 재생성되는 산출물만 담는다 — 저장소에 쌓이면 안 된다.\n"
            "*\n!.gitignore\n")


def ensure_untracked(dir_path: Union[str, Path], skill_id: str) -> str:
    """Make the folder carry its own untracked rule.

    Returns: created (newly written) / already (ours already there) / kept (someone else's preserved)
    **Never overwrite a .gitignore written by someone else.**
    """
    d = Path(dir_path)
    d.mkdir(parents=True, exist_ok=True)
    f = d / ".gitignore"
    body = gitignore_body(skill_id)
    if f.exists():
        if f.is_file() and f.read_text(encoding="utf-8") == body:
            return "already"
        return "kept"
    f.write_text(body, encoding="utf-8")
    return "created"


def add_root_and_issue_args(parser, with_issue: bool = True) -> None:
    """Shared get-output-path args: --root (project), --issue (explicit issue number) (#943)"""
    parser.add_argument("--root", default=None,
                        help="project root (default: $PROJECT_ROOT, then the git root of the current folder)")
    if with_issue:
        parser.add_argument("--issue", type=int, default=None,
                            help="issue number to use (default: found from the worktree path, then the branch name)")


def _project_dir(root: Optional[str]) -> Optional[str]:
    """Project folder: --root > $PROJECT_ROOT > None (= current folder). ValueError instead of None for a missing folder"""
    chosen = root or os.environ.get("PROJECT_ROOT") or None
    if chosen and not os.path.isdir(chosen):
        raise ValueError(chosen)
    return chosen


def resolve_output_path(skill_id: str, forced_title: Optional[str] = None,
                        use_issue_number: bool = True,
                        root: Optional[str] = None, issue: Optional[int] = None) -> dict:
    """Compute the output md path and return it as a dict (the CLI emits it as is).

    The issue number is looked up from the worktree path → branch name; if neither has one,
    the day's serial number is used. The title comes from the argument first, else from the path.

    root: project root. Defaults to $PROJECT_ROOT, then the current folder (correct even after the shell folder changes, #943).
    issue: explicit issue number (wins over values found from worktree or branch).

    use_issue_number=False skips branch/worktree numbers and uses only the serial number.
    If an output **that has no number yet**, like a new issue doc, borrowed the current branch's issue number,
    its name would collide with another issue's file (#822).
    """
    import subprocess
    from datetime import date

    # Only registered skills are accepted. Blocks values like `../../escape` from leaving the output root (#713)
    if skill_id not in EVIDENCE_SKILLS and skill_id not in DOCUMENT_SKILLS:
        return {
            "ok": False,
            "code": "unknown_skill_id",
            "error": f"unregistered skill_id: {skill_id!r}",
            "known": sorted(EVIDENCE_SKILLS | DOCUMENT_SKILLS),
            "hint": "for a new output skill, register it in EVIDENCE_SKILLS/DOCUMENT_SKILLS in scripts/common/paths.py",
        }

    from common.issue_number import (
        extract_from_path as in_extract_from_path,
        extract_from_branch, get_current_branch, resolve,
    )
    from common.gh_branch import strip_issue_decorations
    from common.title import normalize, extract_from_path as title_extract_from_path

    try:
        project_dir = _project_dir(root)
    except ValueError as bad:
        return {"ok": False, "code": "root_not_found", "error": f"project folder not found: {bad}",
                "next": "pass a real project path to --root"}
    cwd = project_dir or os.getcwd()
    today = date.today().strftime("%Y%m%d")

    wt_number = in_extract_from_path(cwd)
    branch = get_current_branch(project_dir)
    br_number = extract_from_branch(branch) if branch else None
    issue_num, mismatch = resolve(wt_number, br_number)
    if issue is not None:
        issue_num, mismatch = str(issue), False
    if not use_issue_number:
        issue_num, mismatch = None, False

    try:
        root_str = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=project_dir, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {"ok": False, "code": "git_not_found", "error": "not a git repository",
                "next": "run it from the project folder or pass --root <project path> ($PROJECT_ROOT also works)"}

    configured_root, config_warning = read_configured_output_root()
    output_base = _join_output_root(root_str, configured_root)
    skill_dir = output_base / skill_id
    # Clean the title (strip emoji and [tags] > normalize file name > strip leading duplicate issue number)
    if forced_title:
        final_title = normalize(strip_issue_decorations(forced_title))
    else:
        raw = title_extract_from_path(cwd)
        final_title = normalize(raw) if raw else "untitled"
    final_title = _drop_repeated_issue_number(final_title, issue_num)

    # Number: issue number > reuse today's serial for the same title (evidence only) > new serial
    # Docs (issue, report, etc.) always get a new number; reuse would overwrite the earlier doc with the same title
    reuse_title = final_title if skill_id in EVIDENCE_SKILLS else None
    number = issue_num if issue_num else get_next_seq(skill_dir, today, title=reuse_title)

    path = build_output_path(output_base, skill_id, today, number, final_title)
    out = {
        "path": str(path),
        "summary": str(path),
        "mismatch": mismatch,
        "output_root": str(output_base),
    }
    if config_warning:
        out["config_warning"] = config_warning
    # For evidence-producing skills, plant the ignore rule while creating the folder.
    # Left to each skill, some skill will always forget.
    if skill_id in EVIDENCE_SKILLS:
        out["gitignore"] = ensure_untracked(skill_dir, skill_id)
    return out
