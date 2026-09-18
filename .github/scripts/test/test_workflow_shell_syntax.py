"""워크플로우 run: 본문 셸 문법 검사 (#597).

실사고: 테스트 앱 빌드가 `syntax error: unexpected end of file` 로 죽었다.

    cat << EOF > build-info.txt
    ...
    EOF                    ← 컬럼 0. 닫힌다

    if [ -n "$PR_NUMBER" ]; then
      cat << EOF >> build-info.txt
      ...
      EOF                  ← 컬럼 2. **안 닫힌다**
    fi

`<< EOF` 의 종료자는 **컬럼 0** 이어야 한다. if 블록 안에 두면 자연스럽게 들여쓰게 되고,
그러면 셸이 종료자를 못 찾아 스크립트 끝까지 읽는다. `<<-` 로 바꿔도 **탭만** 허용하므로
공백 들여쓰기는 여전히 안 닫힌다.

더 나쁜 것은 **이 경로가 이슈 댓글로 트리거할 때만 탄다**는 점이었다. 게다가 그보다 앞선
스텝이 권한 문제(#595)로 먼저 죽어 여기까지 오지도 못했다. 사람이 눈으로 볼 수 있는
지점이 아니었다.

`${{ }}` 를 더미 값으로 치환한 뒤 `bash -n` 을 돌리면 머지 전에 잡힌다.
"""
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WF = ROOT / ".github" / "workflows"

# 러너가 실행 전에 치환하는 자리. 그대로 두면 bash 가 읽지 못한다.
_EXPR = re.compile(r"\$\{\{[^}]*\}\}")
# bash 가 아닌 셸로 도는 스텝은 대상이 아니다
_BASH = ("bash", "sh")


def _shell_steps():
    """(파일, job, step 이름, 본문) — bash 로 도는 run: 스텝 전부."""
    out = []
    for f in sorted(list(WF.rglob("*.yaml")) + list(WF.rglob("*.yml"))):
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue                      # YAML 자체 검증은 다른 테스트의 몫
        for jname, job in (doc.get("jobs") or {}).items():
            job = job or {}
            job_shell = ((job.get("defaults") or {}).get("run") or {}).get("shell")
            for st in job.get("steps") or []:
                if not isinstance(st, dict) or not isinstance(st.get("run"), str):
                    continue
                shell = st.get("shell") or job_shell
                if shell and not shell.startswith(_BASH):
                    continue
                out.append((f, jname, st.get("name") or "(이름 없음)", st["run"]))
    return out


STEPS = _shell_steps()


def test_there_are_shell_steps_to_check():
    """대상을 하나도 못 찾으면 이 테스트는 조용히 아무것도 검사하지 않는다."""
    assert len(STEPS) > 50, f"run: 스텝을 {len(STEPS)}개만 찾았다 — 수집이 깨졌다"


@pytest.mark.parametrize(
    "path,job,step,body", STEPS,
    ids=[f"{f.name}:{s}" for f, _, s, _ in STEPS])
def test_run_body_is_valid_bash(path, job, step, body):
    r = subprocess.run(["bash", "-n"], input=_EXPR.sub("X", body),
                       capture_output=True, text=True)
    assert r.returncode == 0, (
        f"{path.relative_to(WF)} · job={job} · step={step}\n"
        f"{r.stderr.strip()}\n"
        "heredoc 이면 종료자가 컬럼 0 인지 보라. if 블록 안이라면 heredoc 대신 "
        "`{ echo ...; } > 파일` 을 쓴다."
    )
