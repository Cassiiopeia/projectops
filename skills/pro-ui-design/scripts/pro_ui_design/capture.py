"""capture command: validate input > job file > call the capture runner (PNG, GIF)"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from common.emit import emit
from common.state import venv_python

from pro_ui_design.session import find_session, write_json_atomically
from pro_ui_design.session_commands import read_server_state
from pro_ui_design.settings import CAPTURES_FOLDER_NAME

WORKER_SCRIPT = Path(__file__).resolve().parent / "capture_worker.py"
JOB_FILE_NAME = "capture-job.json"
WORKER_BASE_TIMEOUT_SECONDS = 120
GIF_SIZE_WARNING_BYTES = 10 * 1024 * 1024
MAX_STEP_MILLISECONDS = 60000
SELECTOR_ACTIONS = ("click", "press", "drag")
OTHER_ACTIONS = ("play", "play-all", "reset", "wait")
FAILURE_NEXT = {
    "browser_missing": "Ask the user, then run launch_cli.py web setup. Otherwise describe the mockup and give the url",
    "pillow_missing": "Run launch_cli.py web setup, or share key frames as PNG with a written description of the motion",
    "step_failed": "Fix that step's selector or order in the steps file and run again",
    "option_not_found": "Use a data-choice value from the mockup",
}


def _read_steps(steps_path: str | None) -> tuple[list | None, str | None]:
    """Validate the steps file: list, known action, required values, time range"""
    if not steps_path:
        return None, "--gif needs --steps (a JSON list of steps)"
    try:
        steps = json.loads(Path(steps_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return None, f"Could not read the steps file: {error}"
    if not isinstance(steps, list) or not steps:
        return None, "The steps file must be a non-empty JSON list"
    for index, step in enumerate(steps):
        action = step.get("action") if isinstance(step, dict) else None
        if action not in SELECTOR_ACTIONS + OTHER_ACTIONS:
            return None, f"Step {index}: action must be one of {', '.join(SELECTOR_ACTIONS + OTHER_ACTIONS)}"
        if action in SELECTOR_ACTIONS and not step.get("selector"):
            return None, f"Step {index}: {action} needs selector"
        if action == "play" and not step.get("option"):
            return None, f"Step {index}: play needs option"
        duration = step.get("ms", 0)
        if not isinstance(duration, int) or not 0 <= duration <= MAX_STEP_MILLISECONDS:
            return None, f"Step {index}: ms must be 0 to {MAX_STEP_MILLISECONDS}"
    return steps, None


def _run_worker(job_file: Path, timeout_seconds: float) -> dict:
    """Prefer the dedicated venv Python, else the current one (browser_missing without Playwright)"""
    interpreter = venv_python() or sys.executable
    try:
        output = subprocess.run([str(interpreter), str(WORKER_SCRIPT), "--job", str(job_file)], capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": "capture_timeout", "error": f"Capture took over {int(timeout_seconds)} seconds",
                "next": "Too many steps or screens in one call, or a page that keeps loading. Split the capture and retry"}
    lines = output.stdout.strip().splitlines()
    try:
        return json.loads(lines[-1])
    except (IndexError, ValueError):
        return {"ok": False, "code": "capture_failed", "error": output.stderr.strip()[-500:] or "The capture worker gave no result"}


def cmd_capture(args) -> int:
    session = find_session(Path(args.root).resolve(), args.title)
    if session is None:
        return emit({"ok": False, "code": "no_session", "error": "No mockup session for this project",
                     "next": "ui_design_cli.py start --title <screen name>"})
    state = read_server_state(session)
    if state is None:
        return emit({"ok": False, "code": "server_stopped", "error": "The mockup server is not running",
                     "next": f"ui_design_cli.py start --title \"{session.title}\", then capture again"})
    screen = args.screen or state["current"]
    if not screen or screen not in {item["name"] for item in state["screens"]}:
        return emit({"ok": False, "code": "screen_not_found", "error": f"No mockup named {screen}",
                     "screens": [item["name"] for item in state["screens"]]})
    steps = None
    if args.gif:
        steps, problem = _read_steps(args.steps)
        if problem:
            return emit({"ok": False, "code": "bad_steps", "error": problem, "next": "Format: references/sharing.md"})

    job = {"port": session.port, "key": session.key, "screen": screen, "device": args.device, "theme": args.theme,
           "speed": args.speed, "option": args.option, "all_options": args.all_options, "gif": args.gif, "steps": steps,
           "max_frames": args.max_frames, "max_width": args.max_width,
           "out_dir": args.out or str(Path(session.run_dir) / CAPTURES_FOLDER_NAME)}
    job_file = session.state_dir / JOB_FILE_NAME
    write_json_atomically(job_file, job)
    held_seconds = sum(step.get("ms", 500) for step in steps) / 1000 if steps else 0
    result = _run_worker(job_file, WORKER_BASE_TIMEOUT_SECONDS + held_seconds * 3)
    job_file.unlink(missing_ok=True)   # Holds the access key, so do not leave it behind

    if not result.get("ok"):
        code = result.get("code")
        return emit({**result, "next": FAILURE_NEXT.get(code, "Read error, fix the cause and run again")})
    warnings = [f"{Path(item['path']).name} is over 10 MB: lower --max-width or shorten the steps"
                for item in result["files"] if args.gif and item["size_bytes"] > GIF_SIZE_WARNING_BYTES]
    warnings += ["Stopped recording at --max-frames" for item in result["files"] if item.get("is_truncated")]
    return emit({**result, "warnings": warnings, "summary": f"{len(result['files'])} file(s) captured",
                 "next": ("Open it with Read to check it. To post on an issue, get approval, then: "
                          "github_cli.py upload-image {owner} {repo} <files> --prefix mockup")})
