"""`web shot` — 화면을 찍는다. `--container` 는 안쪽 스크롤 영역을 내려가며 조각으로 찍는다 (#930)."""
from __future__ import annotations

from pathlib import Path

from pro_launch.commands.web.session import safe_title
from pro_launch.registry import Action
from pro_launch.runtime.context import project_root
from pro_launch.runtime.shots import finish_shot, shot_target

# --tiles 를 안 줬을 때 조각 수 상한 · 한 번에 내리는 비율(겹치게 해서 잘린 줄을 잇는다)
DEFAULT_MAXIMUM_TILES = 20
SCROLL_STEP_RATIO = 0.85
# 스크롤 뒤 가상화 목록이 그려지길 기다리는 시간(ms)
TILE_SETTLE_MILLISECONDS = 200

# 컨테이너를 한 칸 내리고 > 바닥인가 · 위치를 돌려준다
SCROLL_CONTAINER_JS = """(e, step) => {
  const before = e.scrollTop;
  e.scrollTop = before + Math.floor(e.clientHeight * step);
  return { top: e.scrollTop, moved: e.scrollTop > before,
           is_bottom: e.scrollTop + e.clientHeight >= e.scrollHeight - 1,
           scroll_height: e.scrollHeight, client_height: e.clientHeight };
}"""


def _tile_name(args, index: int) -> str:
    """조각 이름: 이름만 주면 {이름}_{번호}, 경로를 주면 같은 폴더의 {파일}_{번호}"""
    base = args.out or "container"
    if "/" in base or "\\" in base:
        path = Path(base)
        return str(path.with_name(f"{path.stem}_{index:02d}"))
    return f"{Path(base).stem}_{index:02d}"


def _shoot_container(page, args, root) -> dict:
    """컨테이너를 맨 위로 올리고 > 조각 찍기 > 한 칸 내리기를 바닥(또는 --tiles)까지"""
    container = page.locator(args.container).first
    if page.locator(args.container).count() == 0:
        return {"ok": False, "code": "selector_not_found", "action": "shot", "url": page.url,
                "error": f"{args.container} 에 맞는 요소가 없습니다", "next": "web find --selector <선택자>"}
    container.evaluate("(e) => { e.scrollTop = 0; }")
    limit = args.tiles or DEFAULT_MAXIMUM_TILES
    files, last_scroll = [], {}
    for index in range(1, limit + 1):
        page.wait_for_timeout(TILE_SETTLE_MILLISECONDS)
        raw, explicit = shot_target(root, _tile_name(args, index))
        container.screenshot(path=str(raw))
        files.append(str(finish_shot(raw, explicit, args)))
        last_scroll = container.evaluate(SCROLL_CONTAINER_JS, SCROLL_STEP_RATIO)
        # 더 안 내려가면 방금 찍은 것이 바닥 화면이다
        if not last_scroll["moved"]:
            break
    is_complete = not last_scroll.get("moved")
    return {"action": "shot", "files": files, "file": files[0], "tiles": len(files), "is_complete": is_complete,
            "container": {"selector": args.container, "scroll_height": last_scroll.get("scroll_height"),
                          "client_height": last_scroll.get("client_height")},
            "url": page.url, "title": safe_title(page),
            "summary": f"{args.container} 를 {len(files)}조각으로 찍었다" + ("" if is_complete else " (바닥 전에 멈춤 — --tiles 를 늘린다)"),
            "next": "이미지를 위에서부터 읽어 다음 조작을 정하세요"}


def configure(p) -> None:
    p.add_argument("--full", action="store_true", help="페이지 전체")
    p.add_argument("--container", default=None,
                   help="안쪽에서 스크롤되는 영역의 선택자 — 위에서부터 내려가며 조각(_01, _02 …)으로 찍는다 (--full 이 잘리는 편집기용)")
    p.add_argument("--tiles", type=int, default=None, help=f"--container: 조각 수 상한 (기본 바닥까지, 최대 {DEFAULT_MAXIMUM_TILES})")


def execute(page, args, state: dict) -> dict:
    # Playwright 는 webp 로 못 찍는다(png·jpeg 만) — png 로 찍고 바꾼다.
    root = project_root(args)
    if args.container:
        return _shoot_container(page, args, root)
    raw, explicit = shot_target(root, args.out)
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
                help="화면을 찍는다 (기본 WebP 로 줄인다, --container 는 안쪽 스크롤 영역을 조각으로)",
                example="web shot --out 02_empty --full")
