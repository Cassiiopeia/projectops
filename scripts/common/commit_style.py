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
    ("${issueNumber}", "{issue_number}"), ("${branchName}", "{branch_name}"), ("${date}", "{date}"),
    ("${labels}", "{labels}"), ("${assignees}", "{assignees}"), ("{변경 사항에 대한 설명}", "{description}"),
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


def read_team_config(repo_root: str) -> dict:
    """version.yml 에서 팀 커밋 설정을 읽는다.

    issue_helper 섹션 해석은 `.github/scripts/issue_helper.py` load_config 와 같은 규칙이다
    (첫 `issue_helper:` 블록만, 끝나면 멈춤, commit_type_map 은 얕은 맵 1개). 배포 경로가 달라
    import 할 수 없어 복제하며, 일치는 test_commit_style 의 렌더 패리티 테스트가 강제한다.
    """
    out = {"template": None, "installed": False, "semver_auto": False, "commit_type_map": {}}
    path = Path(repo_root) / "version.yml"
    if not path.exists():
        return out
    try:
        # BOM 이 붙은 파일도 읽는다 (Windows 편집기)
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
        # 설치 판정은 최상위 키만 본다. 중첩된 같은 이름 키는 projectops 설치의 증거가 아니다.
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
        if indent <= section_indent:  # 섹션 종료 — 뒤에 같은 이름 섹션이 또 있어도 issue_helper 처럼 무시
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
    """(commit_template 또는 None, projectops 설치 여부, semver_auto 여부). 하위호환용 — read_team_config 참조."""
    cfg = read_team_config(repo_root)
    return cfg["template"], cfg["installed"], cfg["semver_auto"]


def resolve_style(prefs_values: dict, repo_root: str, *, legacy_user: bool = False) -> dict:
    """형식 결정: 팀 template > 설치 레포 기본 > 개인 template/preset > (기존 사용자면 projectops) > conventional.

    legacy_user — 예전부터 pro-commit 을 써 온 사람(승인 설정이 남아 있음). 형식을 정한 적이 없으면
    새 기본값 대신 그동안 쓰던 projectops 형식을 유지해 어느 날 갑자기 바뀌지 않게 한다 (spec S1).
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


# 알려진 자리표시자 + 이슈 헬퍼에도 없는 ${...}. 후자는 채울 값이 없으므로 문자 그대로 커밋에
# 박히지 않게 빈 값으로 본다. 한 정규식으로 한 번에 치환해야 제목 속 "${x}" 글자를 건드리지 않는다.
_PLACEHOLDER = re.compile(
    r"\{(issue_title|type|scope|issue_url|issue_number|emoji|branch_name|date|labels|assignees)\}"
    r"|\$\{[A-Za-z_]\w*\}")
_EMPTY = "\x00"  # 빈 값 자리 표식. 주변 구분자를 함께 걷기 위해 잠시 남긴다


def _drop_empty(line: str) -> str:
    """빈 값 때문에 남는 '()'·'[]'·'#'·앞 구분자(' : ' 등)·겹 공백을 지운다."""
    if _EMPTY not in line:
        return line
    # "Refs: {issue_url}" 처럼 라벨 하나와 빈 값뿐인 줄은 라벨째 지운다 (다른 내용이 있으면 손대지 않는다)
    if re.fullmatch(r"\s*\w[\w-]*\s*:\s*\x00\s*", line):
        return ""
    # '#'·'@' 를 먼저 걷어야 "(#{issue_number})" 가 "(\x00)" 이 되어 괄호 규칙에 걸린다
    line = re.sub(r"[#@]\x00", _EMPTY, line)
    line = re.sub(r"[(\[]\x00[)\]]", _EMPTY, line)
    line = re.sub(r"\s*[:|,]\s*\x00", _EMPTY, line)       # 앞 구분자째
    line = re.sub(r"^\s*\x00\s*[:|,]?\s*", "", line)     # 줄 머리면 뒤 구분자째
    line = line.replace(_EMPTY, "")
    return re.sub(r" {2,}", " ", line)


def render(template: str, *, issue_title: str, issue_url: str, commit_type: str, scope: str = "",
           branch_name: str = "", date: str = "", labels: str = "", assignees: str = "") -> str:
    """{description} 만 남기고 채운다. 빈 값 때문에 생기는 '()'·빈 URL 줄·앞 구분자를 지운다.

    branch_name·date·labels·assignees 는 이슈 헬퍼(${branchName} 등)와 같은 자리표시자다.
    모르면 비워 두며, 그 자리는 주변 구분자와 함께 사라진다.
    """
    out = normalize_placeholders(template)
    num = re.search(r"/issues/(\d+)", issue_url or "")
    values = {
        "issue_title": strip_issue_decorations(issue_title) if issue_title else "",
        "type": commit_type, "scope": scope, "issue_url": issue_url or "",
        "issue_number": num.group(1) if num else "", "emoji": _EMOJI.get(commit_type, "🔧"),
        "branch_name": branch_name, "date": date, "labels": labels, "assignees": assignees,
    }
    # 한 번에 치환한다. 순차 replace 면 제목에 든 "{type}" 같은 글자가 뒤의 치환에 다시 걸린다.
    out = _PLACEHOLDER.sub(lambda m: (values[m.group(1)] if m.group(1) else "") or _EMPTY, out)
    lines = [_drop_empty(ln).rstrip() for ln in out.split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines).strip()


def render_for_issue(style: dict, *, issue_title: str, issue_url: str, commit_type: str | None = None,
                     scope: str = "", **extra) -> str:
    """해석된 형식(style)으로 렌더한다. 타입을 안 주면 팀 commit_type_map 까지 반영해 제목 태그에서 유도한다.

    두 CLI(커밋·GitHub)가 이 함수 하나를 써야 이슈 헬퍼 댓글과 같은 타입이 나온다.
    """
    from common.gh_branch import infer_commit_type
    ctype = commit_type or infer_commit_type(issue_title, style.get("commit_type_map") or None)
    return render(style["template"], issue_title=issue_title, issue_url=issue_url, commit_type=ctype,
                  scope=scope, **extra)


def resolve_for_repo(repo_root: str | None = None) -> tuple:
    """레포의 커밋 형식을 해석한다 (팀 > 개인). pro-commit·이슈 헬퍼 CLI 가 같은 결과를 보게 하는 단일 경로."""
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
    """cwd 가 속한 git 레포 루트. 하위 폴더에서 불러도 루트의 version.yml(팀 형식)을 찾게 한다."""
    import os
    import subprocess
    cwd = os.getcwd()
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd,
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return cwd
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else cwd
