"""other: 앱·웹·서버가 아닌 것 밟기 (실행 · 파일 변화 · 두 번 실행 비교)"""
from __future__ import annotations

import hashlib
import os
import subprocess
import time
from pathlib import Path

from common.emit import emit

from pro_agent_test.scenario_rules import _EXPECT_KEYS, _validate, scenario_target
from pro_agent_test.storage import _expand, _resolve_scenario, _scenario_dir


# =========================================================================
# other — 앱·웹·서버가 아닌 것을 밟는다
#
# CI 워크플로·CLI 툴·라이브러리·템플릿·배치. 종류를 열거하지 않는다 — 열거하면
# 목록에 없는 것은 또 못 한다.
#
# **무엇을 돌릴지와 무엇이 맞는지는 agent 가 정한다.** 여기서 하는 일은 셋뿐이다.
#   ① 돌리고 종료코드·출력을 돌려준다
#   ② 실행 전후 **파일 변화**를 보여준다 — 사람은 출력만 보고 부작용을 놓친다
#   ③ 두 번 돌려 같은지 본다 — 멱등은 중요한데 손으로는 거의 안 해본다
# =========================================================================

# 파일 목록을 뜰 때 건너뛸 것. 이것을 세면 느리기만 하고 알려주는 것이 없다.
_SNAP_SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__",
              ".gradle", "build", "dist", ".next", ".dart_tool", "Pods"}
_SNAP_MAX = 20000          # 이보다 많으면 관찰을 포기하고 그 사실을 알린다


def _fingerprint(f: Path, digest: bool) -> tuple:
    """파일 한 개의 지문.

    **두 가지 다른 질문에 같은 기준을 쓰면 안 된다** (실측으로 겪었다).

      "이 명령이 무엇을 건드렸나"  → 수정시각. 덮어썼으면 건드린 것이다.
      "두 번 돌려도 상태가 같은가"  → **내용**. 덮어써도 내용이 같으면 멱등이다.

    앞의 것은 stat 만으로 충분하고(싸다), 뒤의 것은 내용을 읽어야 한다(비싸다).
    그래서 내용 해시는 `--twice` 일 때만 뜬다.
    """
    st = f.stat()
    if not digest:
        # 나노초까지 본다. 초 단위로 보면 같은 초에 같은 크기로 바뀐 파일을 놓친다
        # — 실측으로 겪었다 ("old" → "new" 가 안 잡혔다).
        return (st.st_size, st.st_mtime_ns)
    h = hashlib.sha256()
    with f.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return (st.st_size, h.hexdigest())


def _snapshot(paths: list[Path], digest: bool = False) -> tuple[dict, str | None]:
    """경로별 파일 상태. 너무 많으면 (부분, 경고)를 돌려준다."""
    seen: dict[str, tuple] = {}
    for base in paths:
        if not base.exists():
            continue
        if base.is_file():
            seen[str(base)] = _fingerprint(base, digest)
            continue
        for f in base.rglob("*"):
            if len(seen) >= _SNAP_MAX:
                return seen, f"파일이 {_SNAP_MAX}개를 넘어 관찰을 멈췄습니다 — --watch 를 좁히세요"
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
        r = subprocess.run(["bash", "-lc", command], cwd=str(cwd), env=env,
                           capture_output=True, text=True, timeout=timeout)
        return {"exit_code": r.returncode, "stdout": r.stdout or "", "stderr": r.stderr or "",
                "elapsed_ms": int((time.time() - t0) * 1000), "timed_out": False}
    except subprocess.TimeoutExpired:
        return {"exit_code": None, "stdout": "", "stderr": "",
                "elapsed_ms": int((time.time() - t0) * 1000), "timed_out": True}


def _judge(step: dict, run: dict, cwd: Path) -> list[str]:
    """기대 결과와 대조한다. 조건을 주지 않았으면 아무 말도 하지 않는다."""
    bad: list[str] = []
    if run["timed_out"]:
        return ["제한 시간 안에 끝나지 않았습니다"]

    want_exit = step.get("expect_exit")
    if want_exit is not None and run["exit_code"] != want_exit:
        bad.append(f"종료코드가 {run['exit_code']} 입니다 (기대: {want_exit})")

    want_out = step.get("expect_output")
    if want_out:
        if want_out not in (run["stdout"] + run["stderr"]):
            bad.append(f"출력에 '{want_out}' 이 없습니다")

    # 존재 여부는 **실행 뒤** 기준이다. 변화가 아니다 — 변화는 files 를 본다.
    want_file = step.get("expect_file")
    if want_file and not (cwd / want_file).exists():
        bad.append(f"'{want_file}' 이 만들어지지 않았습니다")

    absent = step.get("expect_absent")
    if absent and (cwd / absent).exists():
        bad.append(f"'{absent}' 이 남아 있습니다 — 나오면 안 되는 것입니다")
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
        # 멱등은 **내용** 기준이다. 1회차 뒤 상태를 내용으로 떠 둔다.
        content1, _ = (_snapshot(watch, digest=True) if watch else ({}, None))
        run2 = _exec_once(step["do"], cwd, env, timeout)
        content2, _ = (_snapshot(watch, digest=True) if watch else ({}, None))

        # **멱등은 "한 번 더 돌려도 상태가 그대로"다.** 변화 목록끼리 비교하면 안 된다 —
        # 1회차는 파일을 만들고(created) 2회차는 덮어쓰므로(modified) 목록은 당연히
        # 다르고, 그래도 결과 상태는 같을 수 있다. 실측으로 오판을 겪어 고쳤다.
        settled = (content1 == content2) if watch else None
        out["second_run"] = {
            "exit_code": run2["exit_code"],
            "same_exit": run2["exit_code"] == run["exit_code"],
            "same_stdout": run2["stdout"] == run["stdout"],
            "settled": settled,          # 두 번째 실행 뒤 내용이 그대로인가
            "changed_again": (_diff_snapshot(content1, content2, root) if watch else None),
        }
        # 멱등이 깨진 것이 곧 결함은 아니다 — 로그·타임스탬프가 섞였을 수도 있다.
        # 판단은 agent 가 한다. 여기서는 "달랐다"는 사실만 올린다.
        if run2["exit_code"] != run["exit_code"]:
            problems.append(f"두 번째 실행의 종료코드가 다릅니다 ({run['exit_code']} → {run2['exit_code']})")
        elif settled is False:
            d = out["second_run"]["changed_again"]["counts"]
            # **단정하지 않는다.** 실측해 보니 세 건 다 타임스탬프와 append-only 로그
            # 때문이었다. 매번 "멱등이 아니다"라고 외치면 사람이 곧 무시하게 된다.
            # 사실만 올리고 어디를 보면 되는지 알려준다 — 판단은 agent 가 한다.
            problems.append(
                f"두 번 돌리자 상태가 또 바뀌었습니다 (생성 {d['created']} · 수정 {d['modified']} "
                f"· 삭제 {d['deleted']}) — second_run.changed_again 의 파일을 열어 "
                f"시간·로그 때문인지, 진짜로 멱등이 아닌지 보세요")

    out["problems"] = problems
    out["ok"] = not problems
    return out


def cmd_other(args) -> int:
    """명령을 돌리고, 무엇이 만들어졌는지까지 함께 본다."""
    root = Path(args.root).resolve()
    cwd = Path(args.cwd).resolve() if args.cwd else root
    if not cwd.is_dir():
        return emit({"ok": False, "code": "cwd_not_found", "error": f"{cwd} 가 없습니다"})

    env = dict(os.environ)
    for kv in (args.env or []):
        if "=" not in kv:
            return emit({"ok": False, "code": "bad_env",
                         "error": f"--env 는 K=V 형태여야 합니다: {kv}"})
        k, v = kv.split("=", 1)
        env[k] = v

    watch = [Path(w) if Path(w).is_absolute() else (cwd / w) for w in (args.watch or [])]

    # ── 시나리오를 밟는 경우: 화면을 보고 판단할 것이 없으므로 한 번에 끝까지 간다
    #    (server 타겟과 같은 이유. 앞이 실패하면 뒤는 밟지 않는다 — 진짜 원인이 묻힌다)
    if args.name:
        d = _scenario_dir(root)
        f = _resolve_scenario(d, args.name)
        if f is None:
            return emit({"ok": False, "code": "scenario_not_found",
                         "error": f"시나리오 '{args.name}' 을 찾지 못했습니다",
                         "next": f"scenario list --root {root}"})
        data, pre = _expand(d, f)
        problems = _validate(data) + pre
        if problems:
            return emit({"ok": False, "code": "scenario_invalid", "problems": problems})
        if scenario_target(data) != "other":
            return emit({"ok": False, "code": "wrong_target",
                         "error": f"이 시나리오의 target은 '{scenario_target(data)}' 입니다",
                         "hint": "other run --name 은 other 타겟 전용입니다"})

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
            "summary": ("끝까지 밟았습니다" if failed_at is None
                        else f"{failed_at}번째 단계에서 멈춤"),
            "next": (None if failed_at is None else
                     "stderr_tail 과 files 를 읽고 원인을 짚으세요"),
        })

    # ── 한 번만 돌리는 경우
    if not args.command:
        return emit({"ok": False, "code": "args_required",
                     "error": "--command 또는 --name 중 하나가 필요합니다",
                     "hint": "--command 는 한 번 돌리고, --name 은 시나리오를 끝까지 밟습니다"})

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
        "summary": (f"종료코드 {r['exit_code']} · {r['elapsed_ms']}ms"
                    + (f" · 문제 {len(r['problems'])}건" if r["problems"] else "")),
        "next": (None if judged else
                 "기대 결과를 주지 않았습니다 — 출력과 files 를 읽고 직접 판단하세요"),
    })
    return emit(r)
