"""#836 — 레포를 알 수 없는 폴더 · 상태 루트 격리 · docstring · access 성적.

지키려는 것:
  · 스킬·플러그인 캐시 폴더(원격 없음)에서 불려도 `scripts` 같은 가짜 버킷이 생기지 않는다
  · 정상 레포는 예전과 같은 자리에 쓴다
  · PROJECTOPS_HOME 이 상태 루트를 정한다 — 테스트가 실제 홈에 쓰지 않는다
  · 적어 둔 접속 방법이 먹혔는지 도구가 직접 기록하고, 실패가 앞서면 verify 로 알린다
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_launch_cli import _j  # noqa: E402
import launch_cli  # noqa: E402
from common import state as common_state  # noqa: E402


def _fake_skill_dir(tmp_path: Path, kind: str = "skills") -> Path:
    """원격 없는 플러그인 캐시를 흉내 낸다 — 이 체크아웃은 원격이 있어 그대로 쓸 수 없다."""
    if kind == "skills":
        d = tmp_path / "cache" / "skills" / "pro-launch" / "scripts"
    else:
        d = tmp_path / ".claude" / "plugins" / "cache" / "projectops" / "scripts"
    d.mkdir(parents=True)
    return d


# ── 상태 루트 ────────────────────────────────────────────────────────────

def test_base_dir_prefers_projectops_home(tmp_path, monkeypatch):
    monkeypatch.setenv("PROJECTOPS_HOME", str(tmp_path / "ph"))
    assert common_state.base_dir() == tmp_path / "ph"
    monkeypatch.delenv("PROJECTOPS_HOME")
    assert common_state.base_dir() == Path.home() / ".projectops"


def test_unknown_root_warns_and_writes_no_fake_bucket(tmp_path):
    d = _fake_skill_dir(tmp_path)
    env = {k: v for k, v in os.environ.items() if k != "PROJECT_ROOT"}
    r = subprocess.run([sys.executable, str(launch_cli._HERE), "access", "set", "--key", "base_url",
                        "--json", '{"url":"http://localhost:1"}', "--root", str(d)],
                       capture_output=True, text=True, encoding="utf-8", env=env)
    out = _j(r.stdout)
    assert out["root_unknown"] is True and "--root" in out["next"], out
    launch = common_state.base_dir() / "launch"
    assert (launch / "_machine" / "access.json").is_file()
    assert sorted(p.name for p in launch.iterdir()) == ["_machine"], "가짜 버킷이 생겼다"
