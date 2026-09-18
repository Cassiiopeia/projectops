"""e2e_cli 단위 테스트.

**리팩터 전에 현재 동작을 고정하기 위한 것이다** (이슈 #586).

앱·웹·서버 타겟 어댑터를 넣으려고 1442줄을 뜯는데, 지금 테스트가 하나도 없어서
기존 앱 E2E가 조용히 깨져도 알 방법이 없었다. 특히 아래 넷은 이미 잘 돌고 있는
순수 로직이라 손대는 순간 티 없이 망가진다.

  - 시나리오 전제 상속 · 순환 참조 거부
  - 기대 결과 없는 단계 거부 (이게 없으면 "화면이 떴으니 통과"로 끝난다)
  - 비밀값 탐지·마스킹 (테스트 계정·토큰이 산출물로 새는 것을 막는 유일한 방어)
  - 산출물 폴더 .gitignore 보장

기기·브라우저·서버가 없어도 돌아야 한다 — CI에서 실행하려면 네트워크와 SDK에
기대면 안 된다.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

CLI = Path(__file__).resolve().parents[1] / "scripts" / "e2e_cli.py"
sys.path.insert(0, str(CLI.parent))

import e2e_cli  # noqa: E402


def run_cli(*args):
    import os
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, str(CLI), *args],
                       capture_output=True, text=True, encoding="utf-8", env=env)
    return r.returncode, r.stdout or "", r.stderr or ""


def _write(d: Path, name: str, data: dict) -> Path:
    f = d / f"{name}.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return f


def _step(**over):
    """검증을 통과하는 최소 단계. 고쳐야 할 것만 넘긴다."""
    base = {"screen": "홈", "do": "버튼을 누른다", "expect_screen": "다음 화면"}
    base.update(over)
    return base


# ── 시나리오 검증 ────────────────────────────────────────────────────────

def test_validate_rejects_step_without_any_expectation():
    """기대 결과가 하나도 없으면 막는다.

    이걸 통과시키면 "화면이 떴으니 통과"로 끝나고, 서버에 아무것도 안 들어가 있어도 모른다.
    """
    problems = e2e_cli._validate({
        "name": "x",
        "steps": [{"screen": "홈", "do": "누른다"}],
    })
    assert any("기대 결과가 없습니다" in p for p in problems), problems


def test_validate_accepts_server_only_expectation():
    """화면 없이 서버만 확인하는 단계도 통과해야 한다 — 서버 타겟의 기반이다."""
    problems = e2e_cli._validate({
        "name": "x",
        "steps": [{"screen": "-", "do": "POST /api/x", "expect_server": "select 1"}],
    })
    assert problems == [], problems


def test_validate_rejects_empty_steps():
    problems = e2e_cli._validate({"name": "x", "steps": []})
    assert any("steps가 비었습니다" in p for p in problems), problems


def test_validate_rejects_missing_name():
    problems = e2e_cli._validate({"steps": [_step()]})
    assert any("name이 비었습니다" in p for p in problems), problems


# ── 전제 상속 ────────────────────────────────────────────────────────────

def test_expand_prepends_precondition_steps():
    """전제의 단계가 앞에 붙고, 몇 개가 전제인지 표시된다."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        _write(d / "_shared", "login", {"name": "로그인", "steps": [_step(screen="로그인")]})
        f = _write(d / "flows", "main", {
            "name": "본작업", "precondition": "_shared/login",
            "steps": [_step(screen="본문")],
        })
        merged, problems = e2e_cli._expand(d, f)
        assert problems == []
        assert [s["screen"] for s in merged["steps"]] == ["로그인", "본문"]
        assert merged["_precondition_steps"] == 1


def test_expand_inherits_reset_from_precondition():
    """전제의 reset을 물려받는다 — 처음부터 다시 밟으려면 전제 것도 지워야 한다."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        _write(d / "_shared", "login", {
            "name": "로그인", "reset": ["앱 데이터 삭제"], "steps": [_step()]})
        f = _write(d / "flows", "main", {
            "name": "본작업", "precondition": "_shared/login", "steps": [_step()]})
        merged, _ = e2e_cli._expand(d, f)
        assert merged["reset"] == ["앱 데이터 삭제"]


def test_expand_detects_circular_precondition():
    """순환 참조는 무한 재귀로 죽지 않고 문제로 보고한다."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        _write(d / "flows", "a", {"name": "a", "precondition": "b", "steps": [_step()]})
        f = _write(d / "flows", "b", {"name": "b", "precondition": "a", "steps": [_step()]})
        _, problems = e2e_cli._expand(d, f)
        assert any("순환" in p for p in problems), problems


def test_expand_reports_missing_precondition():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        f = _write(d / "flows", "a", {
            "name": "a", "precondition": "없는것", "steps": [_step()]})
        _, problems = e2e_cli._expand(d, f)
        assert any("찾지 못했습니다" in p for p in problems), problems


def test_resolve_scenario_finds_in_subfolder():
    """이름만 줘도 하위 폴더까지 찾아준다."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        _write(d / "flows" / "guardian", "routine-create", {"name": "x", "steps": [_step()]})
        found = e2e_cli._resolve_scenario(d, "routine-create")
        assert found is not None and found.stem == "routine-create"


# ── 비밀값 방어 ──────────────────────────────────────────────────────────

def test_find_secrets_catches_credentials():
    """산출물에 계정·토큰이 섞여 나가는 것을 막는 유일한 방어다."""
    hits = e2e_cli._find_secrets(
        'password: "hunter2"\naccessToken: "eyJhbGciOiJIUzI1NiJ9.abc.def"')
    assert hits, "비밀값을 하나도 못 잡았다"


def test_find_secrets_quiet_on_clean_text():
    """평범한 문장에 오탐이 나면 경고가 소음이 되어 아무도 안 읽는다."""
    assert e2e_cli._find_secrets("홈 화면에서 버튼을 누른다") == []


def test_mask_hides_middle():
    masked = e2e_cli._mask("supersecretvalue")
    assert "supersecretvalue" not in masked
    assert "*" in masked


# ── 산출물 폴더 보호 ─────────────────────────────────────────────────────

def test_ensure_gitignore_creates_excluding_rule():
    """기본값은 '올리지 않는다' — 무엇이 생길지 미리 다 알 수 없기 때문이다."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "e2e"
        d.mkdir()
        e2e_cli._ensure_gitignore(d)
        lines = [l.strip() for l in (d / ".gitignore").read_text(encoding="utf-8").splitlines()]
        # 전부 제외가 기본. 주석이 앞에 오므로 줄 단위로 본다.
        assert "*" in lines, lines
        assert "!.gitignore" in lines, lines
        # 폴더 자체는 막지 않는다 — 막으면 git이 안을 들여다보지 않아
        # `!하위폴더/파일` 예외가 통하지 않는다 (#578에서 실제로 겪은 함정).
        assert "!*/" in lines, lines


def test_ensure_gitignore_keeps_handwritten_file():
    """손으로 고친 .gitignore는 덮지 않는다."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "e2e"
        d.mkdir()
        (d / ".gitignore").write_text("# 내가 쓴 것\n*.png\n", encoding="utf-8")
        e2e_cli._ensure_gitignore(d)
        assert "내가 쓴 것" in (d / ".gitignore").read_text(encoding="utf-8")


# ── CLI 계약 ─────────────────────────────────────────────────────────────

def test_help_lists_subcommands():
    rc, out, err = run_cli("--help")
    combined = out + err
    for cmd in ["detect", "devices", "doctor", "scenario", "bootstrap",
                "edges", "note", "backend", "shrink"]:
        assert cmd in combined, f"{cmd}가 --help에 없다"


def test_unknown_subcommand_does_not_crash():
    rc, out, err = run_cli("존재하지-않는-커맨드")
    assert rc != 0


# ── 지식 저장 위치 (이슈 #586) ───────────────────────────────────────────
#
# 쌓은 지식이 워크트리마다 사라지던 문제를 고친 부분이다. 여기가 깨지면 자가발전이
# 조용히 초기화되므로, 되돌아가지 않게 고정한다.

def _git_repo(tmp: Path, remote: str | None = None) -> Path:
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp)], check=True, capture_output=True)
    if remote:
        subprocess.run(["git", "-C", str(tmp), "remote", "add", "origin", remote],
                       check=True, capture_output=True)
    return tmp


def test_repo_key_uses_remote_not_path():
    """워크트리마다 경로가 달라도 같은 프로젝트면 같은 키여야 한다."""
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        ra = _git_repo(Path(a), "https://github.com/Twin-Fang/elum.git")
        rb = _git_repo(Path(b), "git@github.com:Twin-Fang/elum.git")
        # 경로도 다르고 remote 표기(https/ssh)도 다르지만 같은 저장소다
        assert e2e_cli._repo_key(ra) == e2e_cli._repo_key(rb) == "Twin-Fang__elum"


def test_repo_key_falls_back_to_folder_name():
    """remote가 없는 로컬 전용 저장소도 동작해야 한다."""
    with tempfile.TemporaryDirectory() as tmp:
        r = _git_repo(Path(tmp) / "local-only")
        (Path(tmp) / "local-only").mkdir(exist_ok=True)
        key = e2e_cli._repo_key(Path(tmp) / "local-only")
        assert key and "/" not in key


def test_home_dir_is_outside_project():
    """산출물이 프로젝트 안에 생기면 워크트리에서 다시 사라진다."""
    with tempfile.TemporaryDirectory() as tmp:
        r = _git_repo(Path(tmp), "https://github.com/o/r.git")
        home = e2e_cli._home_dir(r)
        assert str(home).startswith(str(Path.home()))
        assert str(r) not in str(home)


def test_migrate_moves_old_knowledge_to_home():
    """예전 위치에 쌓인 것이 홈으로 넘어와야 한다 — 13KB를 잃지 않는 경로다."""
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as home_tmp:
        r = _git_repo(Path(tmp), "https://github.com/o/r.git")
        old = r / "docs" / "testing" / "e2e"
        old.mkdir(parents=True)
        (old / "learned.json").write_text('{"pitfalls":["x"]}', encoding="utf-8")
        (old / ".gitignore").write_text("*\n", encoding="utf-8")
        (old / "flows").mkdir()

        home = Path(home_tmp) / "agent-test" / "o__r"
        note = e2e_cli._migrate_from_project(r, home)

        assert note and "learned.json" in note
        assert (home / "learned.json").exists(), "지식이 옮겨지지 않았다"
        assert (home / "flows").exists(), "폴더도 함께 옮겨야 한다"
        # 이동이지 복사가 아니다 — 두 곳에 남으면 어느 쪽이 최신인지 알 수 없다
        assert not (old / "learned.json").exists(), "원본이 남았다(복사가 됐다)"
        # 예전 위치를 막던 규칙은 따라갈 이유가 없다
        assert not (home / ".gitignore").exists()


def test_migrate_does_not_overwrite_newer_home():
    """홈에 이미 있으면 그쪽이 최신이다 — 덮어쓰면 쌓은 것이 날아간다."""
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as home_tmp:
        r = _git_repo(Path(tmp), "https://github.com/o/r.git")
        old = r / "docs" / "testing" / "e2e"
        old.mkdir(parents=True)
        (old / "learned.json").write_text('{"old":true}', encoding="utf-8")

        home = Path(home_tmp) / "agent-test" / "o__r"
        home.mkdir(parents=True)
        (home / "learned.json").write_text('{"new":true}', encoding="utf-8")

        e2e_cli._migrate_from_project(r, home)
        assert json.loads((home / "learned.json").read_text(encoding="utf-8")) == {"new": True}


def test_migrate_returns_none_when_nothing_to_move():
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as home_tmp:
        r = _git_repo(Path(tmp), "https://github.com/o/r.git")
        assert e2e_cli._migrate_from_project(r, Path(home_tmp) / "x") is None

