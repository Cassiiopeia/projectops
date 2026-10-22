"""전용 가상환경을 만들고 패키지를 까는 단계 — `web setup` 과 `desktop setup` 이 함께 쓴다 (#985).

결과는 단계 목록(`steps`)으로 돌려준다. 부르는 쪽이 그 목록에 자기 단계를 이어 붙여 한 번에 보고한다.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from common.state import venv_dir, venv_python


def ensure_venv(steps: list, force: bool = False) -> tuple[Path | None, dict | None]:
    """가상환경이 없으면(또는 force) 만든다. (venv 파이썬, 실패 결과) — 실패면 앞이 None."""
    if not venv_python() or force:
        r = subprocess.run([sys.executable, "-m", "venv", str(venv_dir())],
                           capture_output=True, text=True)
        steps.append({"step": "create virtualenv", "ok": r.returncode == 0,
                      "error": (r.stderr or "")[-300:] or None})
        if r.returncode != 0:
            return None, {"ok": False, "code": "venv_failed", "steps": steps,
                          "error": "Could not create the virtualenv"}
    vpy = venv_python()
    if vpy is None:
        return None, {"ok": False, "code": "venv_missing", "steps": steps,
                      "error": "Could not find the virtualenv Python"}
    return vpy, None


def pip_install(vpy: Path, packages: list[str], steps: list, timeout: int = 900) -> bool:
    """venv 에 패키지를 깐다. 결과를 steps 에 남기고 성공 여부를 돌려준다."""
    try:
        r = subprocess.run([str(vpy), "-m", "pip", "install", "-q", *packages],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        r = None
    ok = r is not None and r.returncode == 0
    steps.append({"step": f"install {' · '.join(packages)}", "ok": ok,
                  "error": None if ok else ((r.stderr or "")[-300:] if r else "timed out") or None})
    return ok
