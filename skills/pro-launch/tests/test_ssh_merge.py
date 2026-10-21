"""pro-ssh 통합 (#841) — 서버 기억 필터 · 첫 접속 사실 기록 · import-ssh · 비밀 미출력. 서버 없이 가짜 ssh 로."""
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_credentials import run, write_cfg  # noqa: E402


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


# ── import-ssh ───────────────────────────────────────────────────────────
def test_import_ssh_prune_은_백업한_뒤_가져온_서버만_옛_섹션에서_지운다(home):
    write_cfg(home, {"ssh": [{"name": "nas", "host": "h", "password": "pw-SECRET99"},
                             {"name": "한글이름", "host": "k", "password": "pw-KEEP"}]})
    r = run(home, "cred", "import-ssh", "--prune")
    assert r["pruned"]["removed"] == ["nas"] and "pw-SECRET99" not in json.dumps(r)
    cfgdir = home / ".projectops" / "config"
    saved = json.loads((cfgdir / "config.json").read_text(encoding="utf-8"))
    assert [s["name"] for s in saved["ssh"]] == ["한글이름"]            # 못 가져온 서버는 옛 섹션에 남는다
    assert saved["launch"]["credentials"]["nas"]["password"] == "pw-SECRET99"
    bak = cfgdir / "config.json.bak-ssh-prune"
    assert bak.exists() and oct(bak.stat().st_mode & 0o777) == "0o600"
    assert "pw-SECRET99" in bak.read_text(encoding="utf-8")            # 백업에서 되돌릴 수 있다


# ── 저장 없이 직접 접속 (일회성) — pro-ssh 가 원래 하던 일을 잃지 않는다 ──────────────

def _recording_ssh(tmp_path: Path) -> Path:
    """받은 인자와 환경변수 SSHPASS 를 파일에 적는 가짜 ssh/sshpass."""
    b = tmp_path / "rbin"
    b.mkdir(exist_ok=True)
    (b / "ssh").write_text('#!/bin/bash\ncat > /dev/null\necho "$@" > "$REC"\necho ok\n')
    (b / "sshpass").write_text('#!/bin/bash\necho "SSHPASS=$SSHPASS" > "$REC.pw"\nshift\nexec "$@"\n')
    for f in ("ssh", "sshpass"):
        (b / f).chmod(0o755)
    return b


def test_저장_없이_비밀번호는_환경변수나_인자로_받고_출력에서_가린다(home, tmp_path):
    rec = tmp_path / "rec"
    r = run(home, "ssh", "--host", "h", "--user", "u", "--password-env", "MY_PW", "--command", "echo pw-ZZZ-9999",
            path_prepend=_recording_ssh(tmp_path), env_extra={"REC": str(rec), "MY_PW": "pw-ZZZ-9999"})
    assert r["ok"] is True
    assert (tmp_path / "rec.pw").read_text().strip() == "SSHPASS=pw-ZZZ-9999"     # sshpass -e 로 전달
    assert "pw-ZZZ-9999" not in json.dumps(r)                                    # 응답에서는 가려진다
    r2 = run(home, "ssh", "--host", "h", "--user", "u", "--password", "inline-PW-1", "--command", "true",
             path_prepend=_recording_ssh(tmp_path), env_extra={"REC": str(rec)})
    assert r2["ok"] is True and "inline-PW-1" not in json.dumps(r2)
