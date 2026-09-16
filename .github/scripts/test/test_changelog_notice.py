"""릴리스 노트 안내 — 정상·예외 경로 전수 검증 (#566).

설계 계약:
  - Job Summary는 **매번** 기록한다 (이메일 알림 없음)
  - PR 댓글은 **AI를 하나도 못 썼을 때만** (품질이 실제로 떨어진 경우)
  - 댓글은 마커로 **갱신**한다 (알림은 처음 한 번만)
  - 안내가 실패해도 **릴리스를 막지 않는다** (항상 exit 0)
"""
import json
import os
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import changelog_notice as notice  # noqa: E402


def write_result(tmp_path, data):
    p = tmp_path / "provider_result.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


# ── Job Summary ──────────────────────────────────────────────────────

class TestSummary:
    def test_shows_each_step(self):
        md = notice.build_summary({"provider": "commit", "attempted": ["copilot", "commit"], "failed": ["copilot"]})
        assert "Copilot" in md and "❌ 실패" in md
        assert "커밋 내용 분석" in md and "✅ 사용됨" in md

    def test_uses_human_labels_not_internal_ids(self):
        md = notice.build_summary({"provider": "openai:gemini", "attempted": ["openai:gemini"], "failed": []})
        assert "Gemini" in md
        assert "openai:gemini" not in md, "내부 라벨을 사람에게 보여주면 안 된다"

    def test_unknown_provider_falls_back_to_raw_name(self):
        md = notice.build_summary({"provider": "newthing", "attempted": ["newthing"], "failed": []})
        assert "newthing" in md, "모르는 이름이라도 빈칸으로 두지 않는다"

    def test_empty_attempted(self):
        md = notice.build_summary({"provider": None, "attempted": [], "failed": []})
        assert "생성 실패" in md or "실행되지 않음" in md

    def test_missing_keys_do_not_crash(self):
        # 결과 파일 스키마가 바뀌어도 죽지 않아야 한다
        assert notice.build_summary({}) != ""


# ── PR 댓글 생성 조건 ────────────────────────────────────────────────

class TestCommentCondition:
    def test_comment_when_ai_all_failed(self):
        body = notice.build_comment({"provider": "commit", "attempted": ["copilot", "commit"], "failed": ["copilot"]})
        assert body is not None
        assert notice.MARKER in body
        assert "aistudio.google.com/apikey" in body, "실행 가능한 다음 행동이 있어야 한다"
        assert "MODEL_API_KEY" in body

    def test_no_comment_when_ai_succeeded(self):
        """경로만 바뀌고 AI가 성공했으면 알리지 않는다 — 소음 방지."""
        assert notice.build_comment({"provider": "openai:gemini", "attempted": ["copilot", "openai:gemini"], "failed": ["copilot"]}) is None

    def test_no_comment_when_commit_was_the_choice(self):
        """처음부터 commit만 시도 = 설정대로 동작 — 알릴 것이 없다."""
        assert notice.build_comment({"provider": "commit", "attempted": ["commit"], "failed": []}) is None

    def test_comment_names_what_was_tried(self):
        body = notice.build_comment({"provider": "commit", "attempted": ["copilot", "openai:gemini", "commit"],
                                     "failed": ["copilot", "openai:gemini"]})
        assert "Copilot" in body and "Gemini" in body

    def test_comment_offers_manual_path(self):
        body = notice.build_comment({"provider": "commit", "attempted": ["copilot", "commit"], "failed": ["copilot"]})
        assert "직접 작성" in body, "키 등록이 싫은 사람에게도 길이 있어야 한다"


# ── 댓글 upsert (API 모킹) ───────────────────────────────────────────

class FakeAPI:
    def __init__(self, comments=None, fail_on=None):
        self.comments = comments or []
        self.fail_on = fail_on
        self.calls = []

    def __call__(self, method, url, token, payload=None):
        self.calls.append((method, url))
        if self.fail_on and self.fail_on in method:
            raise urllib.error.URLError("boom")
        if method == "GET":
            return self.comments
        return {"id": 999}


class TestUpsert:
    def test_creates_when_absent(self, monkeypatch):
        api = FakeAPI(comments=[{"id": 1, "body": "다른 댓글"}])
        monkeypatch.setattr(notice, "request", api)
        notice.upsert_comment("a/b", 1, "tok", "body")
        assert any(m == "POST" for m, _ in api.calls), "기존 댓글이 없으면 생성"

    def test_updates_when_marker_found(self, monkeypatch):
        api = FakeAPI(comments=[{"id": 7, "body": f"{notice.MARKER}\n이전 안내"}])
        monkeypatch.setattr(notice, "request", api)
        notice.upsert_comment("a/b", 1, "tok", "새 body")
        assert any(m == "PATCH" for m, _ in api.calls), "마커가 있으면 갱신 — 알림이 또 가면 안 된다"
        assert not any(m == "POST" for m, _ in api.calls)

    def test_list_failure_is_swallowed(self, monkeypatch, capsys):
        monkeypatch.setattr(notice, "request", FakeAPI(fail_on="GET"))
        notice.upsert_comment("a/b", 1, "tok", "body")  # 예외가 새어나오면 실패
        assert "실패" in capsys.readouterr().err

    def test_write_failure_is_swallowed(self, monkeypatch, capsys):
        monkeypatch.setattr(notice, "request", FakeAPI(comments=[], fail_on="POST"))
        notice.upsert_comment("a/b", 1, "tok", "body")
        assert "릴리스는 계속" in capsys.readouterr().err


# ── main: 어떤 상황에서도 릴리스를 막지 않는다 ───────────────────────

class TestMainNeverBlocks:
    def _run(self, monkeypatch, result_path, tmp_path, token=None):
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        if token:
            monkeypatch.setenv("GITHUB_TOKEN", token)
        else:
            monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setattr(sys, "argv", ["x", "--repo", "a/b", "--pr", "1", "--result", result_path])
        return notice.main(), summary

    def test_missing_result_file(self, monkeypatch, tmp_path):
        code, _ = self._run(monkeypatch, str(tmp_path / "nope.json"), tmp_path)
        assert code == 0, "결과 파일이 없어도 릴리스를 막지 않는다"

    def test_corrupt_result_file(self, monkeypatch, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        code, _ = self._run(monkeypatch, str(bad), tmp_path)
        assert code == 0

    def test_writes_summary(self, monkeypatch, tmp_path):
        rp = write_result(tmp_path, {"provider": "commit", "attempted": ["copilot", "commit"], "failed": ["copilot"]})
        code, summary = self._run(monkeypatch, rp, tmp_path)
        assert code == 0
        assert "릴리스 노트 생성 결과" in summary.read_text(encoding="utf-8")

    def test_no_token_skips_comment_but_keeps_summary(self, monkeypatch, tmp_path, capsys):
        rp = write_result(tmp_path, {"provider": "commit", "attempted": ["copilot", "commit"], "failed": ["copilot"]})
        code, summary = self._run(monkeypatch, rp, tmp_path)
        assert code == 0
        assert "GITHUB_TOKEN 없음" in capsys.readouterr().err
        assert summary.read_text(encoding="utf-8").strip() != "", "토큰이 없어도 요약은 남는다"

    def test_unwritable_summary_path(self, monkeypatch, tmp_path):
        rp = write_result(tmp_path, {"provider": "commit", "attempted": ["commit"], "failed": []})
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "no_such_dir" / "s.md"))
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setattr(sys, "argv", ["x", "--repo", "a/b", "--pr", "1", "--result", rp])
        assert notice.main() == 0, "요약 기록 실패도 릴리스를 막지 않는다"
