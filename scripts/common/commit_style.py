"""커밋 메시지 형식 해석.

한 레포 안에서 형식이 사람마다 갈라지면 안 되므로 팀 형식(version.yml)이 이기고, 말투는 사람이 정한다.
예전 pro-commit 은 형식을 하드코딩해 version.yml 의 commit_template 을 무시했다 — 그래서 팀이 형식을
바꾸면 이슈 헬퍼 댓글과 스킬 결과가 달랐다. 이 모듈이 두 쪽의 같은 정본을 읽는다.
"""
from __future__ import annotations

import re
from pathlib import Path

from common.gh_branch import strip_issue_decorations

PRESETS = {
    # 가장 널리 쓰이는 중립 형식. 이슈가 없으면 URL 줄은 render 가 지운다.
    "conventional": "{type}({scope}): {description}\n\n{issue_url}",
    # 이슈 헬퍼 워크플로우 기본값과 같은 형식 (projectops 설치 레포의 팀 기본값)
    "projectops": "{issue_title} : {type} : {description} {issue_url}",
    "gitmoji": "{emoji} {type}({scope}): {description}\n\n{issue_url}",
}
_EMOJI = {"feat": "✨", "fix": "🐛", "docs": "📝", "refactor": "♻️", "test": "✅", "chore": "🔧", "design": "💄"}

# 이슈 헬퍼(${...})와 한·영 설명 자리표시자를 새 이름으로 통일한다
_LEGACY = [
    ("${issueTitle}", "{issue_title}"), ("${commitType}", "{type}"), ("${issueUrl}", "{issue_url}"),
    ("${issueNumber}", "{issue_number}"), ("{변경 사항에 대한 설명}", "{description}"),
    ("{description of the change}", "{description}"), ("{설명}", "{description}"),
]


def normalize_placeholders(template: str) -> str:
    for old, new in _LEGACY:
        template = template.replace(old, new)
    return template


def _strip_comment(raw: str) -> str:
    # 따옴표 안의 # 은 값이다. issue_helper._strip_comment 와 같은 규칙.
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        end = raw.find(raw[0], 1)
        if end != -1:
            return raw[: end + 1]
    return re.sub(r"\s+#.*$", "", raw)


def _unquote(v: str) -> str:
    v = v.strip()
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"" else v


def read_team_template(repo_root: str) -> tuple:
    """(commit_template 또는 None, projectops 설치 여부, semver_auto 여부)."""
    path = Path(repo_root) / "version.yml"
    if not path.exists():
        return None, False, False
    template, installed, semver = None, False, False
    in_helper, helper_indent = False, 0
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        # 설치 판정은 최상위 키만 본다. 중첩된 같은 이름 키는 projectops 설치의 증거가 아니다.
        if indent == 0 and re.match(r"^(issue_helper|metadata):", s):
            installed = True
        if re.match(r"^semver_auto:\s*true\b", s, re.IGNORECASE):
            semver = True
        if re.match(r"^issue_helper:\s*(#.*)?$", s):
            in_helper, helper_indent = True, indent
            continue
        if in_helper:
            if indent <= helper_indent:
                in_helper = False
                continue
            m = re.match(r"^commit_template\s*:\s*(.*)$", s)
            if m:
                template = _unquote(_strip_comment(m.group(1)))
    return template, installed, semver


def resolve_style(prefs_values: dict, repo_root: str) -> dict:
    warnings = []
    team, installed, semver = read_team_template(repo_root)
    preset = prefs_values.get("preset") or "conventional"
    if preset not in PRESETS and preset != "custom":
        warnings.append(f"알 수 없는 preset '{preset}' — conventional 을 쓴다")
        preset = "conventional"

    if team:
        template, source = normalize_placeholders(team), "version.yml"
    elif installed:
        template, source, preset = PRESETS["projectops"], "team-default", "projectops"
    elif prefs_values.get("template"):
        template, source, preset = normalize_placeholders(prefs_values["template"]), "preferences", "custom"
    elif preset == "custom":
        warnings.append("preset 이 custom 인데 template 이 없다 — conventional 을 쓴다")
        template, source, preset = PRESETS["conventional"], "default", "conventional"
    else:
        template = PRESETS[preset]
        source = "preferences" if prefs_values.get("preset") else "default"

    if semver and "{type}" not in template:
        warnings.append("semver_auto 가 켜진 레포인데 형식에 {type} 이 없다 — 릴리스가 항상 patch 로 판정된다")
    return {"template": template, "source": source, "preset": preset, "warnings": warnings}


_PLACEHOLDER = re.compile(r"\{(issue_title|type|scope|issue_url|issue_number|emoji)\}")


def render(template: str, *, issue_title: str, issue_url: str, commit_type: str, scope: str = "") -> str:
    """{description} 만 남기고 채운다. 빈 값 때문에 생기는 '()'·빈 URL 줄·앞 구분자를 지운다."""
    out = normalize_placeholders(template)
    if not scope:
        out = out.replace("({scope})", "")
    num = re.search(r"/issues/(\d+)", issue_url or "")
    values = {
        "issue_title": strip_issue_decorations(issue_title) if issue_title else "",
        "type": commit_type, "scope": scope, "issue_url": issue_url or "",
        "issue_number": num.group(1) if num else "", "emoji": _EMOJI.get(commit_type, "🔧"),
    }
    # 한 번에 치환한다. 순차 replace 면 제목에 든 "{type}" 같은 글자가 뒤의 치환에 다시 걸린다.
    out = _PLACEHOLDER.sub(lambda m: values[m.group(1)], out)
    lines = []
    for ln in out.split("\n"):
        # 제목이 비면 "제목 : 타입" 형식이 앞에 " : " 를 남긴다. 그 구분자만 떼어낸다.
        if not issue_title:
            ln = ln.lstrip(" :")
        lines.append(ln.rstrip())
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines).strip()
