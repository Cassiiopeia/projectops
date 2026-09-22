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
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

CLI = Path(__file__).resolve().parents[1] / "scripts" / "e2e_cli.py"
sys.path.insert(0, str(CLI.parent))

import e2e_cli  # noqa: E402


def run_cli(*args, home: Path | None = None, cwd: Path | None = None):
    import os
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    # 기록은 홈에 쌓인다. 테스트가 사용자의 진짜 기록을 건드리면 안 된다.
    if home is not None:
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)   # Windows
    r = subprocess.run([sys.executable, str(CLI), *args],
                       capture_output=True, text=True, encoding="utf-8", env=env,
                       cwd=str(cwd) if cwd else None)
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


# ── 타겟은 선언이 아니라 확인이다 (이슈 #591) ───────────────────────────
#
# version.yml 의 project_types 는 "이 레포가 무엇인가"를 선언할 뿐이다.
# 서버가 화면을 직접 뿌리는 구조(Thymeleaf·Django 템플릿·Rails·JSP)는 전혀 이상하지
# 않은데, 선언만 보면 server 하나로 끝나 브라우저를 열 생각을 못 했다.
# 그렇다고 py 가 템플릿 폴더를 뒤져 맞히면 프레임워크마다 틀린다 — agent 가 코드를
# 보고 판단하고, py 는 그 판단을 기억한다.

def _declared(tmp: Path, types: str, url="https://github.com/acme/thing.git") -> Path:
    proj = tmp / "proj"
    (proj / ".git").mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    subprocess.run(["git", "-C", str(proj), "remote", "add", "origin", url], check=True)
    (proj / "version.yml").write_text(
        f"version: 1.0.0\nmetadata:\n  template:\n    project_types: [{types}]\n",
        encoding="utf-8")
    return proj


def test_declared_targets_ask_agent_to_confirm(sandbox):
    """선언에서 나온 타겟은 '확인된 것'으로 내놓지 않는다."""
    _, home = sandbox
    proj = _declared(home.parent, "spring")
    rc, out, err = run_cli("detect", "--path", str(proj), home=home)
    assert "Traceback" not in err
    d = json.loads(out)
    assert d["targets"] == ["server"]
    assert d["target_source"] == "version.yml"
    # 여기서 멈추면 화면을 뿌리는 서버의 UI 결함을 영영 못 본다
    assert d.get("confirm"), "선언 기반인데 확인하라는 안내가 없다"
    assert "note target" in d["confirm"]["record"]


def test_recorded_targets_beat_declaration(sandbox):
    """agent 가 확인해 적어 두면 그쪽을 믿는다."""
    _, home = sandbox
    proj = _declared(home.parent, "spring")
    rc, out, _ = run_cli("note", "target", "--root", str(proj),
                         "--targets", "server,web",
                         "--why", "Thymeleaf 템플릿으로 화면을 직접 뿌린다", home=home)
    assert _ok(out)

    rc, out, err = run_cli("detect", "--path", str(proj), home=home)
    assert "Traceback" not in err
    d = json.loads(out)
    assert d["targets"] == ["server", "web"]
    assert d["target_source"] == "recorded"
    assert d["recorded_why"] == "Thymeleaf 템플릿으로 화면을 직접 뿌린다"
    # 확인이 끝났으므로 다시 묻지 않는다
    assert "confirm" not in d
    # web 타겟이 붙었으니 브라우저 준비 상태도 함께 온다
    assert "web" in d


def test_note_target_requires_a_reason(sandbox):
    """근거 없이 적으면 다음에 이 기록이 맞는지 다시 볼 수 없다."""
    proj, home = sandbox
    rc, out, _ = run_cli("note", "target", "--root", str(proj),
                         "--targets", "web", home=home)
    d = json.loads(out)
    assert d["ok"] is False and d["code"] == "why_required"


def test_note_target_rejects_unknown_target(sandbox):
    """오타 하나로 엉뚱한 조작 수단을 타면 원인을 찾기 어렵다."""
    proj, home = sandbox
    rc, out, _ = run_cli("note", "target", "--root", str(proj),
                         "--targets", "server,desktop", "--why", "x", home=home)
    d = json.loads(out)
    assert d["ok"] is False and d["code"] == "bad_targets"
    assert "desktop" in d["error"]


# ── other 타겟 — 앱·웹·서버가 아닌 것 (이슈 #597 후속) ──────────────────
#
# 이 스킬로 만든 것을 이 스킬로 밟아 보다가 결함 세 건이 나왔다. 전부 여기에 고정한다.
#
#   ① 수정시각을 초 단위로 봐서, 같은 초에 같은 크기로 바뀐 파일을 놓쳤다
#   ② 멱등을 "변화 목록이 같은가"로 봤다 — 1회차 created, 2회차 modified 라 늘 다르다
#   ③ "무엇을 건드렸나"와 "상태가 같은가"에 같은 기준을 썼다 — 답이 다른 두 질문이다

def _other(sandbox_dirs, *args):
    proj, home = sandbox_dirs
    rc, out, err = run_cli("other", "run", "--root", str(proj), *args, home=home)
    assert "Traceback" not in err, err
    return json.loads(out)


def test_other_sees_files_created(sandbox):
    """출력만 보면 부작용을 놓친다. 무엇이 생겼는지 기계가 보여줘야 한다."""
    proj, _ = sandbox
    d = _other(sandbox, "--command", "mkdir -p out && echo hi > out/a.txt", "--watch", ".")
    assert d["exit_code"] == 0
    assert d["files"]["created"] == ["out/a.txt"], d["files"]


def test_other_sees_same_size_edit_in_same_second(sandbox):
    """같은 크기로 같은 초에 바뀐 파일 — 초 단위 mtime 으로는 못 본다."""
    proj, _ = sandbox
    (proj / "keep.txt").write_text("old\n", encoding="utf-8")
    d = _other(sandbox, "--command", "echo new > keep.txt", "--watch", ".")
    assert d["files"]["modified"] == ["keep.txt"], d["files"]


def test_other_sees_deletion(sandbox):
    proj, _ = sandbox
    (proj / "gone.txt").write_text("x", encoding="utf-8")
    d = _other(sandbox, "--command", "rm gone.txt", "--watch", ".")
    assert d["files"]["deleted"] == ["gone.txt"], d["files"]


def test_other_twice_overwrite_with_same_content_is_idempotent(sandbox):
    """덮어써도 **내용이 같으면** 멱등이다.

    변화 목록으로 판정하면 여기서 오판한다 — 1회차는 만들고(created) 2회차는
    덮어쓰므로(modified) 목록이 늘 다르다.
    """
    d = _other(sandbox, "--command", "mkdir -p out && echo fixed > out/c.txt",
               "--watch", ".", "--twice")
    assert d["second_run"]["settled"] is True, d["second_run"]
    assert d["ok"] is True, d["problems"]


def test_other_twice_changing_content_is_not_idempotent(sandbox):
    """파일명은 같고 내용만 매번 바뀌는 경우 — 놓치면 안 된다."""
    proj, _ = sandbox
    (proj / "out").mkdir()
    d = _other(sandbox, "--command", "echo $RANDOM > out/t.txt", "--watch", ".", "--twice")
    assert d["second_run"]["settled"] is False
    assert d["ok"] is False
    assert any("또 바뀌었습니다" in p for p in d["problems"]), d["problems"]


def test_other_expect_absent_catches_what_should_not_be_there(sandbox):
    """지금까지 스킬은 '있어야 할 것'만 봤다.

    테스트 코드 유출·임시 파일 잔존·지워졌어야 할 구 파일은 전부 이쪽이다.
    """
    d = _other(sandbox, "--command", "mkdir -p tests", "--expect-absent", "tests")
    assert d["ok"] is False and d["code"] == "expectation_failed"
    assert any("남아 있습니다" in p for p in d["problems"])


def test_other_expectations_are_optional(sandbox):
    """조건을 주지 않으면 판정하지 않고 읽으라고 넘긴다 — 판단은 agent 몫이다."""
    d = _other(sandbox, "--command", "echo hello")
    assert d["ok"] is True and d["judged"] is False
    assert "직접 판단" in (d["next"] or "")


def test_other_expect_output_is_substring(sandbox):
    """전체 일치를 요구하면 문구 한 글자에 시나리오가 깨진다."""
    assert _other(sandbox, "--command", "echo 'hello world'",
                  "--expect-output", "hello")["ok"] is True
    assert _other(sandbox, "--command", "echo 'hello world'",
                  "--expect-output", "bye")["ok"] is False


def test_other_timeout_does_not_hang(sandbox):
    """제한이 없으면 매달린 명령에 세션이 묶인다."""
    d = _other(sandbox, "--command", "sleep 10", "--timeout", "2")
    assert d["ok"] is False and d.get("timed_out") is True


def test_other_env_is_injected(sandbox):
    """'기본값이 다른 환경'을 만들어 보려면 값을 넣을 수 있어야 한다."""
    d = _other(sandbox, "--command", "echo $MYVAR", "--env", "MYVAR=주입됨",
               "--expect-output", "주입됨")
    assert d["ok"] is True, d["problems"]


def test_other_requires_command_or_scenario(sandbox):
    d = _other(sandbox)
    assert d["ok"] is False and d["code"] == "args_required"


def test_other_without_watch_does_not_observe_files(sandbox):
    """--watch 를 주지 않으면 파일을 보지 않는다 — 레포 전체를 뜨면 느리고 시끄럽다."""
    d = _other(sandbox, "--command", "echo hi > x.txt")
    assert "files" not in d


def test_other_scenario_requires_other_target(sandbox):
    """app 시나리오를 other 로 밟으면 조용히 엉뚱한 것을 하지 않고 막는다."""
    proj, home = sandbox
    run_cli("scenario", "init", "--root", str(proj), "--name", "s_app",
            "--target", "app", home=home)
    d = _other(sandbox, "--name", "s_app")
    assert d["ok"] is False and d["code"] in ("scenario_invalid", "wrong_target")


def test_other_target_is_a_known_target():
    """시나리오 검증이 other 를 모르는 값으로 거부하면 안 된다."""
    problems = e2e_cli._validate({
        "name": "x", "target": "other",
        "steps": [{"screen": "빌드", "do": "make", "expect_exit": 0}],
    })
    assert problems == [], problems


def test_other_step_without_any_expectation_is_rejected():
    """기대 결과가 없으면 '돌았으니 통과'로 끝난다."""
    problems = e2e_cli._validate({
        "name": "x", "target": "other",
        "steps": [{"screen": "빌드", "do": "make"}],
    })
    assert any("기대 결과" in p for p in problems), problems


# ── 소셜 로그인 관문 (이슈 #604) ──────────────────────────────────────────
#
# 브라우저가 필요한 테스트가 아니다. 계약을 본다 —
# 비밀번호가 명령줄에 남지 않을 "수단"이 실제로 있는지, 그리고 문서가
# 판정 신호를 계속 들고 있는지. 둘 다 없으면 다음 사람이 같은 벽에 다시 부딪힌다.

def test_web_accepts_text_env_so_passwords_stay_out_of_the_transcript():
    """--text-env 가 없으면 비밀번호를 --text 에 적는 수밖에 없다."""
    _, out, _ = run_cli("web", "--help")
    assert "--text-env" in out


def test_web_text_env_refuses_when_the_variable_is_missing(sandbox):
    """값이 비었는데 조용히 빈 문자열을 넣으면, 로그인 실패 원인을 엉뚱한 데서 찾게 된다."""
    _, out, _ = run_cli("web", "type", "--selector", "#pw", "--text-env", "NO_SUCH_VAR_HERE",
                        "--root", str(sandbox), home=sandbox)
    d = json.loads(out)
    assert d["ok"] is False
    assert d["code"] == "env_not_set"
    assert "NO_SUCH_VAR_HERE" in d["error"]


def test_web_text_env_is_read_before_any_browser_is_needed(sandbox):
    """브라우저가 없어도 이 검사는 통과해야 한다 — 없는 변수는 네트워크 전에 걸린다."""
    _, out, _ = run_cli("web", "type", "--selector", "#pw", "--text-env", "NO_SUCH_VAR_HERE",
                        "--root", str(sandbox), home=sandbox)
    d = json.loads(out)
    # 브라우저 미기동("no_browser") 이 아니라 환경변수 문제로 끝나야 한다
    assert d["code"] == "env_not_set"


def test_skill_keeps_the_login_flow_signal():
    """flowName 판정 신호가 사라지면 headless 로 시도했다가 매번 거부당한다."""
    skill = (CLI.parents[1] / "SKILL.md").read_text(encoding="utf-8")
    assert "WebLiteSignIn" in skill and "GlifWebSignIn" in skill
    assert "--headed" in skill


def test_social_login_reference_exists_and_marks_what_is_unverified():
    """실측하지 않은 제공자를 실측한 것처럼 적으면 다음 사람이 그대로 믿는다."""
    doc = CLI.parents[1] / "references" / "social-login.md"
    assert doc.exists()
    text = doc.read_text(encoding="utf-8")
    assert "미확인" in text          # 애플·카카오 등
    assert "--text-env" in text      # 비밀값 취급 수단을 문서도 안내한다
    assert "테스트 계정" in text      # 소셜 로그인보다 먼저 볼 것


def test_social_login_reference_is_linked_from_the_skill():
    """참조되지 않는 문서는 읽히지 않는다."""
    skill = (CLI.parents[1] / "SKILL.md").read_text(encoding="utf-8")
    assert "references/social-login.md" in skill


# ── 화면 캡처 경량화 (#604 후속) ──────────────────────────────────────
#
# 줄여야 하는 것이 둘인데 방법이 다르다. 한쪽만 하면 나머지가 그대로 남는다.
#   세션 토큰 → 해상도 축소 (포맷은 영향 없음)
#   전송량    → WebP 변환

def test_shot_and_shrink_share_one_max_side():
    """기준이 둘이면 어느 쪽이 맞는지 알 수 없다."""
    _, out, _ = run_cli("shrink", "--help")
    assert str(e2e_cli.SHOT_MAX_SIDE) in out


def test_web_shot_can_keep_the_original_size():
    """좌표를 정밀하게 봐야 할 때가 있다 — 끌 수 있어야 한다."""
    _, out, _ = run_cli("web", "--help")
    assert "--max-side" in out


def test_webp_conversion_survives_without_any_tool(tmp_path, monkeypatch):
    """Pillow·cwebp·ffmpeg 가 하나도 없어도 화면을 못 찍게 되지는 않는다."""
    png = tmp_path / "x.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    monkeypatch.setattr(e2e_cli, "_has_pillow", lambda: False)
    monkeypatch.setattr(e2e_cli, "_venv_python", lambda: None)
    monkeypatch.setattr(e2e_cli.shutil, "which", lambda _n: None)
    assert e2e_cli._to_webp(png) is None
    assert png.exists(), "변환에 실패했다고 원본을 지우면 안 된다"


def test_doctor_tells_when_screens_cannot_be_shrunk(sandbox, monkeypatch):
    """수단이 없다는 사실이 드러나야 사용자가 조치할 수 있다."""
    import json as _json
    _, out, _ = run_cli("doctor", "--root", str(sandbox), home=sandbox)
    d = _json.loads(out)
    assert "image_resize" in d
    # 수단이 있으면 이름이, 없으면 무엇이 손해인지가 적혀야 한다
    assert d["image_resize"]


# ── 증거는 정해진 자리에만 쌓인다 (이슈 #611) ────────────────────────────
#
# 스킬이 "어디에 두라"를 말한 적이 없어서, 밟을 때마다 에이전트가 자리를 지어냈다.
# 실제로 대상 레포에 docs/testing/ 이 생겨 8MB 가 .gitignore 밖에 쌓였다.
# 아래 검사들은 "폴더가 생겼다"가 아니라 **git 이 실제로 무시하는가**를 본다 —
# 있다는 사실만 확인하면 #591 과 같은 실수(돌지 않는 초록불)를 반복한다.

def _repo(tmp: Path, name: str = "proj") -> Path:
    proj = tmp / name
    proj.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    subprocess.run(["git", "-C", str(proj), "remote", "add", "origin",
                    "https://github.com/acme/thing.git"], check=True)
    return proj


def test_output_path_lands_under_the_umbrella(tmp_path):
    """산출물은 harness/WORKFLOW.md 가 정한 docs/projectops/ 우산 아래에만 만든다."""
    proj = _repo(tmp_path)
    rc, out, err = run_cli("get-output-path", "--title", "로그인 화면 검증", cwd=proj)
    assert rc == 0, f"{out}{err}"
    d = json.loads(out)

    umbrella = (proj / "docs" / "projectops" / "agent-test").resolve()
    run_dir = Path(d["run_dir"]).resolve()
    assert run_dir.parent == umbrella, f"우산 밖에 만들었다: {run_dir}"
    assert Path(d["screenshots"]).is_dir(), "screenshots 폴더가 없다"
    assert Path(d["env_file"]).is_file(), "하네스 env.sh 가 없다"


def test_evidence_folder_is_really_untracked(tmp_path):
    """.gitignore 가 있다가 아니라, git add -A 로도 증거가 안 담기는지 본다."""
    proj = _repo(tmp_path)
    _, out, _ = run_cli("get-output-path", "--title", "증거 추적 제외", cwd=proj)
    d = json.loads(out)

    # 실제 증거물을 넣는다 — 이미지 · 메모 · 하네스
    (Path(d["screenshots"]) / "01.png").write_bytes(b"\x89PNG" + b"0" * 4096)
    (Path(d["run_dir"]) / "findings.json").write_text("{}", encoding="utf-8")

    subprocess.run(["git", "-C", str(proj), "add", "-A"], check=True)
    staged = subprocess.run(["git", "-C", str(proj), "diff", "--cached", "--name-only"],
                            capture_output=True, text=True, check=True).stdout.split()

    assert staged == ["docs/projectops/agent-test/.gitignore"], (
        f"증거물이 커밋에 딸려 들어간다: {staged}")


def test_output_path_does_not_touch_root_gitignore(tmp_path):
    """폴더가 추적 제외를 스스로 들고 다닌다 — 공용 파일을 건드리면 사용자 변경과 충돌한다."""
    proj = _repo(tmp_path)
    (proj / ".gitignore").write_text("build/\n", encoding="utf-8")
    run_cli("get-output-path", "--title", "루트 보존", cwd=proj)
    assert (proj / ".gitignore").read_text(encoding="utf-8") == "build/\n", (
        "루트 .gitignore 를 고쳤다")


def test_env_sh_points_inside_the_run(tmp_path):
    """하네스는 실행 폴더 안을 가리켜야 한다. 밖을 가리키면 증거가 흩어진다."""
    proj = _repo(tmp_path)
    _, out, _ = run_cli("get-output-path", "--title", "하네스", "--package", "com.acme.x",
                        cwd=proj)
    d = json.loads(out)
    body = Path(d["env_file"]).read_text(encoding="utf-8")

    # 따옴표 종류가 아니라 값이 맞는지를 본다 — 경로·역할 이름에 $ 나 공백이
    # 들어올 수 있어 작은따옴표로 감싼다 (#583).
    assert "export SHOT_DIR=" in body and "export RUN_DIR=" in body
    assert "com.acme.x" in body and "export PKG=" in body
    shot = Path(d["screenshots"]).resolve()
    assert shot.is_relative_to(Path(d["run_dir"]).resolve()), "SHOT_DIR 이 실행 폴더 밖이다"
    assert str(shot) in body, "env.sh 의 SHOT_DIR 이 실제 폴더와 다르다"


def test_output_path_can_run_twice(tmp_path):
    """같은 실행에서 두 번 불러도 자리가 망가지지 않는다."""
    proj = _repo(tmp_path)
    _, o1, _ = run_cli("get-output-path", "--title", "두 번", cwd=proj)
    _, o2, _ = run_cli("get-output-path", "--title", "두 번", cwd=proj)
    assert json.loads(o1)["gitignore"] == "created"
    assert json.loads(o2)["gitignore"] == "already", "두 번째에 .gitignore 를 다시 썼다"


# ── 문서가 에이전트를 잘못 이끌지 않는지 전수로 본다 (이슈 #611) ──────────
#
# 코드를 고쳐도 문서에 "/tmp 에 찍어라"가 남아 있으면 다음 실행에서 또 흩어진다.
# 실제 원인이 코드가 아니라 SKILL.md 한 줄이었다.

_FORBIDDEN_PATHS = {
    "/tmp/": "임시 폴더에 증거를 쌓으면 실행이 끝나고 사라지거나 흩어진다",
    "docs/testing": "우산(docs/projectops/) 밖이다. 추적 제외도 안 된다",
}


def test_skill_docs_never_name_a_made_up_evidence_path():
    """증거 경로를 문서에 직접 적지 않는다 — get-output-path 가 주는 값만 쓴다."""
    skill_dir = CLI.parents[1]
    docs = [skill_dir / "SKILL.md", *sorted((skill_dir / "references").glob("*.md"))]
    assert docs, "검사할 문서를 찾지 못했다"

    # 산문은 보지 않는다 — "이렇게 하지 마라"는 경고는 오히려 있어야 한다.
    # 에이전트가 실제로 복사해 실행하는 것은 코드블록 안이다.
    bad = []
    for doc in docs:
        in_fence = False
        for i, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if not in_fence:
                continue
            for needle, why in _FORBIDDEN_PATHS.items():
                if needle in line:
                    bad.append(f"{doc.name}:{i} `{needle}` — {why}\n    {line.strip()}")

    assert not bad, (
        "문서가 임의 경로를 지시한다. get-output-path 의 $SHOT_DIR 을 쓰세요:\n"
        + "\n".join(bad))


# ── 참가자가 둘 이상인 검증 (이슈 #583) ──────────────────────────────────
#
# 가장 위험한 실패는 "안 되는 것"이 아니라 **조용히 다른 기기로 가는 것**이다.
# 역할 이름을 셸 변수명에 넣으면 정확히 그렇게 된다:
#
#   $ export DEV_만드는쪽=emulator-5554
#   bash: export: `DEV_만드는쪽=...': not a valid identifier
#   $ echo "$DEV_만드는쪽"
#   만드는쪽                    ← 터지지 않고 엉뚱한 값
#
# 그래서 번호로 고정하고 이름은 값으로 담는다. 아래 검사가 그 계약을 지킨다.

_SH_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _env_of(proj: Path, *bind_args) -> tuple[Path, str, dict]:
    """실행 자리를 만들고 역할을 묶은 뒤 env.sh 를 돌려준다.

    바인딩은 홈(`~/.projectops/...`)에 저장되고 키는 git remote 다 — 테스트끼리
    HOME 을 나눠 갖지 않으면 앞 테스트의 역할이 남아 번호가 밀린다 (실제로 그랬다).
    """
    home = proj.parent / f"home-{proj.name}"
    home.mkdir(exist_ok=True)
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home),
           "PYTHONIOENCODING": "utf-8"}

    r = subprocess.run([sys.executable, str(CLI), "get-output-path", "--title", "역할",
                        "--root", str(proj)],
                       cwd=proj, env=env, capture_output=True, text=True,
                       encoding="utf-8", check=True)
    run_dir = Path(json.loads(r.stdout)["run_dir"])
    env["RUN_DIR"] = str(run_dir)
    for args in bind_args:
        subprocess.run([sys.executable, str(CLI), "device", "bind",
                        "--root", str(proj), *args],
                       cwd=proj, env=env, capture_output=True, text=True,
                       encoding="utf-8", check=True)
    f = run_dir / "env.sh"
    return f, f.read_text(encoding="utf-8"), env


def test_role_names_never_become_shell_variable_names(tmp_path):
    """역할 이름이 무엇이든 env.sh 의 변수명은 전부 올바른 셸 식별자여야 한다."""
    proj = _repo(tmp_path)
    _, body, _ = _env_of(
        proj,
        ["--role", "A", "--serial", "emulator-5554", "--note", "만드는 쪽"],
        ["--role", "받는 쪽", "--serial", "emulator-5556"],
        ["--role", "it's-a/role", "--serial", "emulator-5558"],
    )
    # 한 줄에 export 가 둘이다 (`export ROLE1=...; export DEV1=...`).
    # 줄 앞만 보면 뒤엣것을 놓친다 — 실제로 놓쳤다.
    names = re.findall(r"\bexport ([^=\s]+)=", body)
    assert names, "export 를 하나도 못 찾았다"
    bad = [n for n in names if not _SH_NAME.match(n)]
    assert bad == [], f"셸이 거부하는 변수명이 있다: {bad}"

    # 이름은 값으로 담긴다 — 그래야 시나리오의 roles 키와 이어진다.
    # 아포스트로피는 이스케이프되므로 원문 포함 여부로 보면 안 된다.
    assert "받는 쪽" in body
    assert "it" in body and "s-a/role" in body


@pytest.mark.skipif(not shutil.which("bash"), reason="bash 가 없는 환경")
def test_env_sh_actually_sources_in_bash(tmp_path):
    """값 검사만으로는 부족하다 — 실제로 source 해서 값이 들어오는지 본다."""
    proj = _repo(tmp_path)
    env_file, _, _ = _env_of(
        proj,
        ["--role", "A", "--serial", "emulator-5554"],
        ["--role", "받는 쪽", "--serial", "emulator-5556", "--note", "it's B"],
        ["--role", "it's-a/role", "--serial", "emulator-5558"],
    )
    r = subprocess.run(
        ["bash", "-c",
         f'source "{env_file}"; echo "$ROLE2|$ROLE3|$DEV2|$DEV_COUNT|$DEV"'],
        capture_output=True, text=True)
    assert r.returncode == 0, f"source 가 실패했다: {r.stderr}"
    assert "not a valid identifier" not in r.stderr, r.stderr
    # 한글·공백·아포스트로피·슬래시가 든 이름이 그대로 돌아와야 한다
    assert r.stdout.strip() == "받는 쪽|it's-a/role|emulator-5556|3|emulator-5554", r.stdout


def test_binding_survives_and_orders_the_devices(tmp_path):
    """묶은 순서가 곧 DEV1·DEV2 다. 해제하면 번호가 당겨진다."""
    proj = _repo(tmp_path)
    env_file, body, env = _env_of(
        proj,
        ["--role", "A", "--serial", "s-a"],
        ["--role", "B", "--serial", "s-b"],
    )
    assert "export ROLE1='A'; export DEV1='s-a'" in body
    assert "export ROLE2='B'; export DEV2='s-b'" in body

    subprocess.run([sys.executable, str(CLI), "device", "unbind", "--root", str(proj),
                    "--role", "A"], cwd=proj, env=env, capture_output=True, check=True)
    after = env_file.read_text(encoding="utf-8")
    assert "export ROLE1='B'; export DEV1='s-b'" in after, after
    assert "export DEV2=" not in after, "번호가 당겨지지 않았다"
    assert "export DEV_COUNT=1" in after


def test_package_is_kept_when_bindings_change(tmp_path):
    """device bind 가 env.sh 를 다시 써도 PKG 가 사라지면 안 된다."""
    proj = _repo(tmp_path)
    env_file, _, _ = _env_of(proj, ["--role", "A", "--serial", "s-a",
                                    "--package", "com.acme.x"])
    body = env_file.read_text(encoding="utf-8")
    assert "com.acme.x" in body, f"PKG 가 사라졌다:\n{body}"


def test_dev_is_always_defined(tmp_path):
    """문서가 `adb -s "$DEV"` 로 적혀 있다. DEV 가 없으면 `adb -s ` 가 되어 죽는다."""
    proj = _repo(tmp_path)
    _, out, _ = run_cli("get-output-path", "--title", "기본기기", cwd=proj)
    body = (Path(json.loads(out)["run_dir"]) / "env.sh").read_text(encoding="utf-8")
    assert re.search(r"^export DEV=", body, re.MULTILINE), body


def test_build_mismatch_needs_hashes_not_versions():
    """버전이 같아도 APK 가 다르면 잡아야 한다 — 플래그만 바꾼 재빌드가 그렇다."""
    same_ver = [
        {"role": "A", "build": {"apk": "aaa", "version": "1.2.0+45"}},
        {"role": "B", "build": {"apk": "bbb", "version": "1.2.0+45"}},
    ]
    found = e2e_cli._build_mismatch(same_ver)
    assert found and "한쪽만 다시 설치" in found[0]["detail"]

    assert e2e_cli._build_mismatch([
        {"role": "A", "build": {"apk": "aaa", "version": "1.2.0+45"}},
        {"role": "B", "build": {"apk": "aaa", "version": "1.2.0+45"}},
    ]) == []
    # 해시를 못 구한 기기는 판정에서 빠진다 — 모르는 것을 다르다고 하지 않는다
    assert e2e_cli._build_mismatch([
        {"role": "A", "build": {"apk": "aaa"}},
        {"role": "B", "build": {"apk": None}},
    ]) == []


def test_old_screen_records_are_promoted_not_lost(tmp_path):
    """예전 기록(좌표 한 벌)을 쓰던 프로젝트가 깨지면 안 된다."""
    legacy = {"anchor": "설정", "taps": {"로그아웃": "540,1200"},
              "measured_on": "1080x2400"}
    promoted = e2e_cli._promote_screen(dict(legacy))
    assert "variants" in promoted
    key = "default@1080x2400"
    assert promoted["variants"][key]["taps"] == legacy["taps"]
    assert promoted["anchor"] == "설정"
    # 두 번 올려도 그대로 (멱등)
    assert e2e_cli._promote_screen(dict(promoted)) == promoted


def test_screens_keep_one_set_of_taps_per_role(tmp_path):
    """역할이 다르면 좌표가 따로 쌓여야 한다 — 빌드가 다르면 화면이 다르다."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    proj = _repo(tmp_path, "p2")
    for role, xy in (("A", "540,1200"), ("B", "540,1400")):
        run_cli("note", "screen", "--root", str(proj), "--name", "설정",
                "--anchor", "설정", "--taps", f"로그아웃={xy}",
                "--screen-size", "1080x2400", "--role", role, home=home)
    _, out, _ = run_cli("note", "show", "--root", str(proj), home=home)
    variants = json.loads(out)["screens"]["설정"]["variants"]
    assert set(variants) == {"A@1080x2400", "B@1080x2400"}, variants
    assert variants["A@1080x2400"]["taps"]["로그아웃"] == "540,1200"
    assert variants["B@1080x2400"]["taps"]["로그아웃"] == "540,1400"


# ── 문서가 기기를 지정하지 않는 명령을 가르치면 안 된다 (#583) ────────────
#
# 원인은 에이전트가 아니라 문서였다. `adb shell ...` 이 맨몸으로 적혀 있으면
# 에이전트는 그것을 복사한다. 기기가 한 대일 때는 돌아가서 오래 안 보인다.

_ADB_NEEDS_SERIAL = ("shell", "exec-out", "install", "uninstall", "logcat",
                     "pull", "push", "emu", "root", "forward", "reverse")
_ADB_BARE_OK = ("devices", "start-server", "kill-server", "version")


def test_skill_docs_always_say_which_device(tmp_path=None):
    """문서 코드블록의 adb 는 전부 기기를 지정해야 한다."""
    pattern = re.compile(r"\badb (?!-s )(" + "|".join(_ADB_NEEDS_SERIAL) + r")\b")
    skill_dir = CLI.parents[1]
    docs = [skill_dir / "SKILL.md", *sorted((skill_dir / "references").glob("*.md"))]

    bare, checked = [], 0
    for doc in docs:
        in_fence = False
        for i, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if not in_fence:
                continue
            if "adb " in line:
                checked += 1
            if pattern.search(line):
                bare.append(f"{doc.name}:{i}  {line.strip()}")

    assert checked > 0, "검사할 adb 명령을 못 찾았다 — 검사가 헛돌고 있다"
    assert bare == [], (
        '기기를 지정하지 않은 adb 가 있다. `adb -s "$DEV" ...` 로 적으세요 '
        f'({"·".join(_ADB_BARE_OK)} 는 예외):\n' + "\n".join(bare))


# =========================================================================
# 콘솔 오류는 **로드 중에** 난다 (#625)
#
# 예전에는 `web console` 이 불린 그 시점에 리스너를 달고 잠깐 들었다. 오류는
# 대개 페이지가 열리는 동안 나므로 **정작 잡아야 할 것이 안 잡혔다.**
# 웹에서 가장 흔한 실패가 "화면은 멀쩡한데 자바스크립트가 죽어 버튼이 안 먹는 것"
# 이라 이걸 놓치면 통과로 적게 된다.
# =========================================================================

_LOAD_ERROR_HTML = (
    b'<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>t</title>'
    b'<script>console.error("CONSOLE_ERROR_MARK");</script>'
    b'<script>Promise.reject(new Error("REJECTION_MARK"));</script>'
    b'<script>undefinedFunctionMark();</script>'
    b'<script>console.warn("WARN_MARK");</script>'
    b'</head><body><h1>\xeb\xa9\x80\xec\xa9\xa1\xed\x95\xb4 \xeb\xb3\xb4\xec\x9d\xb8\xeb\x8b\xa4</h1></body></html>'
)


def _serve(body: bytes):
    """테스트용 한 페이지 서버. (포트, 종료함수, 요청수 리스트)를 돌려준다."""
    import http.server
    import threading

    hits = []

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            hits.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_port, srv.shutdown, hits


def test_console_hook_script_covers_every_way_an_error_shows_up():
    """훅 자체는 도구 없이도 검사할 수 있다 — 값 검사라 어디서나 돈다.

    `console.error` 만 가로채면 **잡히지 않은 예외와 거부된 프로미스를 놓친다.**
    실제로 그 둘이 더 심각한 사고인 경우가 많다.
    """
    hook = e2e_cli._CONSOLE_HOOK
    assert "window.__projectops_console" in hook
    assert '"error"' in hook and '"warn"' in hook
    # console 을 안 거치는 두 경로
    assert 'addEventListener("error"' in hook
    assert 'addEventListener("unhandledrejection"' in hook
    # 두 번 심어도 기록이 날아가지 않아야 한다 (붙을 때마다 심는다)
    assert "if (window.__projectops_console) return;" in hook


@pytest.mark.local_only
def test_console_catches_errors_that_happened_while_the_page_loaded(tmp_path):
    """열기 전에 훅을 심어야 로드 중 오류가 잡힌다. 이 순서가 곧 계약이다."""
    ok, _ = e2e_cli._require_playwright()
    if ok is None:
        pytest.skip("Playwright 없음 — web setup 후 실행된다")

    port, stop, hits = _serve(_LOAD_ERROR_HTML)
    root = tmp_path / "proj"
    root.mkdir()
    try:
        rc, out, _ = run_cli("web", "open", "--root", str(root),
                         "--url", f"http://127.0.0.1:{port}/")
        opened = json.loads(out)
        assert opened.get("ok") is not False, opened
        assert opened["console_hook"] is True, "훅을 못 심었다"

        rc, out, _ = run_cli("web", "console", "--root", str(root))
        d = json.loads(out)
        assert d.get("ok") is not False, d
        texts = " | ".join(l["text"] for l in d["logs"])

        # 네 종류가 모두 잡혀야 한다
        assert "CONSOLE_ERROR_MARK" in texts, texts
        assert "undefinedFunctionMark" in texts, texts       # 잡히지 않은 예외
        assert "REJECTION_MARK" in texts, texts              # 거부된 프로미스
        assert "WARN_MARK" in texts, texts
        assert d["error_count"] >= 3, d
        assert "로드 시점부터" in d["summary"]

        # 브라우저를 목적지 URL 로 띄우면 훅 없이 한 번 받고, goto 로 또 받는다.
        # 같은 주소를 **두 번 요청**하는 셈이라 서버에 두 번 찍힌다 — 목적지가
        # 무언가를 바꾸는 주소면 그 일이 두 번 일어난다. 빈 탭으로 띄워야 한다.
        assert [h for h in hits if h == "/"] == ["/"], (
            f"목적지를 {len(hits)}번 요청했다 — 빈 탭으로 띄운 뒤 이동해야 한다: {hits}")
    finally:
        run_cli("web", "close", "--root", str(root))
        stop()


@pytest.mark.local_only
def test_hook_survives_navigation_driven_by_a_later_call(tmp_path):
    """훅은 연결이 끊기면 사라진다 — 붙을 때마다 다시 심지 않으면 조용히 빈다.

    실측: 열 때 한 번만 심었더니, 다른 호출이 이동시킨 페이지에서는 기록이
    통째로 없었다(`console_hook_missing`).
    """
    ok, _ = e2e_cli._require_playwright()
    if ok is None:
        pytest.skip("Playwright 없음 — web setup 후 실행된다")

    port, stop, hits = _serve(_LOAD_ERROR_HTML)
    root = tmp_path / "proj"
    root.mkdir()
    try:
        run_cli("web", "open", "--root", str(root), "--url", "about:blank")
        # 별도 호출로 이동 — 여기서 훅이 다시 심어져야 한다
        run_cli("web", "goto", "--root", str(root), "--url", f"http://127.0.0.1:{port}/")
        rc, out, _ = run_cli("web", "console", "--root", str(root))
        d = json.loads(out)
        assert d.get("code") != "console_hook_missing", d
        assert "CONSOLE_ERROR_MARK" in " ".join(l["text"] for l in d["logs"]), d
    finally:
        run_cli("web", "close", "--root", str(root))
        stop()
