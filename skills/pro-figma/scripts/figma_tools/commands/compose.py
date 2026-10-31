"""store-compose: 장면 파일 > 언어별 HTML + 렌더 작업 목록 + 렌더 스크립트 (#1021)

파일은 run_dir/store/ 아래에만 쓴다 (get-output-path 가 정한 산출물 폴더 밖에는 쓰지 않는다).
렌더(브라우저)는 하지 않는다 — pro-launch `web script` 가 만든 render.py 를 돌린다.
"""
from __future__ import annotations

import json
from pathlib import Path

from common.emit import emit
from figma_tools.commands.store import load_store_specs, resolve_target_locales
from figma_tools.store_html import build_html
from figma_tools.store_render_script import build_render_script
from figma_tools.store_scenes import build_jobs, collect_scene_locales, load_scenes, resolve_theme

STORE_SUBDIR = "store"
SCENES_FILE_NAME = "scenes.json"


def _is_inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _resolve_store_dir(run_dir_arg: str, project_root: Path) -> tuple[Path | None, dict | None]:
    """run_dir 이 산출물 루트 안인지 확인 > run_dir/store. 밖이면 에러 응답"""
    try:
        from common.paths import resolve_output_root
    except ImportError:
        return None, {"ok": False, "code": "common_not_found", "error": "scripts/common/paths.py not found",
                      "hint": "Check that the projectops installation is intact"}
    run_dir = Path(run_dir_arg).resolve()
    output_root = resolve_output_root(project_root).resolve()
    if not run_dir.is_dir() or not _is_inside(run_dir, output_root):
        return None, {"ok": False, "code": "run_dir_invalid",
                      "error": f"--run-dir must be an existing folder inside {output_root}",
                      "hint": "Pass the run_dir printed by get-output-path"}
    return run_dir / STORE_SUBDIR, None


def _stale_image_warnings(images_dir: Path, written: set) -> list:
    """이번 실행이 만들지 않은 이미지 (이전 실행 잔여·손으로 넣은 것) > store-check 장수에 잡히므로 알린다 (지우지는 않음)"""
    if not images_dir.is_dir():
        return []
    stale = sorted(str(p.relative_to(images_dir)) for p in images_dir.rglob("*.png") if p not in written)
    return [{"code": "stale_image", "file": name,
             "message": f"{name} was not produced by this run (earlier run or added by hand) and still counts in store-check"}
            for name in stale]


def cmd_store_compose(args) -> int:
    project_root = Path(args.root).resolve()
    store_dir, error = _resolve_store_dir(args.run_dir, project_root)
    if error:
        return emit(error)
    scenes_path = Path(args.scenes).resolve() if args.scenes else store_dir / SCENES_FILE_NAME
    data, issues = load_scenes(scenes_path)
    if data is None:
        return emit({"ok": False, "code": issues[0]["code"], "error": issues[0]["message"],
                     "hint": f"Write scenes.json at {store_dir / SCENES_FILE_NAME} (format: references/store-assets.md)"})

    specs = load_store_specs()
    theme, theme_issues = resolve_theme(data.get("theme"))
    issues.extend(theme_issues)
    scene_locales = collect_scene_locales(data["scenes"])
    stores_in_use = sorted({o.get("store") for o in data["outputs"] if o.get("store") in specs["stores"]})
    locales_by_store, locale_sources = {}, {}
    for store in stores_in_use:
        locales_by_store[store], locale_sources[store] = resolve_target_locales(
            store, args.locales, project_root, scene_locales)

    jobs, job_issues = build_jobs(data, specs, locales_by_store, args.store)
    issues.extend(job_issues)

    html_dir, images_dir = store_dir / "html", store_dir / "images"
    manifest_path, script_path = store_dir / "render_jobs.json", store_dir / "render.py"
    try:
        store_dir.mkdir(parents=True, exist_ok=True)
        manifest_jobs = _write_job_files(jobs, theme, html_dir, images_dir)
        manifest_path.write_text(json.dumps({"jobs": manifest_jobs}, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
        script_path.write_text(build_render_script(str(manifest_path)), encoding="utf-8")
    except OSError as os_error:
        return emit({"ok": False, "code": "write_failed", "error": str(os_error)})

    written_images = {Path(job["image"]) for job in manifest_jobs}
    warnings = _stale_image_warnings(images_dir, written_images)
    verdict = "issues" if issues or not jobs else "ready"
    return emit({
        "verdict": verdict,
        "summary": (f"{len(jobs)} image job(s) prepared · {len(issues)} issue(s) · {len(warnings)} warning(s)"),
        "next": _next_step(verdict, script_path, images_dir, bool(jobs)),
        "store_dir": str(store_dir),
        "render_script": str(script_path),
        "images_dir": str(images_dir),
        "locales": {store: {"targets": locales_by_store[store], "source": locale_sources[store]}
                    for store in stores_in_use},
        "jobs": [{"id": job["id"], "image": job["image"]} for job in manifest_jobs],
        "issues": issues,
        "warnings": warnings,
    })


def _write_job_files(jobs: list, theme: dict, html_dir: Path, images_dir: Path) -> list:
    """작업마다 HTML 저장 > 매니페스트 항목 (이미지 경로는 store-check 폴더 규약)"""
    manifest_jobs = []
    for job in jobs:
        html_path = html_dir / f"{job['id']}.html"
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(build_html(job, theme), encoding="utf-8")
        image_path = images_dir / job["store"] / job["locale"] / job["slot"] / f"{job['file_name']}.png"
        manifest_jobs.append({"id": job["id"], "width": job["width"], "height": job["height"],
                              "html_uri": html_path.resolve().as_uri(), "image": str(image_path)})
    return manifest_jobs


def _next_step(verdict: str, script_path: Path, images_dir: Path, has_jobs: bool) -> str:
    if not has_jobs:
        return "Fix each item in issues in scenes.json and run store-compose again; nothing was prepared"
    render = (f"Render in your own browser tab: LAUNCH_TAB=compose launch_cli.py web script --file {script_path} "
              f"(pro-launch). Then run store-check --dir {images_dir}. "
              "If text_overflow is not empty, shorten that text or lower the scene's text and render again")
    if verdict == "issues":
        return "Fix the items in issues and run again, or render the prepared jobs now. " + render
    return render
