"""`render` — 코드로 상태를 그려 찍는다 (실행 · 수집 · 청소 · 흔적 검사)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from pro_launch.registry import Command
from pro_launch.runtime.context import project_root, state_home
from pro_launch.runtime.output import out
from pro_launch.runtime.shots import shot_folder


#
# 렌더 코드는 agent 가 references/render.md 레시피를 보고 대상 레포에 **임시로** 짠다.
# 상태 관리 방식(Riverpod · Bloc · Redux …)을 스크립트가 알아맞히지 않는다.
# 여기서는 실행 · 수집 · 청소 · 흔적 검사만 한다. 한 Flutter 앱에서 사람이 챙긴
# "파일을 치운 뒤 git status 로 확인"을 명령이 강제한다.
_RENDER_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def _git_status(root: Path) -> list[str] | None:
    """추적 여부와 상관없이 바뀐 경로. git 레포가 아니면 None — 흔적 검사를 못 한다."""
    try:
        r = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
                           capture_output=True, text=True, timeout=30)
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
    """같은 이름이 있으면 번호를 붙인다. 덮어쓰면 앞 상태의 캡처가 사라진다."""
    if not dst.exists():
        return dst
    n = 2
    while True:
        cand = dst.with_name(f"{dst.stem}-{n}{dst.suffix}")
        if not cand.exists():
            return cand
        n += 1


def _cleanup(root: Path, paths: list[str]) -> tuple[list[str], list[str]]:
    """지정한 경로만 지운다. **레포 밖은 거절한다** — 오타 하나로 남의 폴더가 날아간다."""
    removed, refused = [], []
    for raw in paths or []:
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


# 첫 컴파일 오류 찾기 (#901): 오류는 출력 앞쪽에 나오고 output_tail(끝 40줄)에는 안 보이는 일이 잦다
# Dart 컴파일러: test/_launch_render/states_test.dart:12:5: Error: Undefined name 'MethodChannel'.
_DART_COMPILE_ERROR = re.compile(r"^\S+\.dart:\d+:\d+: Error: ")
# 그 밖의 도구 (gcc·javac·tsc 등): "x.java:3: error: ...", "error TS2304: ..." — 앞이 줄 처음·공백·콜론일 때만
_GENERIC_ERROR = re.compile(r"(?i)(?:^|[\s:])error(?: TS\d+)?\s*:")
# 오류 줄 뒤에 붙는 소스 줄·캐럿(^^^) 문맥 최대 줄 수
_FIRST_ERROR_CONTEXT_LINES = 2
# summary 에 넣는 첫 오류 줄 최대 길이
_SUMMARY_ERROR_MAX_CHARS = 200


def find_first_error(output: str) -> str | None:
    """빌드 출력 > 첫 컴파일 오류 줄(+ 들여쓴 문맥 최대 2줄). Dart 형식 우선, 없으면 일반 error: 줄, 둘 다 없으면 None"""
    lines = output.splitlines()
    for pattern in (_DART_COMPILE_ERROR, _GENERIC_ERROR):
        for index, line in enumerate(lines):
            if not pattern.search(line):
                continue
            picked = [line.rstrip()]
            # 바로 뒤 들여쓴 줄만 문맥으로 (빈 줄·다음 오류에서 멈춤)
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
    if not args.cmd:
        return out({"ok": False, "code": "cmd_required", "error": "--cmd is required"})

    # 기준은 **임시 파일을 만들기 전**의 상태여야 한다. run 직전에 뜨면 이미 만든 임시
    # 파일이 기준에 들어가, --cleanup 에서 빠뜨린 것이 남아도 흔적으로 안 잡힌다 (실측으로 짜 보다 발견).
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
    try:
        r = subprocess.run(["bash", "-lc", args.cmd], cwd=str(cwd), capture_output=True,
                           text=True, timeout=args.timeout, stdin=subprocess.DEVNULL)
        rc, output = r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired as e:
        rc = -1
        output = ((e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes)
                  else (e.stdout or "")) + f"\n[time limit of {args.timeout}s exceeded]"
    tail = "\n".join(output.splitlines()[-40:])

    collected: list[str] = []
    if rc == 0:
        shot_dir = shot_folder(root)
        for pattern in args.collect or []:
            for f in sorted(root.glob(pattern)):
                if f.is_file() and f.suffix.lower() in _RENDER_EXT and _inside(root, f):
                    dst = _unique(shot_dir / f.name)
                    shutil.move(str(f), str(dst))
                    collected.append(str(dst))

    # 실패해도 청소는 한다 — 임시 테스트 파일이 남으면 그것이 곧 흔적이다
    removed, refused = _cleanup(root, args.cleanup)
    after = _git_status(root)
    residue = None
    if before is not None and after is not None:
        residue = [line for line in after if line not in before]
    if baseline_from == "snapshot":
        base_f.unlink(missing_ok=True)   # 한 번 쓰면 끝이다 — 낡은 기준으로 다음 렌더를 재지 않는다

    payload = {"exit_code": rc, "collected": collected, "removed": removed,
               "refused_cleanup": refused or None, "residue": residue,
               "git_checked": before is not None, "baseline": baseline_from}
    if rc != 0:
        first_error = find_first_error(output)
        summary = f"Render command failed (exit code {rc}) — cleaned up without collecting"
        if first_error:
            summary += f" · first error: {first_error.splitlines()[0][:_SUMMARY_ERROR_MAX_CHARS]}"
        # first_error 를 앞쪽 키로 — 긴 output_tail 보다 먼저 읽히게
        payload = {"ok": False, "code": "render_failed", "summary": summary,
                   "first_error": first_error, **payload, "output_tail": tail,
                   "next": ("Fix first_error first (for a missing import, see the recipe's imports). "
                            if first_error else "Read output_tail and fix the render code. ")
                           + "Check the recipe's pitfalls table first"}
    elif residue:
        # 지우지 않는다 — 다른 세션의 변경일 수 있다
        payload.update({"ok": False, "code": "residue",
                        "summary": f"Render left {len(residue)} leftover path(s) in the repo",
                        "next": "Check the leftover paths: if you created them, add them to --cleanup and run again, or delete them yourself. "
                                "Leave changes you do not recognize alone"})
    elif not collected:
        payload.update({"ok": False, "code": "nothing_collected",
                        "summary": "The command succeeded but no images were collected",
                        "next": "Check that the --collect glob matches the render output paths (relative to the repo root)"})
    else:
        payload.update({"summary": f"Collected {len(collected)} image(s) · no leftovers"
                                   + ("" if before is not None else " (not a git repo, so leftovers were not checked)"),
                        "next": "Open them with Read. Shrink them with shrink before attaching to an issue"})
    if refused:
        payload["warning"] = f"Not deleted because outside the repo: {', '.join(refused)}"
    return out(payload)


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
                "next": "Now write the temporary render code and call render run"})


def configure_render(p) -> None:
    p.add_argument("action", choices=["snapshot", "run"],
                   help="snapshot: take the leftover-check baseline **before** creating temporary files · run: run and collect")
    p.add_argument("--cmd", default=None, help="run: render command (runs the temporary test the agent wrote)")
    p.add_argument("--collect", action="append", default=None,
                   help="Glob of images to collect (relative to the repo root, repeatable). e.g. client/test/_launch_render/**/*.png")
    p.add_argument("--cleanup", action="append", default=None,
                   help="Path to delete afterwards (inside the repo only, repeatable). Temporary test files and folders")
    p.add_argument("--cwd", default=None, help="Where to run the command (relative to the repo root, e.g. client)")
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--root", default=".", help="Target repo root — the base for the leftover check")


COMMANDS = [
    Command(name="render", help="Run a render command, collect images and check for leftovers", run=cmd_render,
            configure=configure_render),
]
