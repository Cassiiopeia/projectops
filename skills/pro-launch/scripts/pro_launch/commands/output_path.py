"""`get-output-path` — 이번 실행의 산출물 자리와 env.sh."""
from __future__ import annotations

import os
from pathlib import Path

from pro_launch.registry import Command
from pro_launch.runtime.context import project_root
from pro_launch.runtime.devices import load_devices, save_devices
from pro_launch.runtime.envfile import write_env_sh
from pro_launch.runtime.output import out


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
                    "error": "scripts/common/paths.py 를 찾지 못했습니다",
                    "hint": "projectops 설치가 온전한지 확인하세요"})
    # --root 가 가리키는 저장소 기준으로 자리를 계산한다. 없는 경로는 조용히 무시하지 않는다 (#713)
    if args.root and args.root != ".":
        root_dir = Path(args.root).expanduser()
        if not root_dir.is_dir():
            return out({"ok": False, "code": "not_found",
                        "error": f"--root 경로가 없습니다: {root_dir}"})
        os.chdir(root_dir)
    skill = args.skill or "launch"
    if skill not in EVIDENCE_SKILLS:
        return out({"ok": False, "code": "not_evidence_skill",
                    "error": f"'{skill}' 은 증거 스킬로 등록돼 있지 않습니다",
                    "hint": ("scripts/common/paths.py 의 EVIDENCE_SKILLS 에 넣어야 폴더에 "
                             "추적 제외가 심깁니다. 등록된 것: " + ", ".join(sorted(EVIDENCE_SKILLS)))})

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
    package = args.package or known["package"]
    if package and package != known["package"]:
        save_devices(root, package, known["bindings"])
    env = write_env_sh(run_dir, package, known["bindings"], skill=skill)
    state = r.get("gitignore")
    return out({
        "skill": skill, "run": md.stem, "run_dir": str(run_dir),
        "screenshots": str(run_dir / "screenshots"), "env_file": str(env),
        "output_root": r.get("output_root"), "gitignore": state,
        "mismatch": r.get("mismatch"),
        "summary": f"산출물 자리 {run_dir} (추적 제외 {state})",
        "next": f'source "{env}" 로 SHOT_DIR 을 불러 쓰세요. 캡처·증거는 전부 그 아래에 둡니다',
    })


def configure_get_output_path(p) -> None:
    p.add_argument("--skill", default=None,
                   help="자리를 받을 작업 스킬 id (기본 launch). 증거 스킬만 된다")
    p.add_argument("--title", default=None, help="제목. 없으면 워크트리 경로·브랜치명에서 뽑는다")
    p.add_argument("--package", default=None, help="앱 패키지명 — env.sh 에 PKG 로 넣는다")
    p.add_argument("--root", default=".")


COMMANDS = [
    Command(name="get-output-path", help="이번 실행의 산출물 자리 + env.sh", run=cmd_output_path,
            configure=configure_get_output_path),
]
