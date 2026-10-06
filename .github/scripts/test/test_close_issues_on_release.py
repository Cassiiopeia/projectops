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


# ── #791: dispatch 경로는 태그가 아니라 머지된 릴리스 PR 의 커밋을 쓴다 ─────────

def _release_repo(tmp_path, monkeypatch):
    """실제 릴리스 워크플로우의 모양: 릴리스 커밋들 → 이번 릴리스 태그 → 그 뒤에 붙는 README 커밋."""
    git = _repo(tmp_path)
    git("commit", "-q", "--allow-empty", "-m", "old release https://github.com/o/r/issues/1")
    git("tag", "v1.0.0")
    git("commit", "-q", "--allow-empty", "-m", "fix : x https://github.com/o/r/issues/2")
    git("commit", "-q", "--allow-empty", "-m", "finalize release v1.1.0")
    git("tag", "v1.1.0")                      # 이번 릴리스의 태그가 이미 있다 (태그를 먼저 만든 뒤 후속 워크플로우를 깨운다)
    git("commit", "-q", "--allow-empty", "-m", "readme version bump [skip ci]")
    monkeypatch.chdir(tmp_path)
    return git, git("rev-parse", "HEAD")


def test_태그가_이미_있어도_머지된_릴리스_PR의_커밋_메시지를_쓴다(tmp_path, monkeypatch):
    git, head = _release_repo(tmp_path, monkeypatch)
    release_shas = git("rev-list", "--max-count=3", "HEAD~1").splitlines()   # 릴리스 커밋들 (README 커밋 제외)

    def fake_request(method, url, token, payload=None):
        if "/commits/" in url and url.endswith("/pulls"):
            sha = url.split("/commits/")[1].split("/")[0]
            return ([{"number": 6, "merged_at": "2026-10-07T00:00:00Z", "base": {"ref": "main", "repo": {"default_branch": "main"}},
                      "head": {"ref": "develop"}}] if sha in release_shas else [])
        if "/pulls/6/commits" in url:
            return [{"commit": {"message": "fix : x https://github.com/o/r/issues/2"}},
                    {"commit": {"message": "finalize release v1.1.0"}}]
        raise AssertionError(url)

    monkeypatch.setattr(c, "_request", fake_request)
    msgs = c.release_messages("o/r", "", head, "tok")
    assert c.issue_numbers_from_commits(msgs, "o/r") == [2]      # 이전 릴리스(#1)도, 빈 구간도 아니다


def test_PR을_찾지_못하면_태그_구간으로_대체한다(tmp_path, monkeypatch):
    git, head = _release_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(c, "_request", lambda *a, **k: [])          # 연결된 PR 없음
    msgs = c.release_messages("o/r", "", head, "tok")
    assert msgs                                                       # 죽지 않고 기존 방식으로 이어간다


def test_API가_실패해도_릴리스를_막지_않는다(tmp_path, monkeypatch):
    git, head = _release_repo(tmp_path, monkeypatch)

    def boom(*a, **k):
        raise OSError("network")

    monkeypatch.setattr(c, "_request", boom)
    assert c.release_messages("o/r", "", head, "tok")


def test_push_경로는_before_after_구간을_그대로_쓴다(tmp_path, monkeypatch):
    git = _repo(tmp_path)
    git("commit", "-q", "--allow-empty", "-m", "a")
    before = git("rev-parse", "HEAD")
    git("commit", "-q", "--allow-empty", "-m", "b https://github.com/o/r/issues/5")
    after = git("rev-parse", "HEAD")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(c, "_request", lambda *a, **k: (_ for _ in ()).throw(AssertionError("push 경로는 API 를 부르지 않는다")))
    assert c.issue_numbers_from_commits(c.release_messages("o/r", before, after, "tok"), "o/r") == [5]
