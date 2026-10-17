"""`web download` — 눌러서 받은 파일을 이번 실행 폴더에 저장하고 경로·크기를 돌려준다 (#891)."""
from __future__ import annotations

import os
import time
from pathlib import Path

from pro_launch.commands.web.element import (is_timeout_error, locate_target, not_actionable_failure,
                                             outcome_wait_seconds, target_wait_seconds)
from pro_launch.registry import Action
from pro_launch.runtime.context import project_root
from pro_launch.runtime.shots import shot_folder


def download_path(root: Path, out_name: str | None, suggested: str) -> Path:
    """저장 경로. 경로를 주면 그대로, 이름만 주면 실행 폴더($SHOT_DIR) 아래, 없으면 사이트가 준 이름.

    이름에 확장자가 없으면 사이트가 준 이름의 확장자를 붙인다. 같은 이름이 있으면 시각을 붙여 덮어쓰지 않는다.
    """
    if out_name and (os.sep in out_name or "/" in out_name):
        target = Path(out_name)
        target.parent.mkdir(parents=True, exist_ok=True)
        return target
    name = out_name or suggested or "download"
    if out_name and not Path(out_name).suffix:
        name += Path(suggested).suffix
    target = shot_folder(root) / name
    if target.exists():
        target = target.with_name(f"{target.stem}_{time.strftime('%Y%m%d-%H%M%S')}{target.suffix}")
    return target


def execute(page, args, state: dict) -> dict:
    element, info, failure = locate_target(page, args, state, "download")
    if failure:
        return failure
    outcome_seconds = outcome_wait_seconds(args)
    has_clicked = False
    try:
        with page.expect_download(timeout=outcome_seconds * 1000) as download_info:
            element.click(timeout=target_wait_seconds(args) * 1000)
            has_clicked = True
        download = download_info.value
    except Exception as e:
        if not is_timeout_error(e):
            raise
        # 누르기 전에 시간이 다 됐다 — 내려받기 문제가 아니라 대상 문제다
        if not has_clicked:
            return not_actionable_failure(page, args, "download", info, e)
        return {"ok": False, "code": "download_not_started", "action": "download", "clicked": info,
                "url": page.url, "error": f"눌렀지만 {outcome_seconds}초 안에 내려받기가 시작되지 않았습니다",
                "next": "web text  # 새 창·확인 대화상자가 떴는지 본다 (web dialog --accept)"}
    reason = download.failure()
    if reason:
        return {"ok": False, "code": "download_failed", "action": "download", "clicked": info,
                "url": page.url, "error": str(reason)[:300]}
    target = download_path(project_root(args), args.out, download.suggested_filename)
    download.save_as(str(target))
    size = target.stat().st_size
    return {"action": "download", "file": str(target), "bytes": size,
            "suggested_filename": download.suggested_filename, "source_url": download.url,
            "clicked": info, "url": page.url,
            "summary": f"내려받음: {target.name} ({size} bytes)",
            "next": "파일을 열어 내용을 확인한다"}


ACTION = Action(name="download", run=execute,
                options=("selector", "ref", "out", "target_timeout", "confirm_mutating"),
                help="눌러서 받은 파일을 실행 폴더($SHOT_DIR)에 저장하고 경로·크기를 돌려준다",
                example="web download --ref 3 --out report.csv")
