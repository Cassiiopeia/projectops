"""`render` — 코드로 상태를 그려 찍는다 (실행 · 수집 · 청소 · 흔적 검사)."""
from __future__ import annotations

import json
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


_RENDER_BASE = "render-baseline.json"


def _baseline_path(root: Path) -> Path:
    return state_home(root) / _RENDER_BASE


def cmd_render(args) -> int:
    root = project_root(args)
    if args.action == "snapshot":
        return _render_snapshot(root)
    if not args.cmd:
        return out({"ok": False, "code": "cmd_required", "error": "--cmd 가 필요합니다"})

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
                    "error": f"--cwd 폴더가 없습니다: {cwd}",
                    "next": "--cwd 는 레포 루트(--root) 기준 상대 경로다"})
    try:
        r = subprocess.run(["bash", "-lc", args.cmd], cwd=str(cwd), capture_output=True,
                           text=True, timeout=args.timeout, stdin=subprocess.DEVNULL)
        rc, output = r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired as e:
        rc = -1
        output = ((e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes)
                  else (e.stdout or "")) + f"\n[제한 시간 {args.timeout}초 초과]"
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
        payload.update({"ok": False, "code": "render_failed", "output_tail": tail,
                        "summary": f"렌더 명령 실패 (종료코드 {rc}) — 수집하지 않고 청소만 했다",
                        "next": "output_tail 을 읽고 렌더 코드를 고친다. 레시피의 함정 표를 먼저 본다"})
    elif residue:
        # 지우지 않는다 — 다른 세션의 변경일 수 있다
        payload.update({"ok": False, "code": "residue",
                        "summary": f"렌더 뒤 레포에 흔적 {len(residue)}건이 남았다",
                        "next": "남은 경로를 보고 네가 만든 것이면 --cleanup 에 넣어 다시 돌리거나 직접 지운다. "
                                "모르는 변경이면 건드리지 않는다"})
    elif not collected:
        payload.update({"ok": False, "code": "nothing_collected",
                        "summary": "명령은 성공했는데 모은 그림이 없다",
                        "next": "--collect 글롭이 렌더 결과 경로와 맞는지 본다 (레포 루트 기준)"})
    else:
        payload.update({"summary": f"{len(collected)}장 수집 · 흔적 없음"
                                   + ("" if before is not None else " (git 레포가 아니라 흔적 검사 못 함)"),
                        "next": "Read 로 열어 본다. 이슈에 붙일 거면 shrink 로 줄인다"})
    if refused:
        payload["warning"] = f"레포 밖이라 지우지 않은 경로: {', '.join(refused)}"
    return out(payload)


def _render_snapshot(root: Path) -> int:
    status = _git_status(root)
    if status is None:
        return out({"ok": False, "code": "not_git", "error": "git 레포가 아니라 흔적 검사 기준을 뜰 수 없습니다",
                    "hint": "그래도 render run 은 돈다 — 청소만 하고 흔적 검사는 건너뛴다"})
    f = _baseline_path(root)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"root": str(root), "status": status,
                             "at": time.strftime("%Y-%m-%d %H:%M:%S")}, ensure_ascii=False),
                 encoding="utf-8")
    return out({"baseline": str(f), "changed_now": len(status),
                "summary": f"기준을 떴다 (지금 바뀐 경로 {len(status)}건 — 이것들은 흔적으로 보지 않는다)",
                "next": "이제 임시 렌더 코드를 만들고 render run 을 부른다"})


def configure_render(p) -> None:
    p.add_argument("action", choices=["snapshot", "run"],
                   help="snapshot: 임시 파일을 만들기 **전에** 흔적 검사 기준을 뜬다 · run: 돌리고 모은다")
    p.add_argument("--cmd", default=None, help="run: 렌더 명령 (agent 가 짠 임시 테스트를 돌리는 것)")
    p.add_argument("--collect", action="append", default=None,
                   help="모을 그림 글롭 (레포 루트 기준, 여러 번). 예 client/test/_launch_render/**/*.png")
    p.add_argument("--cleanup", action="append", default=None,
                   help="끝나고 지울 경로 (레포 안만, 여러 번). 임시 테스트 파일·폴더")
    p.add_argument("--cwd", default=None, help="명령을 돌릴 곳 (레포 루트 기준, 예 client)")
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--root", default=".", help="대상 레포 루트 — 흔적 검사 기준")


COMMANDS = [
    Command(name="render", help="렌더 명령을 돌리고 그림을 모으고 흔적을 검사한다", run=cmd_render,
            configure=configure_render),
]
