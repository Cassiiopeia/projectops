"""스킬이 쌓는 상태의 자리 — 프로젝트 밖(홈)에 둔다 (pro-launch · pro-agent-test 공용, #629).

    ~/.projectops/launch/<owner__repo>/      devices.json · browser.json · access.json ·
                                             .browser-profile/ · shots/
    ~/.projectops/launch/.venv               Playwright · Pillow
    ~/.projectops/agent-test/<owner__repo>/  learned.json · 시나리오 · flows/

예전에는 전부 agent-test 폴더 하나에 섞여 있었다. 실행·캡처가 pro-launch 로 떨어져
나가면서 "붙는 법"은 launch 로 옮긴다. 옛 폴더에 남은 파일은 첫 호출 때 옮긴다.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

KINDS = ("launch", "agent-test")

# launch 가 가져가는 몫. 나머지(learned.json · 시나리오 · flows)는 agent-test 에 남는다.
LAUNCH_OWNED = ("devices.json", "browser.json", "access.json", ".browser-profile", "shots")
# 브라우저가 떠 있는 동안 옮기면 안 되는 것 — 프로필을 쓰는 중이고 상태 파일이 그 경로를 가리킨다
_BROWSER_FILES = ("browser.json", ".browser-profile")


def base_dir() -> Path:
    return Path.home() / ".projectops"


def repo_key(root: Path) -> str:
    """프로젝트를 가리키는 키. git remote의 owner/repo를 쓴다.

    **경로를 키로 쓰면 안 된다.** 워크트리마다 경로가 달라 같은 프로젝트가 여러 개로
    갈라지고, 그러면 쌓은 지식이 워크트리 수만큼 쪼개진다.
    remote가 없는(로컬 전용) 저장소는 폴더명으로 떨어진다.
    """
    try:
        url = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        url = ""
    m = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?$", url) if url else None
    if m:
        return f"{m.group(1)}__{m.group(2)}"
    return re.sub(r"[^A-Za-z0-9._-]+", "-", Path(root).name).strip("-") or "unknown"


def state_dir(kind: str, root: Path) -> Path:
    """kind 별 상태 폴더. 만들지는 않는다 — 쓰는 쪽이 필요할 때 만든다."""
    if kind not in KINDS:
        raise ValueError(f"알 수 없는 kind: {kind}")
    return base_dir() / kind / repo_key(root)


def _pid_alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except (ProcessLookupError, ValueError, TypeError, OSError):
        return False


def migrate_launch(root: Path) -> dict:
    """옛 agent-test 폴더에 있는 launch 몫을 launch 폴더로 옮긴다.

    - 새 폴더에 이미 있으면 건드리지 않는다 (멱등 — 두 번째 실행부터는 아무 일도 없다)
    - 브라우저가 떠 있으면 브라우저 관련은 다음으로 미룬다 (쓰는 중인 프로필을 옮기면 깨진다)
    - 옮기다 실패하면 옛 경로를 계속 읽도록 경고만 낸다 — 기능이 멈추면 안 된다
    """
    old = state_dir("agent-test", root)
    new = state_dir("launch", root)
    moved: list[str] = []
    warnings: list[str] = []
    if not old.is_dir():
        return {"moved": moved, "warnings": warnings}

    browser_busy = False
    bj = old / "browser.json"
    if bj.is_file():
        try:
            browser_busy = _pid_alive(json.loads(bj.read_text(encoding="utf-8")).get("pid"))
        except (OSError, json.JSONDecodeError, AttributeError):
            browser_busy = False

    for name in LAUNCH_OWNED:
        src, dst = old / name, new / name
        if not src.exists() or dst.exists():
            continue
        if browser_busy and name in _BROWSER_FILES:
            warnings.append(f"{name}: 브라우저가 떠 있어 옮기지 않았습니다 — web close 뒤 다시 옮겨집니다")
            continue
        try:
            new.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            moved.append(name)
        except OSError as e:
            warnings.append(f"{name}: 옮기지 못했습니다 ({e}) — 옛 자리를 계속 씁니다")

    # 상태 파일이 옛 프로필 경로를 들고 있으면 새 자리로 고친다
    nbj = new / "browser.json"
    if "browser.json" in moved and nbj.is_file():
        try:
            data = json.loads(nbj.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("profile"):
                data["profile"] = str(new / ".browser-profile")
                nbj.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            pass
    return {"moved": moved, "warnings": warnings}


def launch_file(root: Path, name: str) -> Path:
    """launch 몫 파일의 실제 자리. 새 자리에 없고 옛 자리에만 있으면 옛 자리를 쓴다.

    이전(migration)이 실패했을 때도 기능이 이어지게 하는 안전망이다.
    """
    new = state_dir("launch", root) / name
    if new.exists():
        return new
    old = state_dir("agent-test", root) / name
    return old if old.exists() else new


# ── 전용 가상환경 ────────────────────────────────────────────────────────
#
# 시스템 파이썬에 깔지 않는다 — macOS Homebrew 파이썬은 PEP 668로 pip를 막는다.
# 옛 자리(agent-test/.venv)는 옮기지 않는다. 약 100MB 를 다시 받게 만들 이유가 없다.

def venv_dir() -> Path:
    new = base_dir() / "launch" / ".venv"
    old = base_dir() / "agent-test" / ".venv"
    if _venv_exe(new):
        return new
    if _venv_exe(old):
        return old
    return new   # 아직 없으면 새로 만들 자리


def _venv_exe(d: Path) -> Path | None:
    exe = d / ("Scripts" if os.name == "nt" else "bin") / (
        "python.exe" if os.name == "nt" else "python")
    return exe if exe.is_file() else None


def venv_python() -> Path | None:
    return _venv_exe(venv_dir())


def venv_site_packages() -> Path | None:
    d = venv_dir()
    for pat in ("lib/python*/site-packages", "Lib/site-packages"):
        for sp in d.glob(pat):
            if sp.is_dir():
                return sp
    return None
