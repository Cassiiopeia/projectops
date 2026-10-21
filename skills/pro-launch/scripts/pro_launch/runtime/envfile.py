"""`env.sh` 쓰기 — 실행 환경 변수(RUN_DIR·SHOT_DIR·DEV·PKG)를 쓰는 곳은 여기 하나뿐이다."""
from __future__ import annotations

import os
import re
from pathlib import Path

from pro_launch.runtime.devices import sole_device


def resolve_run_dir(args) -> Path | None:
    """env.sh 를 어디에 쓸지. **추측하지 않는다** — 최근 폴더를 골라 주면 틀렸을 때 조용하다."""
    v = getattr(args, "run_dir", None) or os.environ.get("RUN_DIR")
    return Path(v).resolve() if v else None


def _sh_quote(value: str) -> str:
    """셸에서 값이 그대로 쓰이도록 감싼다. 큰따옴표면 `$` 가 전개되어 **다른 값**이 된다."""
    return "'" + value.replace("'", "'\\''") + "'"


def _run_var(skill: str) -> str:
    """실행 이름을 담는 변수. launch → LAUNCH_RUN, agent-test → AGENT_TEST_RUN.

    공통 변수(RUN_DIR·SHOT_DIR·DEV·PKG)는 어느 스킬이 만들어도 같은 이름이다 —
    문서 예시 수십 곳이 그 이름에 기대고 있다.
    """
    return re.sub(r"[^A-Z0-9]+", "_", skill.upper()).strip("_") + "_RUN"


def write_env_sh(run_dir: Path, package: str | None,
                  bindings: list[dict] | None = None, skill: str | None = None) -> Path:
    """실행 환경을 쓴다. **이 파일을 쓰는 곳은 여기 하나뿐이다.**

    역할 이름을 **셸 변수명에 쓰지 않는다.** 한글·공백·하이픈이 든 이름은
    `export DEV_{이름}=...` 이 거부되고 `$DEV_{이름}` 은 조용히 엉뚱한 값이 된다.
    번호로 고정하고 이름은 값으로 담는다.
    """
    shots = run_dir / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    env = run_dir / "env.sh"
    # 스킬 이름을 모르면(device 가 나중에 다시 쓸 때) 처음 쓴 이름을 이어받는다
    if skill is None and env.is_file():
        m = re.search(r"^export ([A-Z0-9_]+_RUN)=", env.read_text(encoding="utf-8"), re.M)
        var = m.group(1) if m else _run_var("launch")
    else:
        var = _run_var(skill or "launch")

    lines = [
        "# 실행 환경 — `source env.sh` 로 불러 쓴다.",
        "# 경로를 손으로 짓지 않는다. 여기 없는 자리에는 아무것도 만들지 않는다.",
        "export %s=%s" % (var, _sh_quote(run_dir.name)),
        "export RUN_DIR=%s" % _sh_quote(str(run_dir)),
        "export SHOT_DIR=%s" % _sh_quote(str(shots)),
    ]
    if package:
        lines.append("export PKG=%s" % _sh_quote(package))

    bindings = bindings or []
    if bindings:
        lines += ["",
                  "# 역할 ↔ 기기. ROLE{n} 값은 시나리오 roles 의 키와 같은 문자열이다.",
                  "# 시나리오가 \"device\": \"B\" 라고 적으면 ROLE2==B 를 보고 $DEV2 를 쓴다.",
                  "export DEV_COUNT=%d" % len(bindings)]
        for n, b in enumerate(bindings, 1):
            note = b.get("note")
            tail = "   # %s" % note if note else ""
            lines.append("export ROLE%d=%s; export DEV%d=%s%s"
                         % (n, _sh_quote(b["role"]), n, _sh_quote(b["serial"]), tail))
        lines += ["", "# 역할을 쓰지 않는 명령의 기본 기기", 'export DEV="$DEV1"']
    else:
        # DEV 는 **반드시 정의한다.** 비어 있으면 `adb -s ` 가 되어 사용법 오류로 죽는다.
        # 다른 세션이 쥔 기기는 후보에서 뺀다 — 정해지지 않으면 비워 두고 acquire 를 안내한다 (#972)
        one = sole_device()
        lines += ["", "# 다른 세션이 쓰지 않는 기기가 한 대뿐이라 그것을 기본으로 둔다"
                      if one else
                      "# 기기를 정하지 않았다 (다른 세션 기기는 넣지 않는다). device acquire --platform ios|android 로"
                      "\n# 빌린 뒤 DEV=<받은 id> 로 쓰거나, device bind 로 역할을 잡으세요",
                  "export DEV=%s" % _sh_quote(one or "")]
    lines.append("")
    env.write_text("\n".join(lines), encoding="utf-8")
    return env
