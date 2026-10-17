"""`web setup` — 전용 환경 · Playwright · 브라우저를 준비한다."""
from __future__ import annotations

import importlib.util
import subprocess
import sys

from common.state import venv_dir, venv_python

import browser_pick

from pro_launch.registry import Action
from pro_launch.runtime.browser import bundled_chromium_path
from pro_launch.runtime.output import out


def _web_setup(force: bool = False) -> dict:
    """전용 가상환경 + Playwright + Pillow + Chromium. 약 100MB 라 부르는 쪽이 먼저 묻는다."""
    vd = venv_dir()
    steps = []
    if not venv_python() or force:
        r = subprocess.run([sys.executable, "-m", "venv", str(vd)],
                           capture_output=True, text=True)
        steps.append({"step": "가상환경 생성", "ok": r.returncode == 0,
                      "error": (r.stderr or "")[-300:] or None})
        if r.returncode != 0:
            return {"ok": False, "code": "venv_failed", "steps": steps,
                    "error": "가상환경을 만들지 못했습니다"}
    vpy = venv_python()
    if vpy is None:
        return {"ok": False, "code": "venv_missing", "steps": steps,
                "error": "가상환경 파이썬을 찾지 못했습니다"}
    # Pillow 를 함께 깐다 — 캡처를 줄이는 수단을 시스템을 건드리지 않고 확보한다
    try:
        r = subprocess.run([str(vpy), "-m", "pip", "install", "-q", "playwright", "pillow"],
                           capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        r = None
    pip_ok = r is not None and r.returncode == 0
    steps.append({"step": "playwright · pillow 설치", "ok": pip_ok,
                  "error": None if pip_ok else ((r.stderr or "")[-300:] if r else "시간 초과") or None})
    if not pip_ok:
        # 내부망: 인덱스가 막혀도 시스템 파이썬에 Playwright 가 이미 있으면 그대로 간다 (#857)
        if importlib.util.find_spec("playwright") is None:
            return {"ok": False, "code": "pip_failed", "steps": steps,
                    "error": "playwright를 설치하지 못했습니다",
                    "next": ("내부망이면 사내 PyPI 미러를 지정해 `pip install playwright pillow` 를 "
                             "시스템에 먼저 깔아 두세요. 브라우저는 설치된 Chrome·Edge 를 씁니다")}
        steps.append({"step": "시스템 Playwright 사용", "ok": True, "error": None,
                      "note": "인덱스에 닿지 않아 전용 환경 설치를 건너뛰고 시스템에 깔린 것을 쓴다"})
    # 이미 쓸 브라우저가 있으면 100MB 를 받지 않는다. 번들이 있으면 기존 동작 그대로다
    pick = browser_pick.resolve(bundled_chromium_path())
    if pick.get("error"):
        return {"ok": False, "code": "browser_env_invalid", "steps": steps, "error": pick["error"],
                "next": f"{browser_pick.ENV_VAR} 를 고치거나 지우세요"}
    if pick["source"] in ("env", "bundled"):
        steps.append({"step": "chromium 내려받기", "ok": True, "error": None,
                      "skipped": True, "note": pick["reason"]})
        return {"ok": True, "steps": steps, "venv": str(vd), "browser": pick["label"],
                "summary": f"웹을 띄울 준비가 됐습니다 ({pick['label']})", "next": "web open --url <주소>"}
    host = browser_pick.download_host()
    reachable = browser_pick.download_host_reachable(host)
    if reachable:
        r = subprocess.run([str(vpy), "-m", "playwright", "install", "chromium"],
                           capture_output=True, text=True, timeout=1800)
        steps.append({"step": "chromium 내려받기", "ok": r.returncode == 0,
                      "error": (r.stderr or "")[-300:] or None})
        if r.returncode == 0:
            return {"ok": True, "steps": steps, "venv": str(vd), "browser": "Playwright Chromium",
                    "summary": "웹을 띄울 준비가 됐습니다", "next": "web open --url <주소>"}
    else:
        steps.append({"step": "chromium 내려받기", "ok": False, "skipped": True,
                      "error": f"{host} 에 닿지 않아 받지 않았다"})
    # 못 받았다 — 설치된 Chrome·Edge 가 있으면 그것으로 간다
    if pick["exe"]:
        return {"ok": True, "steps": steps, "venv": str(vd), "browser": pick["label"],
                "browser_source": "system",
                "summary": f"번들 브라우저는 받지 못했지만 설치된 브라우저({pick['label']})로 웹을 띄웁니다",
                "next": "web open --url <주소>"}
    return {"ok": False, "code": "browser_failed", "steps": steps,
            "error": "브라우저를 받지 못했고 설치된 Chrome·Edge 도 찾지 못했습니다",
            "next": f"Chrome 또는 Edge 를 설치하거나 {browser_pick.ENV_VAR}=<실행 파일 경로> 로 지정하세요"}


def configure(p) -> None:
    p.add_argument("--force", action="store_true", help="setup: 이미 있어도 다시 만든다")


def execute(args) -> int:
    return out(_web_setup(force=args.force))


ACTION = Action(name="setup", needs="nothing", run=execute, configure=configure, options=(),
                help="전용 환경 · Playwright · 브라우저를 준비한다 (약 100MB)", example="web setup")
