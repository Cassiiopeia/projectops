"""`desktop` 동작이 함께 쓰는 준비 · 창 고르기 · 화면 비교 · 캡처 저장 (#985)."""
from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path

from common.state import venv_site_packages

import desktop_input

from pro_launch.runtime.context import project_root
from pro_launch.runtime.creds import cred_field
from pro_launch.runtime.mutating import is_mutating_label
from pro_launch.runtime.shots import finish_shot, shot_target

# --window 예약어: 앞 창이 아닌 시스템 대화상자·알림 배너 (macOS)
OVERLAY_QUERY = "overlay"
OVERLAY_ORDER = ("dialog", "notification")
# 위험 판정에서 빼는 종류 — 알림 배너는 열기만 한다
DESKTOP_NAV_ROLES = {"notification"}
# 화면이 멈췄다고 보는 간격 (초) · 최대 대기 (초)
SETTLE_INTERVAL_SECONDS = 0.25
SETTLE_MAX_SECONDS = 3.0


def load_backend() -> tuple[desktop_input.DesktopBackend | None, dict | None]:
    """(백엔드, 실패 결과). 공용 venv 의 site-packages 를 붙인 뒤 의존성을 본다."""
    site = venv_site_packages()
    if site and str(site) not in sys.path:
        sys.path.insert(0, str(site))
    key = desktop_input.platform_key()
    if key not in desktop_input.BACKENDS:
        return None, {"ok": False, "code": "unsupported_on_platform",
                      "error": f"desktop control supports {', '.join(desktop_input.BACKENDS)} for now, not {sys.platform}"}
    try:
        be = desktop_input.get_backend(key)
    except Exception as e:   # noqa: BLE001 — 백엔드 모듈이 OS 라이브러리를 못 가져왔다
        return None, deps_missing(key, [type(e).__name__ + ": " + str(e)[:200]])
    missing = be.missing_modules()
    if missing:
        return None, deps_missing(key, missing, be)
    return be, None


def deps_missing(key: str, missing: list[str], be=None) -> dict:
    packages = " ".join(be.packages) if be else "(see desktop setup)"
    return {"ok": False, "code": "desktop_deps_missing", "platform": key, "missing": missing,
            "error": f"desktop control needs {', '.join(missing)}",
            "fix": "desktop setup", "manual": f"pip install {packages}",
            "next": "desktop setup  # installs into the shared venv (ask the user first)"}


def pick_window(be, query: str | None) -> tuple[dict | None, dict | None]:
    """--window(제목 일부 · pid · 핸들 · overlay) 또는 앞에 있는 창. (창, 실패 결과)"""
    wins = be.windows()
    if not wins:
        return None, {"ok": False, "code": "window_not_found", "error": "No visible windows"}
    if query == OVERLAY_QUERY:
        return _pick_overlay(wins)
    if not query:
        front = next((w for w in wins if w["foreground"]), None)
        if front:
            return front, None
        return None, {"ok": False, "code": "window_not_found", "error": "No window is in front",
                      "candidates": [w["title"] for w in wins[:15]],
                      "next": "desktop windows  # then pass --window"}
    if query.isdigit():
        n = int(query)
        hit = next((w for w in wins if n in (w["handle"], w["pid"])), None)
        if hit:
            return hit, None
    lowered = query.lower()
    hits = [w for w in wins if lowered in w["title"].lower() or lowered == (w.get("app") or "").lower()]
    if hits:
        return hits[0], None
    return None, {"ok": False, "code": "window_not_found", "error": f"No window matches {query!r}",
                  "candidates": [w["title"] for w in wins[:15]],
                  "next": "desktop windows  # pick a title from candidates"}


def ordered_overlays(wins: list[dict]) -> list[dict]:
    """시스템 대화상자(2FA·권한 팝업) > 알림 배너 순. 소유 프로세스를 몰라도 고를 수 있게 한다."""
    return [w for kind in OVERLAY_ORDER for w in wins if w.get("overlay") and w.get("overlay_kind") == kind]


def _pick_overlay(wins: list[dict]) -> tuple[dict | None, dict | None]:
    found = ordered_overlays(wins)
    if found:
        return found[0], None
    return None, {"ok": False, "code": "window_not_found", "error": "No system dialog or notification is on screen",
                  "next": "desktop windows"}


def windows_to_search(be, query: str | None) -> tuple[list[dict], dict | None]:
    """글자로 찾는 동작(find · wait)이 훑을 창. overlay 는 전부 — 대화상자가 떠 있어도 배너를 찾게."""
    if query == OVERLAY_QUERY:
        found = ordered_overlays(be.windows())
        return (found, None) if found else ([], _pick_overlay([])[1])
    window, failure = pick_window(be, query)
    return ([window] if window else []), failure


def public_window(w: dict) -> dict:
    return {k: w[k] for k in ("handle", "pid", "app", "title", "bounds", "foreground", "minimized", "elevated",
                              "overlay", "overlay_kind") if k in w}


def listed_nodes(nodes: list[dict]) -> list[dict]:
    """보여 줄 노드만 골라 위험 버튼 표시 (desktop 은 설치·동의·허용 계열도 막음)
    알림 배너는 제외 — text 가 본문이고 누르면 열 뿐. 숨은 버튼은 `click --action` 이 이름으로 판정"""
    shown = [n for n in nodes if desktop_input.is_worth_listing(n)]
    for n in shown:
        n["mutating"] = (n["clickable"] and n["role"] not in DESKTOP_NAV_ROLES
                         and is_mutating_label(f"{n['text']} {n['desc']}", is_desktop=True))
    return shown


def compare_region(window: dict, node: dict) -> list[int]:
    """누른 뒤 화면 변화를 볼 영역. 알림 센터 창은 화면 전체라 배너 자리만 본다 (다른 앱 변화를 섞지 않게)."""
    if window.get("overlay_kind") == "notification" and node.get("bounds"):
        return node["bounds"]
    return window["bounds"]


def screen_digest(be, region: list[int] | None) -> str | None:
    png = be.grab(region)
    return hashlib.sha1(png).hexdigest() if png else None


def settle(be, region: list[int] | None, before: str | None) -> tuple[bool | None, float]:
    """화면이 바뀌고 멈출 때까지 기다린다. (바뀌었나, 기다린 초). 캡처를 못 하면 (None, 0)."""
    if before is None:
        return None, 0.0
    started = time.monotonic()
    last = before
    changed = False
    while time.monotonic() - started < SETTLE_MAX_SECONDS:
        time.sleep(SETTLE_INTERVAL_SECONDS)
        now = screen_digest(be, region)
        if now is None:
            return None, round(time.monotonic() - started, 2)
        if now != before:
            changed = True
        if changed and now == last:
            break
        last = now
    return changed, round(time.monotonic() - started, 2)


def save_shot(be, args, region: list[int] | None, name: str | None) -> str | None:
    """캡처를 저장하고 경로를 돌려준다 (WebP, 긴 변 1200px — app·web 과 같다)."""
    png = be.grab(region)
    if not png:
        return None
    raw, explicit = shot_target(project_root(args), name, ".png")
    Path(raw).write_bytes(png)
    return str(finish_shot(Path(raw), explicit, args))


def secret_text(args) -> tuple[str | None, bool, dict | None]:
    """(입력값, 비밀인가, 실패 결과). --text-env · --cred 는 비밀, --text 는 평문."""
    if getattr(args, "text_env", None):
        value = os.environ.get(args.text_env)
        if value is None:
            return None, True, {"ok": False, "code": "env_not_set",
                                "error": f"Environment variable {args.text_env} is empty",
                                "hint": f'Prefix the same command with {args.text_env}="..."'}
        return value, True, None
    if getattr(args, "cred", None):
        value, err = cred_field(args.cred, getattr(args, "cred_field", None))
        return value, True, err
    return getattr(args, "text", None), False, None


def masked(text: str, secret: str | None) -> str:
    return text.replace(secret, "***") if secret and len(secret) >= 4 else text
