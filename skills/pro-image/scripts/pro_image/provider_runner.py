"""One image tool run: codex (dedicated args) or command (placeholder substitution) > log file + verdict inputs
7 command placeholders: {prompt_file} {prompt_text} {run_dir} {out_dir} {out_file} {size} {timeout_seconds}
A standalone "{refs}" argument expands to several reference paths
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from . import codex_runner

REFS_PLACEHOLDER = "{refs}"
# Tail length kept in the log (characters)
LOG_TAIL_CHARACTERS = 1500


def _expand_command_args(invocation: dict, values: dict, reference_files: list[Path]) -> list[str]:
    expanded = []
    for argument in invocation["args"]:
        if argument == REFS_PLACEHOLDER:
            expanded += [str(reference) for reference in reference_files]
            continue
        for key, value in values.items():
            argument = argument.replace("{" + key + "}", value)
        expanded.append(argument)
    return expanded


def build_command(executable: str, invocation: dict, run_dir: Path, reference_files: list[Path],
                  file_name: str, size_text: str, prompt_text: str) -> list[str]:
    if invocation["kind"] == "codex":
        return codex_runner.build_command(executable, invocation, run_dir, reference_files)
    values = {"prompt_file": str(run_dir / "prompt.md"), "run_dir": str(run_dir), "out_dir": str(run_dir / "out"),
              "out_file": str(run_dir / "out" / file_name), "size": size_text, "prompt_text": prompt_text,
              "timeout_seconds": str(invocation["timeout_seconds"])}
    return [executable, *_expand_command_args(invocation, values, reference_files)]


def _environment(invocation: dict) -> dict:
    # codex: remove API key env vars (forces the subscription path); other tools keep the user's environment
    return codex_runner.subscription_environment() if invocation["kind"] == "codex" else dict(os.environ)


def run_once(command: list[str], invocation: dict, run_dir: Path, prompt_text: str) -> dict:
    log_path = run_dir / "run.log"
    try:
        completed = subprocess.run(command, input=prompt_text if invocation["prompt_via_stdin"] else None,
                                   capture_output=True, encoding="utf-8", errors="replace",
                                   timeout=invocation["timeout_seconds"], cwd=str(run_dir), env=_environment(invocation))
        output, exit_code, is_timed_out = (completed.stdout or "") + (completed.stderr or ""), completed.returncode, False
    except subprocess.TimeoutExpired as expired:
        output, exit_code, is_timed_out = str(expired.stdout or ""), None, True
    log_path.write_text(output, encoding="utf-8")
    # used_image_model: only codex can be judged from its log; other tools get None (unknown)
    used_image_model = codex_runner.GENERATED_IMAGES_MARKER in output if invocation["kind"] == "codex" else None
    return {"provider": invocation["name"], "exit_code": exit_code, "is_timed_out": is_timed_out, "log": str(log_path),
            "log_tail": output[-LOG_TAIL_CHARACTERS:], "used_image_model": used_image_model,
            "reported_unavailable": codex_runner.IMAGE_UNAVAILABLE_PHRASE in output.upper()}
