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


# ── 타겟·모드 축 (이슈 #586) ─────────────────────────────────────────────

def test_old_scenario_without_axes_still_works():
    """기존 파일에는 target·mode가 없다. 한 글자도 안 고치고 돌아야 한다."""
    data = {"name": "예전 것", "steps": [_step()]}
    assert e2e_cli.scenario_target(data) == "app"
    assert e2e_cli.scenario_mode(data) == "e2e"
    assert e2e_cli._validate(data) == []


def test_unknown_target_is_rejected_not_defaulted():
    """오타를 기본값으로 삼키면 웹 시나리오가 adb를 타고 원인을 못 찾는다."""
    problems = e2e_cli._validate({"name": "x", "target": "wbe", "steps": [_step()]})
    assert any("target 'wbe'" in p for p in problems), problems


def test_web_target_accepts_url_expectation():
    """웹은 화면 이름 대신 URL·텍스트로 판정하는 경우가 많다."""
    assert e2e_cli._validate({
        "name": "x", "target": "web",
        "steps": [{"screen": "로그인", "do": "click #submit", "expect_url": "/home"}],
    }) == []


def test_server_target_accepts_status_only():
    """서버는 화면이 없다. 상태 코드만으로도 판정된다."""
    assert e2e_cli._validate({
        "name": "x", "target": "server",
        "steps": [{"screen": "-", "do": "POST /api/login", "expect_status": 200}],
    }) == []


def test_server_target_rejects_screen_only_expectation():
    """서버 시나리오에 expect_screen만 있으면 판정할 수 없다 — 화면이 없다."""
    problems = e2e_cli._validate({
        "name": "x", "target": "server",
        "steps": [{"screen": "-", "do": "POST /api/x", "expect_screen": "홈"}],
    })
    assert any("기대 결과가 없습니다" in p for p in problems), problems


def test_load_mode_is_reserved_not_silently_accepted():
    """축만 예약한 상태다. 밟다가 중간에 멈추는 것보다 먼저 말해 준다."""
    problems = e2e_cli._validate({
        "name": "x", "target": "server", "mode": "load",
        "steps": [{"screen": "-", "do": "POST /api/x", "expect_status": 200}],
    })
    assert any("아직 구현되지 않았습니다" in p for p in problems), problems


def test_load_mode_only_makes_sense_on_server():
    """UI로는 부하를 걸 수 없다."""
    problems = e2e_cli._validate({
        "name": "x", "target": "app", "mode": "load", "steps": [_step()]})
    assert any("server 타겟에서만" in p for p in problems), problems


# ── 타겟 감지 (이슈 #586) ────────────────────────────────────────────────

def test_version_yml_wins_over_markers():
    """projectops가 통합된 레포는 이미 답을 갖고 있다 — 추론보다 신뢰할 수 있다."""
    with tempfile.TemporaryDirectory() as tmp:
        r = Path(tmp)
        (r / "version.yml").write_text(
            "metadata:\n  project_types:\n    - flutter\n    - spring\n", encoding="utf-8")
        (r / "package.json").write_text('{"dependencies":{"react":"18"}}', encoding="utf-8")
        det = e2e_cli.detect_targets(r)
        assert det["source"] == "version.yml"
        assert det["targets"] == ["app", "server"], det


def test_markers_used_when_no_version_yml():
    """남의 프로젝트에는 version.yml이 없다. 파일로 추론해야 한다."""
    with tempfile.TemporaryDirectory() as tmp:
        r = Path(tmp)
        (r / "package.json").write_text('{"dependencies":{"next":"14"}}', encoding="utf-8")
        det = e2e_cli.detect_targets(r)
        assert det["source"] == "marker"
        assert "web" in det["targets"], det


def test_flutter_android_gradle_is_not_mistaken_for_server():
    """Flutter 앱의 android/build.gradle을 서버로 잡으면 엉뚱한 것을 밟는다."""
    with tempfile.TemporaryDirectory() as tmp:
        r = Path(tmp)
        (r / "pubspec.yaml").write_text("name: x\ndependencies:\n  flutter:\n", encoding="utf-8")
        (r / "android").mkdir()
        (r / "android" / "build.gradle").write_text("// app", encoding="utf-8")
        det = e2e_cli.detect_targets(r)
        assert det["targets"] == ["app"], det


def test_unknown_project_reports_none_not_crash():
    """무엇인지 몰라도 죽지 않는다 — 사용자가 직접 지정할 수 있어야 한다."""
    with tempfile.TemporaryDirectory() as tmp:
        det = e2e_cli.detect_targets(Path(tmp))
        assert det["targets"] == []
        assert det["source"] == "none"


def test_detect_does_not_fail_without_flutter():
    """예전에는 pubspec이 없으면 첫 명령부터 실패했다 — 웹·서버 레포가 막혔다."""
    with tempfile.TemporaryDirectory() as tmp:
        r = _git_repo(Path(tmp), "https://github.com/o/r.git")
        (r / "package.json").write_text('{"dependencies":{"express":"4"}}', encoding="utf-8")
        rc, out, err = run_cli("detect", "--path", str(r))
        data = json.loads(out)
        assert data.get("ok") is not False, data
        assert "server" in data["targets"], data


def test_detect_rejects_unknown_target_option():
    with tempfile.TemporaryDirectory() as tmp:
        rc, out, err = run_cli("detect", "--path", tmp, "--target", "wbe")
        data = json.loads(out)
        assert data["ok"] is False and data["code"] == "unknown_target"


# ── 서버 타겟: API 시퀀스 (이슈 #586) ────────────────────────────────────

def test_parse_do_reads_method_path_body():
    m, path, body = e2e_cli._parse_do('POST /api/login {"id": "a"}')
    assert (m, path, body) == ("POST", "/api/login", {"id": "a"})


def test_parse_do_without_body():
    assert e2e_cli._parse_do("GET /api/me")[:2] == ("GET", "/api/me")


def test_parse_do_rejects_garbage():
    """읽을 수 없는 단계를 그냥 보내면 무엇이 잘못됐는지 알 수 없다."""
    try:
        e2e_cli._parse_do("아무 말")
        assert False, "거절했어야 한다"
    except ValueError as e:
        assert "형식" in str(e)


def test_fill_substitutes_saved_values():
    """토큰 체이닝의 핵심 — 앞 응답의 값이 다음 요청에 들어간다."""
    out = e2e_cli._fill({"h": "Bearer {token}", "n": [1, "{token}"]}, {"token": "abc"})
    assert out == {"h": "Bearer abc", "n": [1, "abc"]}


def test_fill_reports_missing_key():
    """없는 값을 조용히 빈 문자열로 채우면 401만 받고 원인을 모른다."""
    try:
        e2e_cli._fill("Bearer {nope}", {})
        assert False, "거절했어야 한다"
    except ValueError as e:
        assert "nope" in str(e)


def test_jsonpath_reads_nested_and_array():
    data = {"a": {"b": [{"c": "값"}]}}
    assert e2e_cli._jsonpath(data, "$.a.b[0].c") == "값"
    assert e2e_cli._jsonpath(data, "$.a.missing") is None


def test_api_walks_scenario_with_token_chaining():
    """실제 HTTP 서버를 띄워 끝까지 밟는다 — 체이닝이 진짜 되는지는 이걸로만 안다."""
    import http.server
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):  # 테스트 출력을 더럽히지 않는다
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if self.path == "/api/login":
                payload, code = {"accessToken": "TKN-1"}, 200
            elif self.path == "/api/items":
                # 토큰이 실제로 실려 왔는지 본다
                ok = self.headers.get("Authorization") == "Bearer TKN-1"
                payload, code = ({"id": 7}, 201) if ok else ({"error": "no token"}, 401)
            else:
                payload, code = {"error": "not found"}, 404
            raw = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    try:
        with tempfile.TemporaryDirectory() as tmp:
            r = _git_repo(Path(tmp), "https://github.com/o/apiprobe.git")
            home = e2e_cli._home_dir(r)
            _write(home / "flows", "login-create", {
                "name": "가입 후 생성", "target": "server", "mode": "e2e",
                "steps": [
                    {"screen": "-", "do": 'POST /api/login {"id":"a"}',
                     "expect_status": 200, "save": {"token": "$.accessToken"}},
                    {"screen": "-", "do": 'POST /api/items {"n":"x"}',
                     "auth": "{token}", "expect_status": 201},
                ],
            })
            try:
                rc, out, err = run_cli("api", "--name", "login-create",
                                       "--root", str(r), "--base-url", base)
                data = json.loads(out)
                assert data["ok"] is True, data
                assert len(data["steps"]) == 2, data
                # 두 번째가 201이면 토큰이 실제로 실려 갔다는 뜻이다
                assert data["steps"][1]["http_status"] == 201, data["steps"][1]
                assert data["saved_keys"] == ["token"], data
            finally:
                import shutil as _sh
                _sh.rmtree(home, ignore_errors=True)
    finally:
        srv.shutdown()


def test_api_refuses_non_server_scenario():
    """앱 시나리오를 api로 밟으면 엉뚱한 것을 보낸다."""
    with tempfile.TemporaryDirectory() as tmp:
        r = _git_repo(Path(tmp), "https://github.com/o/apiprobe2.git")
        home = e2e_cli._home_dir(r)
        _write(home / "flows", "app-one", {"name": "앱", "steps": [_step()]})
        try:
            rc, out, err = run_cli("api", "--name", "app-one", "--root", str(r),
                                   "--base-url", "http://127.0.0.1:1")
            data = json.loads(out)
            assert data["ok"] is False and data["code"] == "wrong_target", data
        finally:
            import shutil as _sh
            _sh.rmtree(home, ignore_errors=True)


# ── 웹 타겟 (이슈 #586) ──────────────────────────────────────────────────
#
# 실제 브라우저 조작은 Playwright가 필요해 여기서 돌리지 않는다. Playwright가 없어도
# **막힌 이유가 정확히 전달되는지**는 확인할 수 있고, 그게 CI에서 지킬 수 있는 선이다.

def test_web_reports_missing_playwright_with_install_hint():
    """무엇을 깔아야 하는지 말해주지 않으면 사용자는 여기서 멈춘다."""
    ok, err = e2e_cli._require_playwright()
    if ok is not None:
        import pytest
        pytest.skip("이 환경에는 Playwright가 설치돼 있다")
    assert err["code"] == "playwright_missing"
    assert "pip install playwright" in err["install"]


def test_web_action_without_open_browser_is_refused():
    """브라우저를 열지 않고 클릭하면 무엇을 해야 하는지 알려줘야 한다."""
    with tempfile.TemporaryDirectory() as tmp:
        r = _git_repo(Path(tmp), "https://github.com/o/webprobe.git")
        home = e2e_cli._home_dir(r)
        home.mkdir(parents=True, exist_ok=True)
        try:
            rc, out, err = run_cli("web", "click", "--root", str(r), "--selector", "#x")
            data = json.loads(out)
            assert data["ok"] is False
            # Playwright가 없는 환경이면 그 안내가, 있으면 "브라우저 안 열림"이 나온다
            assert data["code"] in ("browser_not_open", "playwright_missing"), data
        finally:
            import shutil as _sh
            _sh.rmtree(home, ignore_errors=True)


def test_web_state_path_lives_with_knowledge():
    """브라우저 상태도 홈에 둔다 — 워크트리를 오가도 같은 세션을 본다."""
    with tempfile.TemporaryDirectory() as tmp:
        r = _git_repo(Path(tmp), "https://github.com/o/webprobe2.git")
        sp = e2e_cli._web_state_path(r)
        assert str(sp).startswith(str(Path.home()))
        assert sp.parent == e2e_cli._home_dir(r)


def test_web_help_lists_all_actions():
    rc, out, err = run_cli("web", "--help")
    combined = out + err
    for a in ["open", "goto", "click", "type", "shot", "assert", "console", "close"]:
        assert a in combined, f"{a}가 --help에 없다"


def test_web_setup_is_listed_as_action():
    """설치까지가 스킬의 역할이다 — 안내만 하고 세워 두지 않는다."""
    rc, out, err = run_cli("web", "--help")
    assert "setup" in (out + err)


def test_web_missing_playwright_offers_to_install():
    """막혔을 때 '무엇을 물어볼지'까지 있어야 agent가 사용자에게 제안할 수 있다."""
    ok, err = e2e_cli._require_playwright()
    if ok is not None:
        import pytest
        pytest.skip("이 환경에는 Playwright가 있다")
    assert err["fix"].startswith("web setup")
    assert "설치할까요" in err["ask_user"]


def test_web_walks_real_browser():
    """실제 브라우저를 열어 끝까지 밟는다.

    **호출이 쪼개져도 같은 브라우저에 붙는지**가 이 설계의 전부다. launch()로 띄우면
    드라이버가 죽을 때 브라우저도 죽어 두 번째 호출이 붙을 곳이 없다 — 실측으로 겪었고,
    그래서 브라우저를 독립 프로세스로 띄운다. 그 계약이 깨지면 여기서 잡힌다.
    """
    ok, _ = e2e_cli._require_playwright()
    if ok is None:
        import pytest
        pytest.skip("Playwright 없음 — web setup 후 실행된다")

    import http.server
    import threading

    html = (b'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            b'<title>t</title></head><body><input id="v">'
            b'<button id="go" onclick="document.getElementById(\'out\').textContent='
            b'document.getElementById(\'v\').value">go</button>'
            b'<p id="out"></p></body></html>')

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/"

    with tempfile.TemporaryDirectory() as tmp:
        r = _git_repo(Path(tmp), "https://github.com/o/webwalk.git")
        home = e2e_cli._home_dir(r)
        try:
            rc, out, _ = run_cli("web", "open", "--root", str(r), "--url", url)
            assert json.loads(out).get("ok") is not False, out

            rc, out, _ = run_cli("web", "type", "--root", str(r),
                                 "--selector", "#v", "--text", "남아야 한다")
            assert json.loads(out).get("ok") is not False, out

            rc, out, _ = run_cli("web", "click", "--root", str(r), "--selector", "#go")
            assert json.loads(out).get("ok") is not False, out

            # 세 번의 별개 호출을 거쳐도 입력이 살아 있어야 한다
            rc, out, _ = run_cli("web", "assert", "--root", str(r), "--text", "남아야 한다")
            data = json.loads(out)
            assert data["ok"] is True, data
        finally:
            run_cli("web", "close", "--root", str(r))
            srv.shutdown()
            import shutil as _sh
            _sh.rmtree(home, ignore_errors=True)


# ── bootstrap·edges 타겟 분기 (이슈 #586) ────────────────────────────────

def test_scan_server_finds_endpoints_across_frameworks():
    """서버 시나리오는 엔드포인트 목록에서 시작한다."""
    with tempfile.TemporaryDirectory() as tmp:
        r = Path(tmp)
        (r / "src").mkdir()
        (r / "src" / "a.js").write_text(
            "router.post('/api/auth/login', h);\nrouter.get('/api/routines', h);\n",
            encoding="utf-8")
        (r / "src" / "B.java").write_text(
            '@GetMapping("/api/member/me")\npublic X me() {}\n', encoding="utf-8")
        eps = e2e_cli._scan_server(r)["endpoints"]
        paths = {(e["method"], e["path"]) for e in eps}
        assert ("POST", "/api/auth/login") in paths, eps
        assert ("GET", "/api/routines") in paths, eps
        assert ("GET", "/api/member/me") in paths, eps


def test_scan_web_finds_routes():
    with tempfile.TemporaryDirectory() as tmp:
        r = Path(tmp)
        (r / "src").mkdir()
        (r / "src" / "router.ts").write_text(
            "const routes=[{path:'/login'},{path:'/home'}]", encoding="utf-8")
        got = {x["path"] for x in e2e_cli._scan_web(r)["routes"]}
        assert {"/login", "/home"} <= got, got


def test_bootstrap_on_server_project_does_not_demand_flutter():
    """앱이 아니어도 폴더와 지도를 만들어야 한다 — 예전에는 여기서 막혔다."""
    with tempfile.TemporaryDirectory() as tmp:
        r = _git_repo(Path(tmp), "https://github.com/o/bsrv.git")
        (r / "package.json").write_text('{"dependencies":{"express":"4"}}', encoding="utf-8")
        (r / "src").mkdir()
        (r / "src" / "a.js").write_text("router.get('/api/items', h);", encoding="utf-8")
        home = e2e_cli._home_dir(r)
        try:
            rc, out, err = run_cli("bootstrap", "--path", str(r))
            data = json.loads(out)
            assert data.get("ok") is not False, data
            assert data["target"] == "server", data
            assert "items" in data["feature_groups"], data
        finally:
            import shutil as _sh
            _sh.rmtree(home, ignore_errors=True)


def test_edges_on_server_project_scans_js():
    """앱의 lib/*.dart만 훑으면 웹·서버에서는 아무것도 못 준다."""
    with tempfile.TemporaryDirectory() as tmp:
        r = _git_repo(Path(tmp), "https://github.com/o/esrv.git")
        (r / "package.json").write_text('{"dependencies":{"express":"4"}}', encoding="utf-8")
        (r / "src").mkdir()
        (r / "src" / "a.js").write_text(
            "try { x(); } catch (e) { res.status(500); }\n", encoding="utf-8")
        rc, out, err = run_cli("edges", "--path", str(r))
        data = json.loads(out)
        assert data.get("ok") is not False, data
        assert data["scanned_files"] >= 1, data


def test_edges_hints_target_when_flutter_missing():
    """막혔을 때 무엇을 하면 되는지 알려줘야 한다."""
    with tempfile.TemporaryDirectory() as tmp:
        r = _git_repo(Path(tmp), "https://github.com/o/nohint.git")
        rc, out, err = run_cli("edges", "--path", str(r), "--target", "app")
        data = json.loads(out)
        assert data["ok"] is False
        assert "--target" in (data.get("hint") or ""), data

