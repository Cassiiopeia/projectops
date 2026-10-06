"""한글/영문 상태 라벨 별칭 해소 (#776)."""
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import gh_client  # noqa: E402


def test_한글_요청은_영문만_있는_레포에서_영문으로_치환된다():
    assert gh_client.resolve_label_aliases(["작업완료"], ["status: done", "bug"]) == ["status: done"]


def test_영문_요청은_한글만_있는_레포에서_한글로_치환된다():
    assert gh_client.resolve_label_aliases(["status: in progress"], ["작업중"]) == ["작업중"]


def test_정확히_같은_이름이_있으면_그대로_둔다():
    got = gh_client.resolve_label_aliases(["작업중"], ["작업중", "status: in progress"])
    assert got == ["작업중"]


def test_별칭도_없으면_원문을_유지한다():
    assert gh_client.resolve_label_aliases(["없는라벨"], ["bug"]) == ["없는라벨"]


def test_치환_후_중복은_제거한다():
    got = gh_client.resolve_label_aliases(["작업완료", "status: done"], ["status: done"])
    assert got == ["status: done"]


def test_set_issue_labels는_별칭으로_치환해_교체한다():
    with mock.patch.object(gh_client, "list_labels", return_value=["status: done"]), \
         mock.patch.object(gh_client, "_request", return_value=[{"name": "status: done"}]) as req:
        out = gh_client.set_issue_labels("o", "r", 1, ["작업완료"], "pat")
    assert out["labels"] == ["status: done"] and out["skipped"] == []
    assert req.call_args[0][2] == {"labels": ["status: done"]}


def test_remove_issue_label은_이슈에_붙은_쪽_이름으로_지운다():
    calls = []

    def fake_request(method, url, payload, pat):
        calls.append((method, url))
        return [] if method == "DELETE" else [{"name": "status: todo"}]

    with mock.patch.object(gh_client, "_request", side_effect=fake_request):
        gh_client.remove_issue_label("o", "r", 1, "작업전", "pat")
    assert calls[-1][0] == "DELETE" and calls[-1][1].endswith("/labels/status%3A%20todo")
