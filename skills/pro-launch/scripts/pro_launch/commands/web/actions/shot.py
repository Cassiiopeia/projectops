"""`web shot` — 화면을 찍는다."""
from __future__ import annotations

from pro_launch.commands.web.session import safe_title
from pro_launch.registry import Action
from pro_launch.runtime.context import project_root
from pro_launch.runtime.shots import finish_shot, shot_target


def configure(p) -> None:
    p.add_argument("--full", action="store_true", help="페이지 전체")


def execute(page, args, state: dict) -> dict:
    # Playwright 는 webp 로 못 찍는다(png·jpeg 만) — png 로 찍고 바꾼다.
    raw, explicit = shot_target(project_root(args), args.out)
    if args.selector:
        # 한 요소만 — 시안 대조·요청서에서 부분만 필요할 때
        page.locator(args.selector).first.screenshot(path=str(raw))
    else:
        page.screenshot(path=str(raw), full_page=args.full)
    final = finish_shot(raw, explicit, args)
    return {"action": "shot", "file": str(final), "url": page.url,
            "title": safe_title(page), "viewport": state.get("viewport"),
            "routes": len(state.get("routes") or []),
            "summary": f"화면을 찍었습니다: {final.name}",
            "next": "이미지를 읽어 다음 조작을 정하세요"}


ACTION = Action(name="shot", run=execute, configure=configure, options=("selector", "out", "shot_format"),
                help="화면을 찍는다 (기본 WebP 로 줄인다)", example="web shot --out 02_empty --full")
