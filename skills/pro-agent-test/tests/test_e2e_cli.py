"""e2e_cli 단위 테스트.

**리팩터 전에 현재 동작을 고정하기 위한 것이다** (이슈 #586).

앱·웹·서버 타겟 어댑터를 넣으려고 1442줄을 뜯는데, 지금 테스트가 하나도 없어서
기존 앱 E2E가 조용히 깨져도 알 방법이 없었다. 특히 아래 넷은 이미 잘 돌고 있는
순수 로직이라 손대는 순간 티 없이 망가진다.

  - 시나리오 전제 상속 · 순환 참조 거부
  - 기대 결과 없는 단계 거부 (이게 없으면 "화면이 떴으니 통과"로 끝난다)
  - 비밀값 탐지·마스킹 (테스트 계정·토큰이 산출물로 새는 것을 막는 유일한 방어)

기기·브라우저·서버가 없어도 돌아야 한다 — CI에서 실행하려면 네트워크와 SDK에
기대면 안 된다.
"""
import contextlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

CLI = Path(__file__).resolve().parents[1] / "scripts" / "e2e_cli.py"
sys.path.insert(0, str(CLI.parent))

import e2e_cli  # noqa: E402


def run_cli(*args, home: Path | None = None):
    import os
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    # 기록은 홈에 쌓인다. 테스트가 사용자의 진짜 기록을 건드리면 안 된다.
    if home is not None:
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)   # Windows
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


def test_find_secrets_masks_what_it_reports():
    """찾았다고 알릴 때 원문을 그대로 실으면 방어의 의미가 없다."""
    hits = e2e_cli._find_secrets('password: "hunter2supersecret"')
    assert hits, "못 찾았다"
    joined = " ".join(hits)
    assert "hunter2supersecret" not in joined, joined
    assert "***" in joined, joined


# ── 산출물 폴더 보호 ─────────────────────────────────────────────────────

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


# ── 타겟 축 ─────────────────────────────────────────────────────────────

def test_scenario_without_target_defaults_to_app():
    """target 을 안 적으면 app 이다. 대부분의 시나리오가 앱이라 매번 적게 하지 않는다."""
    data = {"name": "x", "steps": [_step()]}
    assert e2e_cli.scenario_target(data) == "app"
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

# ── Playwright 없는 상태를 테스트가 직접 만든다 ──────────────────────────
#
# 아래 두 테스트가 보는 것은 **"못 찾았을 때 무슨 말을 해주나"** 뿐이다. 브라우저가
# 필요 없다. 그런데 설치 여부로 skip하게 두면 **깔려 있는 기계에서는 영영 안 돌아간다.**
# 실제로 그래서 옛 키(`install`)를 보는 테스트가 개발 기계에서는 계속 초록불이었고,
# Playwright가 없는 CI에서만 터졌다. 초록불이 "통과"가 아니라 "실행조차 안 됨"이었다.
#
# sys.modules에 None을 넣으면 import가 ImportError로 끝난다 — 설치 여부와 무관하게
# 없는 상태가 재현되므로 어디서 돌려도 같은 결과가 나온다.

@contextlib.contextmanager
def playwright_hidden():
    names = [k for k in sys.modules if k == "playwright" or k.startswith("playwright.")]
    saved = {k: sys.modules[k] for k in names}
    for k in names:
        del sys.modules[k]
    sys.modules["playwright"] = None
    sys.modules["playwright.sync_api"] = None
    try:
        yield
    finally:
        sys.modules.pop("playwright", None)
        sys.modules.pop("playwright.sync_api", None)
        sys.modules.update(saved)


def test_web_reports_missing_playwright_with_install_hint():
    """무엇을 깔아야 하는지 말해주지 않으면 사용자는 여기서 멈춘다."""
    with playwright_hidden():
        ok, err = e2e_cli._require_playwright()
    assert ok is None
    assert err["code"] == "playwright_missing"
    # 안내만 하지 않는다 — 스킬이 직접 까는 경로(fix)와 손으로 하는 법(manual)을 함께 준다
    assert err["fix"].startswith("web setup"), err
    assert "venv" in err["manual"], err
    assert "설치할까요" in err["ask_user"], err


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
    with playwright_hidden():
        ok, err = e2e_cli._require_playwright()
    assert ok is None
    assert err["fix"].startswith("web setup")
    assert "설치할까요" in err["ask_user"]


@pytest.mark.local_only
def test_web_walks_real_browser():
    """실제 브라우저를 열어 끝까지 밟는다.

    **호출이 쪼개져도 같은 브라우저에 붙는지**가 이 설계의 전부다. launch()로 띄우면
    드라이버가 죽을 때 브라우저도 죽어 두 번째 호출이 붙을 곳이 없다 — 실측으로 겪었고,
    그래서 브라우저를 독립 프로세스로 띄운다. 그 계약이 깨지면 여기서 잡힌다.
    """
    ok, _ = e2e_cli._require_playwright()
    if ok is None:
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

def test_access_refuses_raw_secret():
    """비밀번호 원문을 적으려 하면 막는다 — 값이 아니라 읽을 곳을 적어야 한다."""
    with tempfile.TemporaryDirectory() as tmp:
        r = _git_repo(Path(tmp), "https://github.com/o/acc.git")
        home = e2e_cli._home_dir(r)
        try:
            rc, out, _ = run_cli("access", "set", "--root", str(r), "--key", "db",
                                 "--json", '{"password": "hunter2supersecret"}')
            data = json.loads(out)
            assert data["ok"] is False and data["code"] == "secret_in_value", data
            assert "password_env" in data["hint"], data
        finally:
            import shutil as _sh
            _sh.rmtree(home, ignore_errors=True)


def test_access_roundtrip():
    """적어 두고 꺼내 쓰는 것이 이 기록의 전부다."""
    with tempfile.TemporaryDirectory() as tmp:
        r = _git_repo(Path(tmp), "https://github.com/o/acc2.git")
        home = e2e_cli._home_dir(r)
        try:
            rc, out, _ = run_cli("access", "set", "--root", str(r), "--key", "db",
                                 "--json", '{"how":"direct","engine":"postgres",'
                                           '"host":"127.0.0.1","password_env":"DB_PASSWORD"}')
            assert json.loads(out).get("ok") is not False, out
            rc, out, _ = run_cli("access", "show", "--root", str(r))
            data = json.loads(out)
            assert data["access"]["db"]["engine"] == "postgres", data
        finally:
            import shutil as _sh
            _sh.rmtree(home, ignore_errors=True)


def test_find_secrets_catches_json_form():
    """기록은 JSON으로 들어온다. yaml만 보면 원문이 그대로 저장된다 (#589에서 실제로 뚫렸다)."""
    assert e2e_cli._find_secrets('{"password": "hunter2supersecret"}')


def test_find_secrets_allows_env_var_name():
    """값이 아니라 '어디서 읽을지'를 적는 것은 막으면 안 된다."""
    assert e2e_cli._find_secrets('{"password_env": "DB_PASSWORD"}') == []


def test_find_secrets_allows_connection_info():
    """host·user는 비밀이 아니다. 여기서 막으면 기록 자체를 못 한다."""
    assert e2e_cli._find_secrets('{"host":"127.0.0.1","user":"root","port":5432}') == []


# ── 남아 있는 것과 내려간 것 (이슈 #589) ─────────────────────────────────

def test_help_lists_current_subcommands():
    """실행 수단과 기록만 남는다. 프로젝트를 '맞히는' 것은 내려갔다."""
    rc, out, err = run_cli("--help")
    combined = out + err
    for cmd in ["detect", "devices", "doctor", "scenario", "note",
                "web", "api", "access", "db", "logs", "shrink"]:
        assert cmd in combined, f"{cmd} 가 --help 에 없다"




# ── 실제로 실행해 본다 (이슈 #589 후속) ──────────────────────────────────
#
# 여기 아래가 없어서 `note` 쓰기 4종과 `scenario init` 이 100% 크래시하는 채로
# 48개 테스트가 전부 초록이었다. `--help` 에 이름이 있는지만 봤기 때문이다.
#
# 기록을 홈으로 옮긴 뒤(#586) 완료 문구가 아직 프로젝트 기준 상대경로를 계산해
# ValueError 로 죽었는데, 파일은 이미 써진 뒤라 "쓰기는 됐지만 명령은 실패"하는
# 형태였다. **이름이 있는지가 아니라 실행이 되는지를 본다.**



@pytest.fixture
def sandbox(tmp_path):
    """프로젝트 하나 + 격리된 홈. 진짜 기록을 건드리지 않는다."""
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)          # git 루트로 인식시킨다
    home = tmp_path / "home"
    home.mkdir()
    return proj, home


def _ok(out: str) -> dict:
    d = json.loads(out)
    assert d.get("ok") is True, f"ok=false: {out}"
    return d


# 인자까지 포함한 실제 호출. 하나라도 죽으면 여기서 잡힌다.
WRITE_CALLS = [
    ("note constraint", ["note", "constraint", "--text", "탈퇴 후 재가입이 되어야 한다"]),
    ("note pitfall",    ["note", "pitfall", "--text", "토스트가 2초 뒤 사라진다"]),
    ("note run",        ["note", "run", "--name", "signup", "--text", "3단계 통과"]),
    ("note screen",     ["note", "screen", "--name", "로그인", "--anchor", "로그인하기",
                         "--taps", "버튼=540,1200", "--screen-size", "1080x2400"]),
    ("scenario init app",    ["scenario", "init", "--name", "s_app", "--target", "app"]),
    ("scenario init web",    ["scenario", "init", "--name", "s_web", "--target", "web"]),
    ("scenario init server", ["scenario", "init", "--name", "s_srv", "--target", "server"]),
    ("access set",      ["access", "set", "--key", "db",
                         "--json", '{"via":"ssh","host":"db.internal"}']),
]


@pytest.mark.parametrize("label,argv", WRITE_CALLS, ids=[c[0] for c in WRITE_CALLS])
def test_write_subcommands_actually_run(sandbox, label, argv):
    """쓰기 명령이 실제로 완주하는가. 예외로 죽으면 stdout이 JSON이 아니라 잡힌다."""
    proj, home = sandbox
    rc, out, err = run_cli(*argv, "--root", str(proj), home=home)
    assert "Traceback" not in err, f"{label} 이 예외로 죽었다:\n{err}"
    d = _ok(out)
    written = Path(d["file"])
    assert written.is_file(), f"{label}: 파일이 생기지 않았다 — {written}"
    # 기록은 홈 아래에 있어야 한다. 프로젝트 안에 쓰면 워크트리에서 또 사라진다.
    assert str(written).startswith(str(home)), f"{label}: 홈 밖에 썼다 — {written}"


def test_read_subcommands_run_on_empty_project(sandbox):
    """아무것도 쌓이지 않은 상태에서도 조회가 죽지 않아야 한다.

    처음 쓰는 사람이 가장 먼저 밟는 경로다. 여기서 예외가 나면 시작을 못 한다.
    """
    proj, home = sandbox
    for argv in (["detect", "--path", str(proj)],
                 ["doctor", "--root", str(proj)],
                 ["note", "show", "--root", str(proj)],
                 ["access", "show", "--root", str(proj)],
                 ["scenario", "list", "--root", str(proj)]):
        rc, out, err = run_cli(*argv, home=home)
        assert "Traceback" not in err, f"{argv[0]} 이 예외로 죽었다:\n{err}"
        json.loads(out)          # JSON 계약이 깨지면 agent가 다음 수를 못 정한다


def test_note_accumulates_instead_of_overwriting(sandbox):
    """두 번 적으면 둘 다 남아야 한다 — 덮어쓰면 쌓이는 의미가 없다."""
    proj, home = sandbox
    run_cli("note", "pitfall", "--text", "첫 번째", "--root", str(proj), home=home)
    rc, out, _ = run_cli("note", "pitfall", "--text", "두 번째",
                         "--root", str(proj), home=home)
    saved = json.loads(Path(_ok(out)["file"]).read_text(encoding="utf-8"))
    texts = [p["text"] for p in saved["pitfalls"]]
    assert texts == ["첫 번째", "두 번째"], texts


def test_scenario_init_then_show_reports_unfilled_template(sandbox):
    """템플릿을 만든 직후 show 하면 '안 채웠다'고 막아야 한다.

    통과시키면 중괄호가 그대로인 시나리오를 밟아 엉뚱한 곳을 누른다.
    """
    proj, home = sandbox
    run_cli("scenario", "init", "--name", "s", "--target", "app",
            "--root", str(proj), home=home)
    rc, out, err = run_cli("scenario", "show", "--name", "s",
                           "--root", str(proj), home=home)
    assert "Traceback" not in err
    d = json.loads(out)
    assert d["ok"] is False and d["code"] == "scenario_invalid"
    assert d["unfilled_placeholders"], "안 채운 자리를 짚어주지 않으면 그대로 밟는다"


def test_knowledge_survives_a_new_worktree(tmp_path):
    """같은 remote면 경로가 달라도 같은 기록을 본다 — 워크트리를 만든 상황.

    기록을 홈으로 옮긴 이유가 이것이다. 경로를 키로 쓰면 여기서 갈라진다.
    """
    home = tmp_path / "home"
    home.mkdir()
    main_wt = tmp_path / "main"
    side_wt = tmp_path / "wt_20260918_600"
    for d in (main_wt, side_wt):
        d.mkdir()
        subprocess.run(["git", "init", "-q", str(d)], check=True)
        subprocess.run(["git", "-C", str(d), "remote", "add", "origin",
                        "https://github.com/acme/thing.git"], check=True)

    run_cli("note", "pitfall", "--text", "워크트리 전에 알아낸 것",
            "--root", str(main_wt), home=home)
    rc, out, _ = run_cli("note", "show", "--root", str(side_wt), home=home)
    d = _ok(out)
    texts = [p["text"] for p in d.get("notes", d).get("pitfalls", [])]
    assert "워크트리 전에 알아낸 것" in texts, f"새 워크트리에서 기록이 사라졌다: {out}"
