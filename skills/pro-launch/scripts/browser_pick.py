"""어떤 브라우저로 띄울지 정한다 — 내부망처럼 Playwright 번들 Chromium 을 못 받는 곳 대응 (#857).

"내부망인가"를 추측하지 않고 **쓸 수 있는 브라우저가 있나**로 판단한다.
IP 대역·DNS 로 가르면 VPN·핫스팟에서 틀린다. 이 스킬은 브라우저를 독립 프로세스로 띄워
CDP 로 붙으므로, 실행 파일 경로만 바뀌면 나머지는 그대로 돈다.

우선순위
  1. 환경변수 LAUNCH_CHROMIUM_PATH (명시한 것. 잘못된 경로면 조용히 넘어가지 않고 멈춘다)
  2. Playwright 번들 Chromium (기존 동작)
  3. 설치된 Chrome → Edge → Chromium (표준 위치 자동 탐지)
"""
from __future__ import annotations

import os
import shutil
import socket
import ssl
import sys
from pathlib import Path
from urllib.parse import urlparse

ENV_VAR = "LAUNCH_CHROMIUM_PATH"
DEFAULT_DOWNLOAD_HOST = "https://cdn.playwright.dev"


def system_candidates() -> list[tuple[str, Path]]:
    """설치된 Chromium 계열 브라우저의 표준 위치. (이름, 경로) 를 쓸 만한 순서로 준다."""
    found: list[tuple[str, Path]] = []
    if sys.platform == "win32":
        roots = [os.environ.get(k) for k in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
        for root in filter(None, roots):
            found.append(("Chrome", Path(root) / "Google/Chrome/Application/chrome.exe"))
        for root in filter(None, roots):
            found.append(("Edge", Path(root) / "Microsoft/Edge/Application/msedge.exe"))
    elif sys.platform == "darwin":
        apps = Path("/Applications")
        found += [("Chrome", apps / "Google Chrome.app/Contents/MacOS/Google Chrome"),
                  ("Edge", apps / "Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                  ("Chromium", apps / "Chromium.app/Contents/MacOS/Chromium")]
    else:
        for label, names in (("Chrome", ("google-chrome", "google-chrome-stable")),
                             ("Edge", ("microsoft-edge", "microsoft-edge-stable")),
                             ("Chromium", ("chromium", "chromium-browser"))):
            for n in names:
                p = shutil.which(n)
                if p:
                    found.append((label, Path(p)))
    return found


def resolve(bundled: str | None, env: dict | None = None) -> dict:
    """쓸 브라우저를 고른다.

    돌려주는 것: exe(없으면 None) · source(env|bundled|system) · label · reason · error(환경변수가 틀릴 때만)
    """
    env = os.environ if env is None else env
    override = (env.get(ENV_VAR) or "").strip().strip('"')
    if override:
        if Path(override).is_file():
            return {"exe": override, "source": "env", "label": Path(override).stem,
                    "reason": f"환경변수 {ENV_VAR} 로 지정됨"}
        return {"exe": None, "source": "env", "label": ENV_VAR,
                "error": f"{ENV_VAR} 가 가리키는 파일이 없습니다: {override}",
                "reason": "환경변수 경로가 틀림 — 다른 브라우저로 조용히 넘어가지 않는다"}
    if bundled and Path(bundled).is_file():
        return {"exe": bundled, "source": "bundled", "label": "Playwright Chromium",
                "reason": "Playwright 번들 Chromium"}
    for label, path in system_candidates():
        if path.is_file():
            return {"exe": str(path), "source": "system", "label": label,
                    "reason": f"번들 Chromium 이 없어 설치된 브라우저({label})를 씁니다"}
    return {"exe": None, "source": None, "label": None,
            "reason": "번들 Chromium 도, 설치된 Chrome·Edge 도 찾지 못했다"}


def download_host() -> str:
    """Playwright 가 브라우저를 받는 곳. 사내 미러를 쓰는 사람은 PLAYWRIGHT_DOWNLOAD_HOST 로 이미 바꿔 둔다."""
    return (os.environ.get("PLAYWRIGHT_DOWNLOAD_HOST") or DEFAULT_DOWNLOAD_HOST).rstrip("/")


def download_host_reachable(host: str | None = None, timeout: float = 3.0) -> bool:
    """TLS 핸드셰이크까지 가 보고 안 닿으면 False. 100MB 받다 실패하는 것보다 먼저 안다.

    TCP 연결만 보면 부족하다 — 사내 방화벽은 연결은 받아 두고 핸드셰이크에서 끊는다(실측).
    """
    u = urlparse(host or download_host())
    name = u.hostname
    if not name:
        return False
    port = u.port or (443 if u.scheme != "http" else 80)
    try:
        with socket.create_connection((name, port), timeout=timeout) as raw:
            if u.scheme == "http":
                return True
            ctx = ssl.create_default_context()
            ctx.check_hostname = False          # 인증서가 아니라 길이 열렸는지만 본다
            ctx.verify_mode = ssl.CERT_NONE
            raw.settimeout(timeout)
            with ctx.wrap_socket(raw, server_hostname=name):
                return True
    except (OSError, ssl.SSLError):
        return False
