"""`render` — draw a state in code and capture it (run · collect · clean · residue check)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from common.proc import bash_executable
from pro_launch.registry import Command
from pro_launch.runtime.context import project_root, state_home
from pro_launch.runtime.output import out
from pro_launch.runtime.render_scaffold import render_scaffold, settle_scaffold_after_run
from pro_launch.runtime.shots import shot_folder


#
# The agent writes render code **temporarily** in the target repo from the references/render.md recipe.
# The script does not guess the state management approach (Riverpod · Bloc · Redux …).
# Here it only runs, collects, cleans and checks residue. The command enforces what a person
# did by hand in one Flutter app: "remove the files, then confirm with git status".
_RENDER_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def _git_status(root: Path) -> list[str] | None:
    """Changed paths, tracked or not. None if not a git repo — no residue check possible."""
    try:
        r = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return sorted(line for line in r.stdout.splitlines() if line.strip())


def _inside(root: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _unique(dst: Path) -> Path:
    """Add a number if the name exists. Overwriting would lose the previous state's capture."""
    if not dst.exists():
        return dst
    n = 2
    while True:
        cand = dst.with_name(f"{dst.stem}-{n}{dst.suffix}")
        if not cand.exists():
            return cand
        n += 1


def _split_cleanup_paths(values: list[str] | None) -> list[str]:
    """--cleanup values > list of paths (repeated flags and comma lists both, #1178)"""
    return [part.strip() for value in values or [] for part in value.split(",") if part.strip()]


# Files the render command creates as tool by-products (relative to --cwd) — only those absent before the command are removed (#1178)
# flutter test recreates macos/Podfile every time on a macOS host
_TOOL_GENERATED_FILES = ("macos/Podfile", "ios/Podfile")


def _missing_tool_generated(cwd: Path) -> list[Path]:
    """Tool by-product paths that do not exist yet before the command runs"""
    return [cwd / rel for rel in _TOOL_GENERATED_FILES if not (cwd / rel).exists()]


def _remove_tool_generated(root: Path, candidates: list[Path]) -> list[str]:
    """Remove only tool by-products that appeared after the command > removed paths (relative to repo)"""
    removed = []
    for target in candidates:
        if target.is_file() and _inside(root, target):
            target.unlink()
            removed.append(target.resolve().relative_to(root.resolve()).as_posix())
    return removed


def _cleanup(root: Path, paths: list[str]) -> tuple[list[str], list[str]]:
    """Remove only the given paths. **Paths outside the repo are refused** — one typo could wipe someone else's folder."""
    removed, refused = [], []
    for raw in _split_cleanup_paths(paths):
        t = (root / raw) if not Path(raw).is_absolute() else Path(raw)
        if not _inside(root, t) or t.resolve() == root.resolve():
            refused.append(raw)
            continue
        if t.is_dir():
            shutil.rmtree(t, ignore_errors=True)
            removed.append(raw)
        elif t.exists():
            t.unlink()
            removed.append(raw)
    return removed, refused


# Find the first compile error (#901): errors appear early in the output and often not in output_tail (last 40 lines)
# Dart compiler: test/_launch_render/states_test.dart:12:5: Error: Undefined name 'MethodChannel'.
_DART_COMPILE_ERROR = re.compile(r"^\S+\.dart:\d+:\d+: Error: ")
# Other tools (gcc·javac·tsc etc.): "x.java:3: error: ...", "error TS2304: ..." — only when preceded by line start, space or colon
_GENERIC_ERROR = re.compile(r"(?i)(?:^|[\s:])error(?: TS\d+)?\s*:")
# Max number of source/caret (^^^) context lines following an error line
_FIRST_ERROR_CONTEXT_LINES = 2
# Max length of the first error line put in summary
_SUMMARY_ERROR_MAX_CHARS = 200


def find_first_error(output: str) -> str | None:
    """Build output > first compile error line (+ up to 2 indented context lines). Dart format first, then a generic error: line, else None"""
    lines = output.splitlines()
    for pattern in (_DART_COMPILE_ERROR, _GENERIC_ERROR):
        for index, line in enumerate(lines):
            if not pattern.search(line):
                continue
            picked = [line.rstrip()]
            # Only immediately following indented lines count as context (stop at a blank line or the next error)
            for following in lines[index + 1:index + 1 + _FIRST_ERROR_CONTEXT_LINES]:
                if not following.strip() or not following[:1].isspace():
                    break
                picked.append(following.rstrip())
            return "\n".join(picked)
    return None


_RENDER_BASE = "render-baseline.json"


def _baseline_path(root: Path) -> Path:
    return state_home(root) / _RENDER_BASE


def cmd_render(args) -> int:
    root = project_root(args)
    if args.action == "snapshot":
        return _render_snapshot(root)
    if args.action == "scaffold":
        return out(render_scaffold(root, args.app, lambda: _take_baseline(root)))
    if not args.cmd:
        return out({"ok": False, "code": "cmd_required", "error": "--cmd is required"})

    # The baseline must be the state **before temp files are created**. Taking it right before run puts already-created
    # temp files into the baseline, so anything --cleanup misses is not caught as residue (found by trying it for real).
    base_f = _baseline_path(root)
    before, baseline_from = None, "run"
    if base_f.is_file():
        try:
            saved = json.loads(base_f.read_text(encoding="utf-8"))
            if saved.get("root") == str(root):
                before, baseline_from = saved.get("status"), "snapshot"
        except (OSError, json.JSONDecodeError):
            pass
    if before is None:
        before = _git_status(root)
    cwd = (root / args.cwd) if args.cwd else root
    if not cwd.is_dir():
        return out({"ok": False, "code": "cwd_not_found",
                    "error": f"--cwd folder does not exist: {cwd}",
                    "next": "--cwd is a path relative to the repo root (--root)"})
    tool_generated_candidates = _missing_tool_generated(cwd)
    try:
        r = subprocess.run([bash_executable(), "-lc", args.cmd], cwd=str(cwd), capture_output=True,
                           text=True, errors="replace", timeout=args.timeout, stdin=subprocess.DEVNULL)
        rc, output = r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired as e:
        rc = -1
        output = ((e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes)
                  else (e.stdout or "")) + f"\n[time limit of {args.timeout}s exceeded]"
    tail = "\n".join(output.splitlines()[-40:])

    collected: list[str] = []
    renamed: list[str] = []
    if rc == 0:
        shot_dir = shot_folder(root)
        for pattern in args.collect or []:
            for f in sorted(root.glob(pattern)):
                if f.is_file() and f.suffix.lower() in _RENDER_EXT and _inside(root, f):
                    dst = _unique(shot_dir / f.name)
                    shutil.move(str(f), str(dst))
                    collected.append(str(dst))
                    if dst.name != f.name:   # renamed because the name existed: report it so the old file is not mistaken for the new result (#1078)
                        renamed.append(dst.name)

    # Clean up even on failure — a leftover temp test file is itself residue
    removed, refused = _cleanup(root, args.cleanup)
    removed_generated = _remove_tool_generated(root, tool_generated_candidates)
    after = _git_status(root)
    residue = None
    if before is not None and after is not None:
        residue = [line for line in after if line not in before]
    if baseline_from == "snapshot":
        base_f.unlink(missing_ok=True)   # single use — the next render is not measured against a stale baseline
    # If the scaffold folder was removed, clean up the manifest too (#948)
    scaffold_state = settle_scaffold_after_run(root)

    payload = {"exit_code": rc, "collected": collected, "saved_under_new_name": renamed or None, "removed": removed,
               "removed_tool_generated": removed_generated or None, "refused_cleanup": refused or None, "residue": residue,
               "git_checked": before is not None, "baseline": baseline_from}
    if rc != 0:
        first_error = find_first_error(output)
        summary = f"Render command failed (exit code {rc}) — cleaned up without collecting"
        if first_error:
            summary += f" · first error: {first_error.splitlines()[0][:_SUMMARY_ERROR_MAX_CHARS]}"
        # first_error as an early key — read before the long output_tail
        payload = {"ok": False, "code": "render_failed", "summary": summary,
                   "first_error": first_error, **payload, "output_tail": tail,
                   "next": ("Fix first_error first (for a missing import, see the recipe's imports). "
                            if first_error else "Read output_tail and fix the render code. ")
                           + "Check the recipe's pitfalls table first"}
    elif residue:
        # Do not delete — it may be another session's change
        payload.update({"ok": False, "code": "residue",
                        "summary": f"Render left {len(residue)} leftover path(s) in the repo: {_residue_preview(residue)}",
                        "next": "Check the leftover paths: if you created them, add them to --cleanup and run again, or delete them yourself. "
                                "Leave changes you do not recognize alone"})
    elif not collected:
        payload.update({"ok": False, "code": "nothing_collected",
                        "summary": "The command succeeded but no images were collected",
                        "next": "Check that the --collect glob matches the render output paths (relative to the repo root)"})
    else:
        renamed_note = f" · saved under a new name because the old one exists: {', '.join(renamed)}" if renamed else ""
        payload.update({"summary": f"Collected {len(collected)} image(s) · no leftovers{renamed_note}"
                                   + ("" if before is not None else " (not a git repo, so leftovers were not checked)"),
                        "next": "Open them with Read. Shrink them with shrink before attaching to an issue"})
    if scaffold_state:
        payload.update(scaffold_state)
    if refused:
        payload["warning"] = f"Not deleted because outside the repo: {', '.join(refused)}"
    return out(payload)


# Number of residue paths shown in summary — the rest go in the residue field
_RESIDUE_PREVIEW_COUNT = 3


def _residue_preview(residue: list[str]) -> str:
    """git status lines > a few paths ('?? a, ?? b (+2 more)') — visible even when --brief drops residue"""
    shown = ", ".join(residue[:_RESIDUE_PREVIEW_COUNT])
    rest = len(residue) - _RESIDUE_PREVIEW_COUNT
    return shown + (f" (+{rest} more)" if rest > 0 else "")


def _take_baseline(root: Path) -> dict:
    """Save the residue-check baseline. scaffold reuses the baseline (snapshot) already taken"""
    f = _baseline_path(root)
    if f.is_file():
        try:
            if json.loads(f.read_text(encoding="utf-8")).get("root") == str(root):
                return {"from": "snapshot", "path": str(f)}
        except (OSError, json.JSONDecodeError):
            pass
    status = _git_status(root)
    if status is None:
        return {"from": "none", "note": "Not a git repo — leftovers will not be checked"}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"root": str(root), "status": status,
                             "at": time.strftime("%Y-%m-%d %H:%M:%S")}, ensure_ascii=False),
                 encoding="utf-8")
    return {"from": "scaffold", "path": str(f), "changed_now": len(status)}


def _render_snapshot(root: Path) -> int:
    status = _git_status(root)
    if status is None:
        return out({"ok": False, "code": "not_git", "error": "Not a git repo, so no baseline for the leftover check can be taken",
                    "hint": "render run still works — it cleans up and skips the leftover check"})
    f = _baseline_path(root)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"root": str(root), "status": status,
                             "at": time.strftime("%Y-%m-%d %H:%M:%S")}, ensure_ascii=False),
                 encoding="utf-8")
    return out({"baseline": str(f), "changed_now": len(status),
                "summary": f"Baseline taken ({len(status)} path(s) already changed — these are not counted as leftovers)",
                "next": "Flutter: render scaffold creates the temporary render folder. Other stacks: write the temporary render code, then call render run"})


def configure_render(p) -> None:
    p.add_argument("action", choices=["snapshot", "scaffold", "run"],
                   help="snapshot: take the leftover-check baseline **before** creating temporary files · "
                        "scaffold: create the Flutter temporary render folder (fonts incl. icons, golden skeleton) · run: run and collect")
    p.add_argument("--app", default=None, help="scaffold: Flutter app folder (relative to --root). Default: version.yml project_paths, then pubspec.yaml search")
    p.add_argument("--cmd", default=None, help="run: render command (runs the temporary test the agent wrote)")
    p.add_argument("--collect", action="append", default=None,
                   help="Glob of images to collect (relative to the repo root, repeatable). e.g. client/test/_launch_render/**/*.png")
    p.add_argument("--cleanup", action="append", default=None,
                   help="Path to delete afterwards (inside the repo only; repeat the flag or give a comma list). Temporary test files and folders. "
                        "macos/Podfile · ios/Podfile created by the command are removed without it")
    p.add_argument("--cwd", default=None, help="Where to run the command (relative to the repo root, e.g. client)")
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--root", default=".", help="Target repo root — the base for the leftover check")


COMMANDS = [
    Command(name="render", help="Run a render command, collect images and check for leftovers", run=cmd_render,
            configure=configure_render),
]
