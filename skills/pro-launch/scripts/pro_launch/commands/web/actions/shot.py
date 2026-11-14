"""`web shot` — take a screenshot. `--container` scrolls an inner scroll area and captures it in tiles (#930)."""
from __future__ import annotations

from pathlib import Path

from pro_launch.commands.web.session import safe_title
from pro_launch.registry import Action
from pro_launch.runtime.context import project_root
from pro_launch.runtime.shots import finish_shot, shot_target

# Tile cap when --tiles is not given · fraction scrolled per step (overlapping, so cut lines join up)
DEFAULT_MAXIMUM_TILES = 20
SCROLL_STEP_RATIO = 0.85
# Time to wait after scrolling for a virtualized list to render (ms)
TILE_SETTLE_MILLISECONDS = 200

# Scroll the container down one step > return whether it hit bottom · position
SCROLL_CONTAINER_JS = """(e, step) => {
  const before = e.scrollTop;
  e.scrollTop = before + Math.floor(e.clientHeight * step);
  return { top: e.scrollTop, moved: e.scrollTop > before,
           is_bottom: e.scrollTop + e.clientHeight >= e.scrollHeight - 1,
           scroll_height: e.scrollHeight, client_height: e.clientHeight };
}"""


def _tile_name(args, index: int) -> str:
    """Tile names: a bare name gives {name}_{n}, a path gives {file}_{n} in the same folder"""
    base = args.out or "container"
    if "/" in base or "\\" in base:
        path = Path(base)
        return str(path.with_name(f"{path.stem}_{index:02d}"))
    return f"{Path(base).stem}_{index:02d}"


def _shoot_container(page, args, root) -> dict:
    """Scroll the container to the top > capture a tile > scroll one step, until the bottom (or --tiles)"""
    container = page.locator(args.container).first
    if page.locator(args.container).count() == 0:
        return {"ok": False, "code": "selector_not_found", "action": "shot", "url": page.url,
                "error": f"No element matches {args.container}", "next": "web find --selector <selector>"}
    container.evaluate("(e) => { e.scrollTop = 0; }")
    limit = args.tiles or DEFAULT_MAXIMUM_TILES
    files, last_scroll = [], {}
    for index in range(1, limit + 1):
        page.wait_for_timeout(TILE_SETTLE_MILLISECONDS)
        raw, explicit = shot_target(root, _tile_name(args, index))
        container.screenshot(path=str(raw))
        files.append(str(finish_shot(raw, explicit, args)))
        last_scroll = container.evaluate(SCROLL_CONTAINER_JS, SCROLL_STEP_RATIO)
        # If it no longer scrolls, the tile just taken is the bottom screen
        if not last_scroll["moved"]:
            break
    is_complete = not last_scroll.get("moved")
    return {"action": "shot", "files": files, "file": files[0], "tiles": len(files), "is_complete": is_complete,
            "container": {"selector": args.container, "scroll_height": last_scroll.get("scroll_height"),
                          "client_height": last_scroll.get("client_height")},
            "url": page.url, "title": safe_title(page),
            "summary": f"Captured {args.container} in {len(files)} tiles" + ("" if is_complete else " (stopped before the bottom — raise --tiles)"),
            "next": "Read the images from the top and decide the next action"}


def configure(p) -> None:
    p.add_argument("--full", action="store_true", help="Whole page")
    p.add_argument("--container", default=None,
                   help="Selector of an inner scrolling area — captured top-down in tiles (_01, _02 …) (for editors where --full gets cut)")
    p.add_argument("--tiles", type=int, default=None, help=f"--container: tile limit (default to the bottom, max {DEFAULT_MAXIMUM_TILES})")


def execute(page, args, state: dict) -> dict:
    # Playwright cannot capture webp (png and jpeg only) — capture png and convert.
    root = project_root(args)
    if args.container:
        return _shoot_container(page, args, root)
    raw, explicit = shot_target(root, args.out)
    if args.selector:
        # One element only — when mockup comparisons or requests need just a part
        page.locator(args.selector).first.screenshot(path=str(raw))
    else:
        page.screenshot(path=str(raw), full_page=args.full)
    final = finish_shot(raw, explicit, args)
    return {"action": "shot", "file": str(final), "url": page.url,
            "title": safe_title(page), "viewport": state.get("viewport"),
            "routes": len(state.get("routes") or []),
            # Put the captured URL in the summary — so an agent reading only the summary notices a wrong tab even if an earlier goto failed (#1149)
            "summary": f"Captured the screen: {final.name} ({page.url})",
            "next": "Read the image and decide the next action"}


ACTION = Action(name="shot", run=execute, configure=configure, options=("selector", "out", "shot_format"),
                help="Capture the screen (shrunk to WebP by default; --container captures an inner scroll area in tiles)",
                example="web shot --out 02_empty --full")
