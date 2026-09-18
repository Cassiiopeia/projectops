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

