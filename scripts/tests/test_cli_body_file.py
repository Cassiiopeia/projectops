# scripts/tests/test_cli_body_file.py
#
# pro-issue 통합(#464) 이후 create-issue/update-issue의 body_file 검증은 모두
# github_cli.py 대상이다 (issue_cli는 삭제됨 — create-issue를 github_cli가 흡수).
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
if str(ROOT / "skills/pro-github/scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "skills/pro-github/scripts"))

from common.cli_parser import run_cli  # noqa: E402
from github_cli import build_parser as build_github_parser  # noqa: E402


def test_create_issue_body_file_not_found(capsys):
    parser = build_github_parser()
    # 존재하지 않는 임시 경로를 지정하여 create-issue 실행
    rc = run_cli(parser, ["create-issue", "Cassiiopeia", "projectops", "테스트 이슈", "nonexistent_body.md", "작업전"])

    # 리턴코드는 실패(1)여야 함
    assert rc == 1

    # 출력된 JSON 파싱 및 구조 검증
    out = json.loads(capsys.readouterr().out.strip())
    assert out["ok"] is False
    assert out["code"] == "body_file_not_found"
    assert "body file not found" in out["error"]
    assert out["path_attempted"] == str(Path("nonexistent_body.md").resolve())


def test_create_issue_success_includes_body_length(capsys, tmp_path, monkeypatch):
    # 임시 본문 파일 생성
    body_file = tmp_path / "issue_body.md"
    body_content = "이것은 테스트용 본문입니다."
    body_file.write_text(body_content, encoding="utf-8")

    # github_cli 모듈 자체에 바인딩된 함수들을 Mocking
    import github_cli
    monkeypatch.setattr(
        github_cli,
        "create_issue",
        lambda owner, repo, title, body, labels, pat, assignees: {
            "number": 999,
            "url": "https://github.com/mock/repo/issues/999",
            "title": title,
            "assignees": assignees
        }
    )

    # PAT 검증을 통과시키기 위해 get_github_pat Mocking
    monkeypatch.setattr(github_cli, "get_github_pat", lambda owner, repo: "mock_pat")

    parser = build_github_parser()
    rc = run_cli(parser, [
        "create-issue", "Cassiiopeia", "projectops", "성공 테스트",
        str(body_file), "작업전", "--assignees", "Cassiiopeia"
    ])

    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["number"] == 999
    assert out["body_length"] == len(body_content)


def test_github_cli_update_issue_body_file_not_found(capsys):
    from github_cli import build_parser as build_github_parser
    parser = build_github_parser()
    # 존재하지 않는 임시 경로를 지정하여 update-issue 실행
    rc = run_cli(parser, ["update-issue", "Cassiiopeia", "projectops", "426", "--body-file", "nonexistent_github_update.md"])
    
    # 리턴코드는 실패(1)여야 함
    assert rc == 1
    
    # 출력된 JSON 파싱 및 구조 검증
    out = json.loads(capsys.readouterr().out.strip())
    assert out["ok"] is False
    assert out["code"] == "body_file_not_found"
    assert "body file for the update not found" in out["error"]


def test_github_cli_update_issue_success_includes_body(capsys, tmp_path, monkeypatch):
    from github_cli import build_parser as build_github_parser
    # 임시 수정 본문 파일 생성
    body_file = tmp_path / "github_issue_update_body.md"
    body_content = "github_cli로 수정된 본문입니다."
    body_file.write_text(body_content, encoding="utf-8")
    
    # github_cli 모듈 자체에 바인딩된 update_issue 함수를 Mocking
    import github_cli
    monkeypatch.setattr(
        github_cli, 
        "update_issue", 
        lambda owner, repo, number, pat, title=None, body=None, state=None, labels=None, assignees=None: {
            "number": number,
            "url": f"https://github.com/mock/repo/issues/{number}",
            "title": "기존 제목",
            "body": body
        }
    )
    monkeypatch.setattr(github_cli, "get_github_pat", lambda owner, repo: "mock_pat")
    
    parser = build_github_parser()
    rc = run_cli(parser, [
        "update-issue", "Cassiiopeia", "projectops", "426", 
        "--body-file", str(body_file)
    ])
    
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["number"] == 426
    assert out["body"] == body_content


def test_github_cli_actions_show_run_success(capsys, monkeypatch):
    from github_cli import build_parser as build_github_parser
    import github_cli
    
    monkeypatch.setattr(
        github_cli,
        "get_run",
        lambda owner, repo, run_id, pat: {
            "run_id": run_id,
            "name": "mock-workflow",
            "status": "completed",
            "conclusion": "success",
            "failed_job_ids": []
        }
    )
    monkeypatch.setattr(github_cli, "get_github_pat", lambda owner, repo: "mock_pat")
    
    parser = build_github_parser()
    rc = run_cli(parser, ["actions", "show-run", "Cassiiopeia", "projectops", "28852073219"])
    
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["run_id"] == 28852073219
    assert out["conclusion"] == "success"
    assert out["name"] == "mock-workflow"
