"""github_cli 단위 테스트.

GitHub API 실제 호출 안 함 — emit JSON 출력 형식·argparse 라우팅만 검증.
"""
import json
import sys
import subprocess
from pathlib import Path

CLI = Path(__file__).resolve().parents[1] / "scripts" / "github_cli.py"


def run_cli(*args, env_extra=None):
    env = {**__import__("os").environ}
    if env_extra:
        env.update(env_extra)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    result = subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True, text=True, encoding="utf-8", env=env,
    )
    return result.returncode, result.stdout or "", result.stderr or ""


def test_help_includes_all_subcommands():
    rc, out, err = run_cli("--help")
    combined = out + err
    for cmd in ["get-issue", "get-issues", "update-issue", "add-comment",
                "create-pr", "list-prs", "update-pr", "search-issues",
                "explore", "secrets", "upload-image", "delete-image"]:
        assert cmd in combined, f"{cmd} missing from --help"


def test_get_issue_missing_args_returns_argparse_error():
    """get-issue 호출 시 인자 누락 → JSON bad_args (이슈 #329)."""
    import os
    result = subprocess.run(
        [sys.executable, str(CLI), "get-issue"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["ok"] is False
    assert payload["code"] == "bad_args"
    # error mentions the missing positional 'owner'
    assert "owner" in payload["error"].lower()


def test_emit_format_4_fields_consistent():
    rc, out, err = run_cli("get-issue", "x", "y", "1")
    # 어떤 ok 값이든 JSON 4필드 보장
    lines = [l for l in out.splitlines() if l.strip().startswith("{")]
    if lines:
        parsed = json.loads(lines[0])
        assert "ok" in parsed
        assert "code" in parsed
        assert "summary" in parsed
        assert "next" in parsed


# ── 증적 이미지 업로드 (이슈 #585) ────────────────────────────────────────
#
# 실제 업로드는 네트워크가 필요하므로, 여기서는 **네트워크 없이 판정되는 것**만 고정한다.
# 이름 생성·렌더 가능 판단·마크다운 형식·없는 파일 처리가 그것이다.

def test_asset_name_is_url_safe():
    """자산 이름에 한글·공백이 남으면 URL 인코딩되어 마크다운이 깨진다."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
    from common.gh_client import _asset_name

    for src in ["검증_2번째.png", "스크린샷 2026-09-18.png", "a b c.PNG"]:
        name = _asset_name(src)
        assert all(ch.isascii() for ch in name), f"비 ASCII가 남았다: {name}"
        assert " " not in name, f"공백이 남았다: {name}"


def test_asset_name_has_no_leading_separator():
    """한글만 있는 이름이 '__2.png' 같은 찌꺼기로 변하지 않아야 한다."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
    from common.gh_client import _asset_name

    name = _asset_name("한글만.png")
    stem = name.split("_", 1)[1]        # 시각 접두사 뒤
    assert not stem.startswith(("_", "-", ".")), name
    assert stem == "image.png", f"알아볼 수 없는 이름이면 image로 둔다: {name}"


def test_asset_name_is_unique_per_call():
    """같은 이름을 다시 올리면 GitHub이 422로 거절한다 — 시각으로 고유해야 한다."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
    from common.gh_client import _asset_name

    assert _asset_name("a.png", prefix="issue1").startswith("issue1_")
    assert "_" in _asset_name("a.png")   # 시각 접두사가 붙는다


def test_upload_image_missing_file_returns_json_error():
    """없는 파일을 줘도 stderr+exit이 아니라 JSON으로 답해야 한다."""
    rc, out, err = run_cli("upload-image", "o", "r", "/존재하지/않는/파일.png")
    data = json.loads(out)
    assert data["ok"] is False
    assert data["code"] in ("no_image_uploaded", "missing_pat")


def test_upload_image_requires_files():
    """파일 인자 없이 부르면 argparse가 JSON으로 거절해야 한다."""
    rc, out, err = run_cli("upload-image", "o", "r")
    data = json.loads(out + err) if (out or err).strip().startswith("{") else json.loads(out)
    assert data["ok"] is False
    assert data["code"] == "bad_args"



# =========================================================================
# actions 진단 흐름 (#622)
#
# 예전에는 위치 인자를 run_id·job_id·pr_number·branch 넷으로 쪼개 두어,
# argparse 가 값을 왼쪽부터 채우는 바람에 **문서에 적힌 그대로 불러도**
# joblog·resolve-pr·resolve-branch 셋이 깨졌다. show-run 과 list-failed 만
# 우연히 맞아서 오래 안 보였다.
#
# 네트워크를 타지 않고 **인자 해석만** 본다. PAT 가 없어도 돌아야 한다.
# =========================================================================

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("github_cli_under_test", CLI)
_gh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gh)


def _parse(*argv):
    return _gh.build_parser().parse_args(list(argv))


def test_every_documented_actions_call_lands_in_one_slot():
    """SKILL.md 에 적힌 다섯 형태를 그대로 파싱해 값이 제자리에 들어가는지 본다."""
    cases = [
        ("show-run", "35700287900"),
        ("joblog", "106656419974"),
        ("resolve-pr", "883"),
        ("resolve-branch", "develop"),
    ]
    for sub, value in cases:
        args = _parse("actions", sub, "acme", "app", value)
        assert args.sub == sub
        assert args.arg == value, f"{sub}: 값이 엉뚱한 칸에 들어갔다 — {args.arg!r}"

    no_value = _parse("actions", "list-failed", "acme", "app")
    assert no_value.arg is None


def test_actions_has_exactly_one_positional_value():
    """칸이 둘 이상이면 argparse 가 왼쪽부터 채워 같은 버그가 되돌아온다."""
    args = _parse("actions", "joblog", "acme", "app", "123")
    for stale in ("run_id", "job_id", "pr_number", "branch"):
        assert not hasattr(args, stale), (
            f"위치 인자 {stale} 가 되살아났다 — arg 하나만 두어야 한다")


def test_branch_name_is_not_forced_to_int():
    """`type=int` 를 파서에 걸면 브랜치명이 argparse 단계에서 죽는다."""
    args = _parse("actions", "resolve-branch", "acme", "app", "feature/한글-브랜치")
    assert args.arg == "feature/한글-브랜치"


def test_missing_and_bad_values_are_told_apart(capsys):
    """**안 준 것**과 **잘못 준 것**은 다른 고침을 부른다 — 코드로 갈라야 한다.

    둘 다 그냥 "에러"로 뭉뚱그리면, 값을 빠뜨린 사람이 형식을 의심하며 헤맨다.
    """
    class _Missing:
        sub, owner, repo, arg = "joblog", "acme", "app", None

    value, err = _gh._actions_int(_Missing(), "job_id")
    assert value is None and err is not None
    out = json.loads(capsys.readouterr().out)
    assert out["code"] == "missing_argument", out
    assert "job_id" in out["hint"], out      # 어떻게 불러야 하는지까지

    class _Bad(_Missing):
        arg = "develop"

    value2, err2 = _gh._actions_int(_Bad(), "run_id")
    assert value2 is None and err2 is not None
    out2 = json.loads(capsys.readouterr().out)
    assert out2["code"] == "bad_argument", out2
    assert "develop" in out2["error"], out2  # 무엇이 문제였는지

    # 제대로 준 값은 숫자로 나온다
    class _Good(_Missing):
        arg = "12345"
    assert _gh._actions_int(_Good(), "run_id") == (12345, None)


def test_actions_runs_without_pat_and_reports_it(tmp_path):
    """PAT 없이도 인자 해석까지는 가야 한다 (진단 도구가 먼저 죽으면 안 된다)."""
    rc, out, _ = run_cli("actions", "resolve-branch", "acme", "app", "develop",
                         env_extra={"HOME": str(tmp_path), "USERPROFILE": str(tmp_path),
                                    "GITHUB_PAT": ""})
    d = json.loads(out)
    assert d["code"] == "missing_pat", d      # bad_args 가 아니라 PAT 문제로 보고
