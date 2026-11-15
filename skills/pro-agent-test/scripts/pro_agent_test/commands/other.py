"""other: drive things that are not an app, web or server (run · file changes · compare two runs)"""
from __future__ import annotations

import hashlib
import os
import subprocess
import time
from pathlib import Path

from common.emit import emit
from common.proc import bash_executable

from pro_agent_test.scenario_rules import _EXPECT_KEYS, _validate, scenario_target
from pro_agent_test.storage import _expand, _resolve_scenario, _scenario_dir


# =========================================================================
# other — drive things that are not an app, web or server
#
# CI workflows, CLI tools, libraries, templates, batch jobs. Kinds are not enumerated — an enumeration
# would again fail on anything not listed.
#
# **The agent decides what to run and what counts as correct.** This does only three things.
#   ① run it and return the exit code and output
#   ② show **file changes** before and after the run — people miss side effects reading only output
#   ③ run it twice and check the result is the same — idempotence matters but is rarely tried by hand
# =========================================================================

# Skip these when listing files. Counting them is slow and tells nothing.
_SNAP_SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__",
              ".gradle", "build", "dist", ".next", ".dart_tool", "Pods"}
_SNAP_MAX = 20000          # beyond this, give up observing and report that fact


def _fingerprint(f: Path, digest: bool) -> tuple:
    """Fingerprint of one file.

    **Two different questions must not use the same criterion** (learned by measurement).

      "what did this command touch"  → mtime. If it was overwritten, it was touched.
      "is the state the same after two runs"  → **content**. Overwritten with the same content is idempotent.

    The first needs only stat (cheap); the second must read content (expensive).
    So the content hash is taken only with `--twice`.
    """
    st = f.stat()
    if not digest:
        # Look down to nanoseconds. Seconds miss a file changed in the same second to the same size
        # — learned by measurement ("old" → "new" was not caught).
        return (st.st_size, st.st_mtime_ns)
    h = hashlib.sha256()
    with f.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return (st.st_size, h.hexdigest())


def _snapshot(paths: list[Path], digest: bool = False) -> tuple[dict, str | None]:
    """File state per path. If there are too many, return (partial, warning)."""
    seen: dict[str, tuple] = {}
    for base in paths:
        if not base.exists():
            continue
        if base.is_file():
            seen[str(base)] = _fingerprint(base, digest)
            continue
        for f in base.rglob("*"):
            if len(seen) >= _SNAP_MAX:
                return seen, f"Stopped watching after more than {_SNAP_MAX} files — narrow --watch"
            if any(part in _SNAP_SKIP for part in f.parts):
                continue
            try:
                if f.is_file():
                    seen[str(f)] = _fingerprint(f, digest)
            except OSError:
                continue
    return seen, None


def _diff_snapshot(before: dict, after: dict, root: Path) -> dict:
    def rel(p: str) -> str:
        try:
            return str(Path(p).relative_to(root))
        except ValueError:
            return p
    created = sorted(rel(k) for k in after.keys() - before.keys())
    deleted = sorted(rel(k) for k in before.keys() - after.keys())
    modified = sorted(rel(k) for k in (after.keys() & before.keys()) if before[k] != after[k])
    return {"created": created[:100], "modified": modified[:100], "deleted": deleted[:100],
            "counts": {"created": len(created), "modified": len(modified), "deleted": len(deleted)}}


def _tail(text: str, n: int = 40) -> str:
    lines = (text or "").splitlines()
    return "\n".join(lines[-n:])


def _exec_once(command: str, cwd: Path, env: dict, timeout: int) -> dict:
    t0 = time.time()
    try:
        r = subprocess.run([bash_executable(), "-lc", command], cwd=str(cwd), env=env,
                           capture_output=True, text=True, errors="replace", timeout=timeout)
        return {"exit_code": r.returncode, "stdout": r.stdout or "", "stderr": r.stderr or "",
                "elapsed_ms": int((time.time() - t0) * 1000), "timed_out": False}
    except subprocess.TimeoutExpired:
        return {"exit_code": None, "stdout": "", "stderr": "",
                "elapsed_ms": int((time.time() - t0) * 1000), "timed_out": True}


def _judge(step: dict, run: dict, cwd: Path) -> list[str]:
    """Compare with expected results. Says nothing if no condition was given."""
    bad: list[str] = []
    if run["timed_out"]:
        return ["did not finish within the time limit"]

    want_exit = step.get("expect_exit")
    if want_exit is not None and run["exit_code"] != want_exit:
        bad.append(f"exit code is {run['exit_code']} (expected: {want_exit})")

    want_out = step.get("expect_output")
    if want_out:
        if want_out not in (run["stdout"] + run["stderr"]):
            bad.append(f"output does not contain '{want_out}'")

    # Existence is judged **after the run**, not as a change — changes are in files.
    want_file = step.get("expect_file")
    if want_file and not (cwd / want_file).exists():
        bad.append(f"'{want_file}' was not created")

    absent = step.get("expect_absent")
    if absent and (cwd / absent).exists():
        bad.append(f"'{absent}' is still there — it must not exist")
    return bad


def _run_other_step(step: dict, root: Path, cwd: Path, watch: list[Path],
                    env: dict, timeout: int, twice: bool) -> dict:
    before, warn = (_snapshot(watch) if watch else ({}, None))
    run = _exec_once(step["do"], cwd, env, timeout)
    after, warn2 = (_snapshot(watch) if watch else ({}, None))

    out: dict = {
        "do": step["do"],
        "exit_code": run["exit_code"],
        "elapsed_ms": run["elapsed_ms"],
        "stdout_tail": _tail(run["stdout"]),
        "stderr_tail": _tail(run["stderr"]),
    }
    if run["timed_out"]:
        out["timed_out"] = True
    if watch:
        out["files"] = _diff_snapshot(before, after, root)
    if warn or warn2:
        out["watch_warning"] = warn or warn2

    problems = _judge(step, run, cwd)

    if twice and not run["timed_out"]:
        # Idempotence is judged by **content**. Snapshot content after the first run.
        content1, _ = (_snapshot(watch, digest=True) if watch else ({}, None))
        run2 = _exec_once(step["do"], cwd, env, timeout)
        content2, _ = (_snapshot(watch, digest=True) if watch else ({}, None))

        # **Idempotent means "one more run leaves the state unchanged".** Do not compare change lists —
        # run 1 creates files (created) and run 2 overwrites them (modified), so the lists naturally
        # differ while the resulting state may be the same. Fixed after a measured misjudgement.
        settled = (content1 == content2) if watch else None
        out["second_run"] = {
            "exit_code": run2["exit_code"],
            "same_exit": run2["exit_code"] == run["exit_code"],
            "same_stdout": run2["stdout"] == run["stdout"],
            "settled": settled,          # is content unchanged after the second run
            "changed_again": (_diff_snapshot(content1, content2, root) if watch else None),
        }
        # Broken idempotence is not automatically a defect — logs or timestamps may be mixed in.
        # The agent judges. Here only the fact "it differed" is reported.
        if run2["exit_code"] != run["exit_code"]:
            problems.append(f"the second run's exit code differs ({run['exit_code']} → {run2['exit_code']})")
        elif settled is False:
            d = out["second_run"]["changed_again"]["counts"]
            # **Do not assert.** Measured: all three cases were timestamps and append-only logs.
            # Shouting "not idempotent" every time makes people ignore it soon.
            # Report only the facts and where to look — the agent judges.
            problems.append(
                f"the state changed again on the second run (created {d['created']} · modified {d['modified']} "
                f"· deleted {d['deleted']}) — open the files in second_run.changed_again and see "
                f"whether it is timestamps or logs, or truly not idempotent")

    out["problems"] = problems
    out["ok"] = not problems
    return out


def cmd_other(args) -> int:
    """Run the command and also see what it produced."""
    root = Path(args.root).resolve()
    cwd = Path(args.cwd).resolve() if args.cwd else root
    if not cwd.is_dir():
        return emit({"ok": False, "code": "cwd_not_found", "error": f"{cwd} does not exist"})

    env = dict(os.environ)
    for kv in (args.env or []):
        if "=" not in kv:
            return emit({"ok": False, "code": "bad_env",
                         "error": f"--env must be K=V: {kv}"})
        k, v = kv.split("=", 1)
        env[k] = v

    watch = [Path(w) if Path(w).is_absolute() else (cwd / w) for w in (args.watch or [])]

    # ── Driving a scenario: nothing to judge from a screen, so go to the end in one call
    #    (same reason as the server target. If an earlier step fails, later ones are skipped — the real cause would be buried)
    if args.name:
        d = _scenario_dir(root)
        f = _resolve_scenario(d, args.name)
        if f is None:
            return emit({"ok": False, "code": "scenario_not_found",
                         "error": f"Scenario '{args.name}' not found",
                         "next": f"scenario list --root {root}"})
        data, pre = _expand(d, f)
        problems = _validate(data) + pre
        if problems:
            return emit({"ok": False, "code": "scenario_invalid", "problems": problems,
                         "next": "Fix each entry in problems in the scenario file, then run it again"})
        if scenario_target(data) != "other":
            return emit({"ok": False, "code": "wrong_target",
                         "error": f"This scenario's target is '{scenario_target(data)}'",
                         "hint": "other run --name is only for the other target"})

        results, failed_at = [], None
        for i, st in enumerate(data["steps"], 1):
            if st.get("human"):
                results.append({"step": i, "human": st["human"], "skipped": True})
                continue
            r = _run_other_step(st, root, cwd, watch, env, args.timeout, args.twice)
            r["step"] = i
            r["screen"] = st.get("screen")
            results.append(r)
            if not r["ok"]:
                failed_at = i
                break
        return emit({
            "ok": failed_at is None,
            "code": "ok" if failed_at is None else "step_failed",
            "scenario": data.get("name"),
            "steps": results,
            "failed_at": failed_at,
            "summary": ("walked to the end" if failed_at is None
                        else f"stopped at step {failed_at}"),
            "next": (None if failed_at is None else
                     "read stderr_tail and files to pin down the cause"),
        })

    # ── Single run
    if not args.command:
        return emit({"ok": False, "code": "args_required",
                     "error": "one of --command or --name is required",
                     "hint": "--command runs once; --name walks a scenario to the end"})

    step = {"do": args.command}
    for k, v in (("expect_exit", args.expect_exit), ("expect_output", args.expect_output),
                 ("expect_file", args.expect_file), ("expect_absent", args.expect_absent)):
        if v is not None:
            step[k] = v
    r = _run_other_step(step, root, cwd, watch, env, args.timeout, args.twice)
    judged = any(k in step for k in _EXPECT_KEYS["other"])
    r.update({
        "code": "ok" if r["ok"] else "expectation_failed",
        "cwd": str(cwd),
        "judged": judged,
        "summary": (f"exit code {r['exit_code']} · {r['elapsed_ms']}ms"
                    + (f" · {len(r['problems'])} problem(s)" if r["problems"] else "")),
        "next": (None if judged else
                 "no expected result given — read the output and files and judge yourself"),
    })
    return emit(r)
