"""Resolve the commit message format.

Within one repo the format must not differ per person, so the team format (version.yml) wins; the tone is personal.
The old pro-commit hardcoded the format and ignored commit_template in version.yml — so when a team changed
the format, issue helper comments and skill output disagreed. This module reads the same source for both.
"""
from __future__ import annotations

import re
from pathlib import Path

from common.gh_branch import strip_issue_decorations

PRESETS = {
    # The most widely used neutral format. render drops the URL line when there is no issue.
    "conventional": "{type}({scope}): {description}\n\n{issue_url}",
    # Same format as the issue helper workflow default (team default for repos with projectops installed)
    "projectops": "{issue_title} : {type} : {description} {issue_url}",
    "gitmoji": "{emoji} {type}({scope}): {description}\n\n{issue_url}",
}
_EMOJI = {"feat": "✨", "fix": "🐛", "docs": "📝", "refactor": "♻️", "test": "✅", "chore": "🔧", "design": "💄"}

# Unify issue helper (${...}) and Korean/English description placeholders under the new names
_LEGACY = [
    ("${issueTitle}", "{issue_title}"), ("${commitType}", "{type}"), ("${issueUrl}", "{issue_url}"),
    ("${issueNumber}", "{issue_number}"), ("${branchName}", "{branch_name}"), ("${date}", "{date}"),
    ("${labels}", "{labels}"), ("${assignees}", "{assignees}"), ("{변경 사항에 대한 설명}", "{description}"),
    ("{description of the change}", "{description}"), ("{설명}", "{description}"),
]


def normalize_placeholders(template: str) -> str:
    for old, new in _LEGACY:
        template = template.replace(old, new)
    return template


def _strip_comment(raw: str) -> str:
    # A # inside quotes is part of the value. Same rule as issue_helper._strip_comment.
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        end = raw.find(raw[0], 1)
        if end != -1:
            return raw[: end + 1]
    return re.sub(r"\s+#.*$", "", raw)


def _unquote(v: str) -> str:
    v = v.strip()
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"" else v


def read_team_config(repo_root: str) -> dict:
    """Read the team commit settings from version.yml.

    The issue_helper section is parsed with the same rules as load_config in `.github/scripts/issue_helper.py`
    (first `issue_helper:` block only, stop at its end, commit_type_map is one flat map). It ships on a different path
    and cannot be imported, so it is duplicated; the render parity test in test_commit_style keeps them in sync.
    """
    out = {"template": None, "installed": False, "semver_auto": False, "commit_type_map": {}}
    path = Path(repo_root) / "version.yml"
    if not path.exists():
        return out
    try:
        # Read files with a BOM too (Windows editors)
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError):
        return out
    section_indent = None
    section_done = False
    in_type_map, type_map_indent = False, 0
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        # Only top-level keys count as installation. A nested key with the same name is no proof of a projectops install.
        if indent == 0 and re.match(r"^(issue_helper|metadata):", s):
            out["installed"] = True
        if re.match(r"^semver_auto:\s*true\b", s, re.IGNORECASE):
            out["semver_auto"] = True
        if section_done:
            continue
        if section_indent is None:
            if re.match(r"^issue_helper:\s*(#.*)?$", s):
                section_indent = indent
            continue
        if indent <= section_indent:  # section ended — ignore later sections with the same name, like issue_helper
            section_done = True
            continue
        m = re.match(r"""^["']?([^"':]+)["']?\s*:\s*(.*?)\s*$""", s)
        if not m:
            continue
        key, raw = m.group(1).strip(), _strip_comment(m.group(2))
        if in_type_map and indent > type_map_indent:
            out["commit_type_map"][key] = _unquote(raw)
            continue
        in_type_map = False
        if key == "commit_type_map":
            in_type_map, type_map_indent = True, indent
        elif key == "commit_template":
            out["template"] = _unquote(raw)
    return out


def read_team_template(repo_root: str) -> tuple:
    """(commit_template or None, projectops installed, semver_auto). Backward compatibility — see read_team_config."""
    cfg = read_team_config(repo_root)
    return cfg["template"], cfg["installed"], cfg["semver_auto"]


def resolve_style(prefs_values: dict, repo_root: str, *, legacy_user: bool = False) -> dict:
    """Pick the format: team template > installed-repo default > personal template/preset > (projectops for existing users) > conventional.

    legacy_user — someone who has used pro-commit for a while (approval setting remains). If they never chose a format,
    keep the projectops format they have been using instead of the new default, so it never changes overnight (spec S1).
    """
    warnings = []
    team_cfg = read_team_config(repo_root)
    team, installed, semver = team_cfg["template"], team_cfg["installed"], team_cfg["semver_auto"]
    preset = prefs_values.get("preset") or "conventional"
    if preset not in PRESETS and preset != "custom":
        warnings.append(f"unknown preset '{preset}'; using conventional")
        preset = "conventional"

    if team:
        template, source = normalize_placeholders(team), "version.yml"
    elif installed:
        template, source, preset = PRESETS["projectops"], "team-default", "projectops"
    elif prefs_values.get("template"):
        template, source, preset = normalize_placeholders(prefs_values["template"]), "preferences", "custom"
    elif preset == "custom":
        warnings.append("preset is custom but no template is set; using conventional")
        template, source, preset = PRESETS["conventional"], "default", "conventional"
    elif not prefs_values.get("preset") and legacy_user:
        template, source, preset = PRESETS["projectops"], "legacy-default", "projectops"
    else:
        template = PRESETS[preset]
        source = "preferences" if prefs_values.get("preset") else "default"

    if semver and "{type}" not in template:
        warnings.append("semver_auto is on in this repo but the format has no {type}; every release will be judged a patch")
    return {"template": template, "source": source, "preset": preset, "warnings": warnings,
            "commit_type_map": team_cfg["commit_type_map"]}


# Known placeholders plus ${...} that the issue helper does not know either. The latter have no value, so treat them
# as empty instead of baking them into the commit literally. One regex in one pass keeps "${x}" text in titles untouched.
_PLACEHOLDER = re.compile(
    r"\{(issue_title|type|scope|issue_url|issue_number|emoji|branch_name|date|labels|assignees)\}"
    r"|\$\{[A-Za-z_]\w*\}")
_EMPTY = "\x00"  # marker for an empty value. Kept briefly so surrounding separators can be removed with it


def _drop_empty(line: str) -> str:
    """Remove '()', '[]', '#', leading separators (' : ' etc.) and double spaces left by empty values."""
    if _EMPTY not in line:
        return line
    # A line holding only one label and an empty value, like "Refs: {issue_url}", goes with its label (lines with other content are left alone)
    if re.fullmatch(r"\s*\w[\w-]*\s*:\s*\x00\s*", line):
        return ""
    # Strip '#' and '@' first so "(#{issue_number})" becomes "(\x00)" and hits the bracket rule
    line = re.sub(r"[#@]\x00", _EMPTY, line)
    line = re.sub(r"[(\[]\x00[)\]]", _EMPTY, line)
    line = re.sub(r"\s*[:|,]\s*\x00", _EMPTY, line)       # with the leading separator
    line = re.sub(r"^\s*\x00\s*[:|,]?\s*", "", line)     # at line start, with the trailing separator
    line = line.replace(_EMPTY, "")
    return re.sub(r" {2,}", " ", line)


def render(template: str, *, issue_title: str, issue_url: str, commit_type: str, scope: str = "",
           branch_name: str = "", date: str = "", labels: str = "", assignees: str = "") -> str:
    """Fill everything except {description}. Removes '()', empty URL lines and leading separators left by empty values.

    branch_name, date, labels and assignees are the same placeholders as the issue helper (${branchName} etc.).
    Unknown ones stay empty, and their spot disappears together with the surrounding separators.
    """
    out = normalize_placeholders(template)
    num = re.search(r"/issues/(\d+)", issue_url or "")
    values = {
        "issue_title": strip_issue_decorations(issue_title) if issue_title else "",
        "type": commit_type, "scope": scope, "issue_url": issue_url or "",
        "issue_number": num.group(1) if num else "", "emoji": _EMOJI.get(commit_type, "🔧"),
        "branch_name": branch_name, "date": date, "labels": labels, "assignees": assignees,
    }
    # Replace in one pass. Sequential replace would re-match text like "{type}" inside the title in a later step.
    out = _PLACEHOLDER.sub(lambda m: (values[m.group(1)] if m.group(1) else "") or _EMPTY, out)
    lines = [_drop_empty(ln).rstrip() for ln in out.split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines).strip()


def render_for_issue(style: dict, *, issue_title: str, issue_url: str, commit_type: str | None = None,
                     scope: str = "", **extra) -> str:
    """Render with the resolved style. Without a type, derive it from the title tag, including the team commit_type_map.

    Both CLIs (commit and GitHub) must use this one function to get the same type as issue helper comments.
    """
    from common.gh_branch import infer_commit_type
    ctype = commit_type or infer_commit_type(issue_title, style.get("commit_type_map") or None)
    return render(style["template"], issue_title=issue_title, issue_url=issue_url, commit_type=ctype,
                  scope=scope, **extra)


def resolve_for_repo(repo_root: str | None = None) -> tuple:
    """Resolve the repo's commit format (team > personal). Single path so pro-commit and the issue helper CLI see the same result."""
    from common import config
    from common.preferences import detect_repo, is_legacy_commit_user, resolve
    root = repo_root or _toplevel()
    owner, repo = detect_repo(root)
    data, status = config.load_with_status()
    prefs = resolve("pro-commit", owner, repo, data if status == "ok" else None)
    style = resolve_style(prefs["values"], root, legacy_user=is_legacy_commit_user(data))
    if status == "unreadable":
        prefs["config_status"] = status
        style["warnings"].append("could not read config.json; using defaults without personal settings")
    return prefs, style


def _toplevel() -> str:
    """Root of the git repo containing cwd. Finds the root version.yml (team format) even when called from a subfolder."""
    import os
    import subprocess
    cwd = os.getcwd()
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
    except (OSError, subprocess.SubprocessError):
        return cwd
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else cwd
