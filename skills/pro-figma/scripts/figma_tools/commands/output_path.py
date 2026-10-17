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
                     "error": "scripts/common/paths.py 를 찾지 못했습니다",
                     "hint": "projectops 설치가 온전한지 확인하세요"})

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
        "summary": (f"대조 자리 {run_dir} (추적 안 함)"
                    + (f" · 에셋은 {candidates[0]} 후보" if candidates else "")),
        "next": ("**두 곳을 구분하세요.** 덤프·시안 export·앱 렌더·차이 그림은 위 "
                 "run_dir 안에 둡니다 — 증거라서 추적하지 않습니다. "
                 "**실제 에셋(앱이 쓸 아이콘·이미지)은 여기 두면 안 됩니다.** "
                 "asset_dir_candidates 중 이 프로젝트의 관례에 맞는 곳을 골라 "
                 "download_figma_images 의 localPath 로 주세요 — 앱이 쓰는 파일이라 "
                 "커밋되어야 합니다. 후보가 비었으면 사용자에게 물어보세요"),
    })
