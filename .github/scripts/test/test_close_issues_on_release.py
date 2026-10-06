"""릴리스 시 완료 이슈 닫기 (#771) 판정 규칙."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import close_issues_on_release as c  # noqa: E402


def test_옵션_키가_없으면_꺼져있다_기존_설치_보호():
    assert c.close_on_release_enabled("metadata:\n  template:\n    options:\n      deploy: none\n") is False


def test_옵션이_true일_때만_켜진다():
    on = "    options:\n      close_on_release: true   # 주석\n"
    off = "    options:\n      close_on_release: false\n"
    assert c.close_on_release_enabled(on) is True
    assert c.close_on_release_enabled(off) is False


def test_커밋_메시지에서_이슈_번호를_순서대로_중복없이_모은다():
    msgs = [
        "제목 : feat : x https://github.com/o/r/issues/12",
        "제목 : fix : y https://github.com/o/r/issues/7\nhttps://github.com/o/r/issues/12",
        "다른 저장소 https://github.com/x/y/issues/99",
    ]
    assert c.issue_numbers_from_commits(msgs, "o/r") == [12, 7]


def test_완료_라벨이_있는_열린_이슈만_닫는다():
    assert c.should_close({"state": "open", "labels": [{"name": "status: done"}]})
    assert c.should_close({"state": "open", "labels": [{"name": "작업완료"}]})
    assert not c.should_close({"state": "open", "labels": [{"name": "status: in progress"}]})
    assert not c.should_close({"state": "closed", "labels": [{"name": "status: done"}]})
    assert not c.should_close({"state": "open", "labels": [{"name": "status: done"}], "pull_request": {}})


def _repo(tmp_path):
    import subprocess
    def git(*a):
        return subprocess.run(["git", *a], cwd=tmp_path, capture_output=True, text=True, check=True).stdout.strip()
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    return git


def test_before가_없으면_직전_릴리스_태그부터_현재까지를_구간으로_삼는다(tmp_path, monkeypatch):
    git = _repo(tmp_path)
    for msg in ("old https://github.com/o/r/issues/1", "rel https://github.com/o/r/issues/2"):
        git("commit", "-q", "--allow-empty", "-m", msg)
        if msg.startswith("old"):
            git("tag", "v1")
    git("commit", "-q", "--allow-empty", "-m", "readme version bump")  # 릴리스 뒤 후속 커밋
    monkeypatch.chdir(tmp_path)
    after = git("rev-parse", "HEAD")
    assert c.release_range("", after) == f"v1..{after}"
    nums = c.issue_numbers_from_commits(c.commit_messages("", after), "o/r")
    assert nums == [2]  # 직전 릴리스(v1)의 이슈 #1은 포함되지 않는다


def test_before가_있으면_그_구간을_그대로_쓴다(tmp_path, monkeypatch):
    git = _repo(tmp_path)
    git("commit", "-q", "--allow-empty", "-m", "a")
    before = git("rev-parse", "HEAD")
    git("commit", "-q", "--allow-empty", "-m", "b https://github.com/o/r/issues/5")
    after = git("rev-parse", "HEAD")
    monkeypatch.chdir(tmp_path)
    assert c.release_range(before, after) == f"{before}..{after}"
    assert c.issue_numbers_from_commits(c.commit_messages(before, after), "o/r") == [5]
