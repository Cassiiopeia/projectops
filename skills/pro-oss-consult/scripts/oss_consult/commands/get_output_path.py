"""get-output-path: 컨설팅 보고서 저장 경로 (경로 규칙은 common/paths.py 단일 소유)
"""
from __future__ import annotations

import os
from pathlib import Path

from oss_consult.output import _fail, _out


def cmd_get_output_path(args) -> int:
    # 경로 규칙은 common/paths.py가 단일 소유 — 여기서 재구현하지 않는다 (#525)
    from common.paths import resolve_output_path
    cwd = getattr(args, "cwd", None)
    if cwd:
        if not Path(cwd).is_dir():
            return _fail("bad_args", f"--cwd 가 디렉터리가 아닙니다: {cwd}", "보고서를 둘 레포의 경로를 넘긴다")
        # 경로 계산은 cwd 의 git 루트 기준이다 — 스크립트 폴더가 아니라 작업 레포를 가리키게 한다
        os.chdir(cwd)
    res = resolve_output_path(args.skill_id, args.title)
    if not res.get("ok", True):
        res.setdefault("summary", res.get("error"))
        if not res.get("next"):
            res["next"] = "보고서를 둘 git 저장소 안에서 실행하거나 --cwd 로 그 저장소를 지정한다"
    elif not res.get("next"):
        res["next"] = "이 경로에 보고서를 저장한다 (저장 전 요약을 보여주고 승인받는다)"
    return _out(res)
