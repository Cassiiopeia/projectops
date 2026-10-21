"""`get-output-path` — 이번 실행의 산출물 자리와 env.sh."""
from __future__ import annotations

import os
from pathlib import Path

from pro_launch.registry import Command
from pro_launch.runtime.app_identity import detected_app_package
from pro_launch.runtime.context import project_root
from pro_launch.runtime.devices import load_devices, save_devices
from pro_launch.runtime.envfile import write_env_sh
from pro_launch.runtime.output import out
from pro_launch.runtime.shots import record_last_run


def cmd_output_path(args) -> int:
    """이번 실행의 산출물 자리를 만들고 알려준다.

    부르는 작업 스킬이 자기 폴더에 받고 싶으면 --skill 로 자기 id 를 넘긴다
    (design-brief 는 --skill design-brief). **증거를 내는 스킬만 받는다** — 문서 스킬 폴더에
    캡처를 쌓으면 추적 제외가 없어 저장소에 커밋된다.
    """
    try:
        from common.paths import EVIDENCE_SKILLS, resolve_output_path
    except ImportError:
        return out({"ok": False, "code": "common_not_found",
                    "error": "scripts/common/paths.py not found",
                    "hint": "Check that the projectops installation is complete"})
    # --root 가 가리키는 저장소 기준으로 자리를 계산한다. 없는 경로는 조용히 무시하지 않는다 (#713)
    if args.root and args.root != ".":
        root_dir = Path(args.root).expanduser()
        if not root_dir.is_dir():
            return out({"ok": False, "code": "not_found",
                        "error": f"--root path does not exist: {root_dir}"})
        os.chdir(root_dir)
    else:
        # 레포 밖에서 불려도 $PROJECT_ROOT·최근에 쓴 루트 기준으로 자리를 잡는다 (#885) — 아니면 git_not_found
        resolved = project_root(args)
        if resolved.is_dir() and resolved != Path.cwd().resolve():
            os.chdir(resolved)
    skill = args.skill or "launch"
    if skill not in EVIDENCE_SKILLS:
        return out({"ok": False, "code": "not_evidence_skill",
                    "error": f"'{skill}' is not registered as an evidence skill",
                    "hint": ("Add it to EVIDENCE_SKILLS in scripts/common/paths.py so the folder gets "
                             "a tracking exclusion. Registered: " + ", ".join(sorted(EVIDENCE_SKILLS)))})

    r = resolve_output_path(skill, args.title)
    if r.get("ok") is False:
        return out(r)
    md = Path(r["path"])        # <우산>/<skill>/{날짜}_{번호}_{제목}.md
    run_dir = md.parent / md.stem
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return out({"ok": False, "code": "mkdir_failed", "error": str(e)})

    root = project_root(args)
    known = load_devices(root)
    package, package_changed = _resolve_package(args.package, known["package"], root)
    if package and package != known["package"]:
        save_devices(root, package, known["bindings"])
    env = write_env_sh(run_dir, package, known["bindings"], skill=skill)
    # env.sh 를 안 부른 Bash 호출의 캡처도 이 실행 폴더로 오게 (#931)
    record_last_run(root, run_dir, run_dir / "screenshots")
    state = r.get("gitignore")
    return out({
        "skill": skill, "run": md.stem, "run_dir": str(run_dir),
        "screenshots": str(run_dir / "screenshots"), "env_file": str(env),
        "output_root": r.get("output_root"), "gitignore": state,
        "mismatch": r.get("mismatch"), "package": package,
        **({"package_changed": package_changed} if package_changed else {}),
        "summary": f"Output location {run_dir} (git exclusion {state})",
        "next": f'source "{env}" to load SHOT_DIR. Put all captures and evidence under it',
    })


def _resolve_package(given: str | None, stored: str | None, root: Path) -> tuple[str | None, str | None]:
    """앱 패키지: --package > 프로젝트 파일(applicationId·bundle id) > devices.json 저장값.

    저장값이 프로젝트 파일과 다르면 프로젝트 파일이 이긴다 — 옛 패키지로 env.sh 를 쓴 적이 있다 (#931).
    > (패키지, 바뀌었으면 "옛 -> 새")
    """
    if given:
        return given, None
    detected = detected_app_package(root)
    if detected and stored and detected != stored:
        return detected, f"{stored} -> {detected}"
    return stored or detected, None


def configure_get_output_path(p) -> None:
    p.add_argument("--skill", default=None,
                   help="Skill id to get a location for (default launch). Evidence skills only")
    p.add_argument("--title", default=None, help="Title. Defaults to one derived from the worktree path or branch name")
    p.add_argument("--package", default=None, help="App package name — written to env.sh as PKG")
    p.add_argument("--root", default=".")


COMMANDS = [
    Command(name="get-output-path", help="Output location for this run + env.sh", run=cmd_output_path,
            configure=configure_get_output_path),
]
