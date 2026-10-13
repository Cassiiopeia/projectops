"""커밋 형식 해석 계약 (#864). 팀 형식 > 개인 형식 > 프리셋."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

from common.commit_style import (  # noqa: E402
    PRESETS, normalize_placeholders, read_team_template, render, resolve_style,
)

URL = "https://github.com/o/r/issues/7"


def _yml(tmp_path, body):
    (tmp_path / "version.yml").write_text(body, encoding="utf-8")
    return str(tmp_path)


def test_plain_repo_defaults_to_conventional(tmp_path):
    s = resolve_style({}, str(tmp_path))
    assert s["preset"] == "conventional" and s["source"] == "default"


def test_projectops_repo_without_template_uses_projectops_format(tmp_path):
    root = _yml(tmp_path, "version: 1.0.0\nmetadata:\n  template:\n    options:\n      semver_auto: true\n")
    s = resolve_style({"preset": "conventional"}, root)
    assert s["template"] == PRESETS["projectops"] and s["source"] == "team-default"


def test_team_template_beats_personal(tmp_path):
    root = _yml(tmp_path, "issue_helper:\n  commit_template: \"#${issueNumber} ${commitType}: {설명}\"\n")
    s = resolve_style({"template": "{type}: {description}"}, root)
    assert s["source"] == "version.yml"


def test_personal_template_when_no_team(tmp_path):
    s = resolve_style({"template": "[{type}] {description}"}, str(tmp_path))
    assert s["template"] == "[{type}] {description}" and s["source"] == "preferences"


def test_unknown_preset_falls_back_with_warning(tmp_path):
    s = resolve_style({"preset": "nope"}, str(tmp_path))
    assert s["preset"] == "conventional" and s["warnings"]


def test_legacy_placeholders():
    t = normalize_placeholders("${issueTitle} : ${commitType} : {변경 사항에 대한 설명} ${issueUrl}")
    assert t == "{issue_title} : {type} : {description} {issue_url}"


def test_render_projectops_matches_old_output():
    out = render(PRESETS["projectops"], issue_title="⚙️[기능추가] 로그인", issue_url=URL, commit_type="feat")
    assert out == f"로그인 : feat : {{description}} {URL}"


def test_conventional_without_issue_drops_url_line():
    out = render(PRESETS["conventional"], issue_title="", issue_url="", commit_type="fix")
    assert out == "fix: {description}"


def test_scope_parens_removed_when_empty():
    assert render("{type}({scope}): {description}", issue_title="", issue_url="", commit_type="feat") \
        == "feat: {description}"


def test_warns_when_type_missing_and_semver_auto(tmp_path):
    root = _yml(tmp_path, "metadata:\n  template:\n    options:\n      semver_auto: true\n"
                          "issue_helper:\n  commit_template: \"{설명} ${issueUrl}\"\n")
    s = resolve_style({}, root)
    assert any("type" in w for w in s["warnings"])


def test_team_reader_agrees_with_issue_helper(tmp_path):
    """워크플로우 댓글과 스킬 결과가 갈라지지 않게, 두 파서가 같은 값을 읽는지 묶는다."""
    import issue_helper
    body = "issue_helper:\n  branch_prefix: \"\"\n  commit_template: \"${commitType}: {설명} ${issueUrl}\"  # 주석\n"
    root = _yml(tmp_path, body)
    assert read_team_template(root)[0] == issue_helper.load_config(root)["commit_template"]
