"""get-output-path: 대조 산출물 자리 + 에셋 폴더 후보"""
from __future__ import annotations

from pathlib import Path

from common.emit import emit


# =========================================================================
# get-output-path — 산출물 자리를 도구가 정한다
#
# 어디에 둘지 정해 주지 않으면 매번 다른 곳에 쌓인다. 실제로 다른 스킬에서
# 8MB 스크린샷이 엉뚱한 폴더에 추적되는 채로 쌓인 적이 있다 (#611).
# =========================================================================

# 실제 에셋이 갈 곳 후보. 프로젝트 마커로 프레임워크를 짐작한다.
# **고르는 것은 agent 다** — 레포마다 관례가 달라 여기서 단정하지 않는다.
_ASSET_HINTS = (
    ("pubspec.yaml", ("assets/images", "assets/icons", "assets")),
    ("app.json", ("assets/images", "assets")),
    ("package.json", ("src/assets", "public/assets", "public", "assets")),
)


def _asset_dirs(root: Path) -> list[str]:
    """이 프로젝트에서 에셋이 갈 만한 곳. 실재하는 것을 앞에 둔다."""
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
    """이번 대조의 산출물 자리를 만들고 알려준다.

    경로 규칙은 common/paths.py 가 단일 소유한다 (#525) — 여기서 재구현하지
    않고 파일명만 빌려 폴더 이름으로 쓴다.
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

    md = Path(r["path"])          # <우산>/figma/{날짜}_{번호}_{제목}.md
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
        "gitignore": r.get("gitignore"),   # 공통(common/paths)이 심는다
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
