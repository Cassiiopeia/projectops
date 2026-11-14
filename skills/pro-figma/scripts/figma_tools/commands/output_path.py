"""get-output-path: comparison output location + asset folder candidates"""
from __future__ import annotations

from pathlib import Path

from common.emit import emit


# =========================================================================
# get-output-path — the tool decides where outputs go
#
# Without a fixed location, outputs pile up in a different place every time. In another skill
# 8MB screenshots once piled up tracked in the wrong folder (#611).
# =========================================================================

# Candidate destinations for real assets. The framework is guessed from project markers.
# **The agent picks** — conventions differ per repo, so nothing is decided here.
_ASSET_HINTS = (
    ("pubspec.yaml", ("assets/images", "assets/icons", "assets")),
    ("app.json", ("assets/images", "assets")),
    ("package.json", ("src/assets", "public/assets", "public", "assets")),
)


def _asset_dirs(root: Path) -> list[str]:
    """Where assets would likely go in this project. Existing ones come first."""
    out: list[str] = []
    for marker, candidates in _ASSET_HINTS:
        if not (root / marker).is_file():
            continue
        for c in candidates:
            if c not in out:
                out.append(c)
    exists = [c for c in out if (root / c).is_dir()]
    return exists + [c for c in out if c not in exists]


def cmd_output_path(args) -> int:
    """Create and report this comparison's output location.

    Path rules are owned solely by common/paths.py (#525) — not reimplemented
    here; only the file name is borrowed as the folder name.
    """
    try:
        from common.paths import resolve_output_path
    except ImportError:
        return emit({"ok": False, "code": "common_not_found",
                     "error": "scripts/common/paths.py not found",
                     "hint": "Check that the projectops installation is intact"})

    r = resolve_output_path("figma", args.title)
    if r.get("ok") is False:
        return emit(r)

    md = Path(r["path"])          # <umbrella>/figma/{date}_{number}_{title}.md
    run_dir = md.parent / md.stem
    subs = {name: run_dir / name for name in ("dump", "design", "render", "diff")}
    try:
        for d in subs.values():
            d.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return emit({"ok": False, "code": "mkdir_failed", "error": str(e)})

    root = Path(args.root).resolve()
    candidates = _asset_dirs(root)
    return emit({
        "run": md.stem,
        "run_dir": str(run_dir),
        "dump": str(subs["dump"]),
        "design": str(subs["design"]),
        "render": str(subs["render"]),
        "diff": str(subs["diff"]),
        "gitignore": r.get("gitignore"),   # planted by common/paths
        "asset_dir_candidates": candidates,
        "output_root": r.get("output_root"),
        "summary": (f"Comparison folder {run_dir} (not tracked)"
                    + (f" · asset folder candidate {candidates[0]}" if candidates else "")),
        "next": ("**Keep two places apart.** Dumps, design exports, app renders and diff "
                 "images go inside run_dir above — they are evidence, so they are not tracked. "
                 "**Real assets (icons and images the app uses) must not go there.** Pick the "
                 "folder in asset_dir_candidates that fits this project's conventions and pass "
                 "it as localPath to download_figma_images — the app uses those files, so they "
                 "must be committed. If there are no candidates, ask the user"),
    })
