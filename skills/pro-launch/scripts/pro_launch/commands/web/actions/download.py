"""`web download` — save the file downloaded by a press into this run's folder and return its path and size (#892)."""
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
    """Save path. A path is used as is, a bare name goes under the run folder ($SHOT_DIR), none uses the site's name.

    If the name has no extension, the site's extension is added. If the name exists, a timestamp is added instead of overwriting.
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
        # Timed out before pressing — a target problem, not a download problem
        if not has_clicked:
            return not_actionable_failure(page, args, "download", info, e)
        return {"ok": False, "code": "download_not_started", "action": "download", "clicked": info,
                "url": page.url, "error": f"Clicked, but no download started within {outcome_seconds}s",
                "next": "web text  # check whether a new window or confirm dialog opened (web dialog --accept)"}
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
            "summary": f"Downloaded: {target.name} ({size} bytes)",
            "next": "Open the file and check its content"}


ACTION = Action(name="download", run=execute,
                options=("selector", "ref", "out", "target_timeout", "confirm_mutating", "frame"),
                help="Click to download, save the file in the run folder ($SHOT_DIR), and return its path and size",
                example="web download --ref 3 --out report.csv")
