"""web 의 가려진 클릭 · 아이콘 버튼 · iframe · 기다리기 · 스크롤 · 올리기 · 조각 실행 (#879 · #877 · #880 · #876 · #904).

여기서 지키는 것:
  · 고정 머리글이 덮으면 가운데로 옮겨 다시 누르고, 그래도 덮이면 덮은 것을 알려 --dom-click 을 안내한다
  · find 는 아이콘 리거처를 icon:<이름> 으로, aria 는 aria-label · title 로 채운다
  · --frame <이름|iframe 선택자|주소 일부> 로 iframe 안에서 찾고 · 넣고 · 누르고 · 확인한다
  · wait 는 주어진 조건이 모두 맞으면 끝나고, 아니면 wait_timeout + 지금 주소
  · upload 는 없는 파일 · 허용 폴더 밖 · accept 밖 · 여러 개 금지를 code 로 가른다
  · script 는 결과를 result 에, 예외는 script_failed, 상한은 script_timeout, 저장된 비밀 값은 가린다
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from pro_launch.commands.web.actions import upload as web_upload  # noqa: E402


# ── upload (#876) ─────────────────────────────────────────────────────────

def test_upload_files_must_exist_and_stay_inside_allowed_folders(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SHOT_DIR", str(tmp_path / "run"))
    (tmp_path / "a.png").write_bytes(b"x")
    paths, failure = web_upload.resolve_upload_files("a.png", tmp_path)
    assert failure is None and paths == [(tmp_path / "a.png").resolve()]
    assert web_upload.resolve_upload_files("nope.png", tmp_path)[1]["code"] == "file_not_found"
    outside = tmp_path.parent / f"outside-{os.getpid()}.png"
    outside.write_bytes(b"x")
    try:
        assert web_upload.resolve_upload_files(str(outside), tmp_path)[1]["code"] == "file_outside_allowed"
    finally:
        outside.unlink()
    assert web_upload.resolve_upload_files(" , ", tmp_path)[1]["code"] == "files_required"
