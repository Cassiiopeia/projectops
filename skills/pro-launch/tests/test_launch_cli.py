"""launch_cli 단위 테스트 (#629).

pro-agent-test 에서 옮겨 온 실행·캡처 계약(web · device · shrink · webp · output · env)과
새 명령(app · web viewport · web route · http · stealth · 저장 폴더 이전)을 본다.

기기·브라우저·서버가 없어도 돌아야 한다. 진짜 브라우저가 필요한 것만 `local_only` 다.

⚠️ 브라우저 테스트는 HOME 을 바꾸지 않는다 — macOS Chrome 은 HOME 이 바뀌면 이동 중
멈춘다(실측). 대신 원격 없는 임시 레포를 --root 로 줘서 상태 폴더만 나누고 끝나면 지운다.
"""
from __future__ import annotations

import contextlib
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

CLI = Path(__file__).resolve().parents[1] / "scripts" / "launch_cli.py"
sys.path.insert(0, str(CLI.parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import launch_cli  # noqa: E402
import stealth  # noqa: E402
from common import image as common_image  # noqa: E402
from common import state as common_state  # noqa: E402

_SH_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def run_cli(*args, home: Path | None = None, cwd: Path | None = None, env_extra=None):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    # 기록은 홈에 쌓인다. 테스트가 사용자의 진짜 기록을 건드리면 안 된다.
    if home is not None:
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)   # Windows
    for k in ("SHOT_DIR", "RUN_DIR", "DEV", "PKG"):
        env.pop(k, None)
    env.update(env_extra or {})
    r = subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True,
                       encoding="utf-8", env=env, cwd=str(cwd) if cwd else None)
    return r.returncode, r.stdout or "", r.stderr or ""


def _j(out: str) -> dict:
    return json.loads(out.strip().splitlines()[-1])


def _repo(tmp: Path, name: str = "proj", remote: str | None = "https://github.com/acme/thing.git") -> Path:
    proj = tmp / name
    proj.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    if remote:
        subprocess.run(["git", "-C", str(proj), "remote", "add", "origin", remote], check=True)
    return proj


@contextlib.contextmanager
def playwright_hidden():
    """설치 여부와 무관하게 '없는 상태'를 만든다 — 깔린 기계에서도 이 검사가 돌아야 한다 (#591)."""
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


# ── 명령 표면 ─────────────────────────────────────────────────────────────

def test_help_lists_every_subcommand():
    _, out, err = run_cli("--help")
    for name in ("doctor", "detect", "devices", "device", "app", "web", "http",
                 "access", "db", "logs", "shrink", "get-output-path"):
        assert name in out + err, f"{name} 가 --help 에 없다"


def test_web_help_lists_all_actions():
    _, out, err = run_cli("web", "--help")
    for a in ("setup", "open", "goto", "click", "type", "shot", "assert", "console", "close",
              "viewport", "route", "--no-stealth", "--max-side"):
        assert a in out + err, f"{a} 가 web --help 에 없다"


def test_bad_args_still_answer_json():
    rc, out, _ = run_cli("app", "fly")
    assert rc != 0 and _j(out)["code"] == "bad_args"


def test_shot_and_shrink_share_one_max_side():
    """기준이 둘이면 어느 쪽이 맞는지 알 수 없다."""
    _, out, _ = run_cli("shrink", "--help")
    assert str(common_image.SHOT_MAX_SIDE) in out


# ── Playwright 가 없을 때 무엇을 말해 주나 ────────────────────────────────

def test_web_reports_missing_playwright_with_install_hint():
    with playwright_hidden():
        ok, err = launch_cli._require_playwright()
    assert ok is None
    assert err["code"] == "playwright_missing"
    assert err["fix"].startswith("web setup"), err
    assert "venv" in err["manual"], err
    assert "설치할까요" in err["ask_user"], err


def test_web_action_without_open_browser_is_refused(tmp_path):
    proj = _repo(tmp_path)
    rc, out, _ = run_cli("web", "click", "--root", str(proj), "--selector", "#x", home=tmp_path)
    assert _j(out)["code"] in ("browser_not_open", "playwright_missing")


def test_web_text_env_refuses_when_the_variable_is_missing(tmp_path):
    """비밀번호는 --text-env 로 받는다. 비어 있으면 브라우저를 찾기 전에 멈춘다."""
    proj = _repo(tmp_path)
    _, out, _ = run_cli("web", "type", "--root", str(proj), "--selector", "#pw",
                        "--text-env", "NO_SUCH_VAR_X", home=tmp_path)
    assert _j(out)["code"] == "env_not_set"


# ── 무엇을 띄울 수 있나 (#586 에서 옮김) ─────────────────────────────────

def test_version_yml_wins_over_markers(tmp_path):
    """projectops 가 통합된 레포는 이미 답을 갖고 있다 — 추론보다 신뢰할 수 있다."""
    (tmp_path / "version.yml").write_text(
        "metadata:\n  project_types:\n    - flutter\n    - spring\n", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"dependencies":{"react":"18"}}', encoding="utf-8")
    det = launch_cli.detect_kinds(tmp_path)
    assert det["source"] == "version.yml" and det["kinds"] == ["app", "server"], det


def test_markers_used_when_no_version_yml(tmp_path):
    (tmp_path / "package.json").write_text('{"dependencies":{"next":"14"}}', encoding="utf-8")
    det = launch_cli.detect_kinds(tmp_path)
    assert det["source"] == "marker" and "web" in det["kinds"], det


def test_flutter_android_gradle_is_not_mistaken_for_server(tmp_path):
    """Flutter 앱의 android/build.gradle 을 서버로 잡으면 엉뚱한 것을 띄운다."""
    (tmp_path / "pubspec.yaml").write_text("name: x\ndependencies:\n  flutter:\n", encoding="utf-8")
    (tmp_path / "android").mkdir()
    (tmp_path / "android" / "build.gradle").write_text("// app", encoding="utf-8")
    assert launch_cli.detect_kinds(tmp_path)["kinds"] == ["app"]


def test_unknown_project_reports_none_not_crash(tmp_path):
    det = launch_cli.detect_kinds(tmp_path)
    assert det["kinds"] == [] and det["source"] == "none"


def test_detect_can_be_told_which_kinds(tmp_path):
    """부르는 쪽이 이미 알면(확인해 적어 둔 타겟) 그 종류의 정보를 모은다."""
    proj = _repo(tmp_path)
    _, out, _ = run_cli("detect", "--path", str(proj), "--kinds", "web", home=tmp_path)
    d = _j(out)
    assert d["kinds"] == ["web"] and d["source"] == "given" and "web" in d
    _, out, _ = run_cli("detect", "--path", str(proj), "--kinds", "wbe", home=tmp_path)
    assert _j(out)["code"] == "unknown_kind"


# ── 저장 자리 · 이전 ──────────────────────────────────────────────────────

def test_repo_key_uses_remote_not_path(tmp_path):
    a = _repo(tmp_path, "a", "https://github.com/Twin-Fang/elum.git")
    b = _repo(tmp_path, "b", "git@github.com:Twin-Fang/elum.git")
    assert common_state.repo_key(a) == common_state.repo_key(b) == "Twin-Fang__elum"


def test_state_lives_under_launch_outside_project(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    proj = _repo(tmp_path)
    d = common_state.state_dir("launch", proj)
    assert d == tmp_path / "home" / ".projectops" / "launch" / "acme__thing"
    assert not d.is_relative_to(proj)


def _old_dir(home: Path) -> Path:
    d = home / ".projectops" / "agent-test" / "acme__thing"
    d.mkdir(parents=True)
    (d / "devices.json").write_text('{"package":"com.a","bindings":[]}', encoding="utf-8")
    (d / "access.json").write_text('{"base_url":"http://x"}', encoding="utf-8")
    (d / "learned.json").write_text("{}", encoding="utf-8")
    (d / "shots").mkdir()
    return d


def test_migration_moves_only_launch_files_and_is_idempotent(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    proj = _repo(tmp_path)
    old = _old_dir(home)

    first = common_state.migrate_launch(proj)
    assert sorted(first["moved"]) == ["access.json", "devices.json", "shots"]
    new = common_state.state_dir("launch", proj)
    assert (new / "access.json").is_file() and not (old / "access.json").exists()
    # QA 몫은 agent-test 에 남는다
    assert (old / "learned.json").is_file() and not (new / "learned.json").exists()

    second = common_state.migrate_launch(proj)
    assert second == {"moved": [], "warnings": []}


def test_migration_does_not_move_a_browser_in_use(tmp_path, monkeypatch):
    """떠 있는 브라우저의 프로필을 옮기면 깨진다 — 미루고 알린다."""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    proj = _repo(tmp_path)
    old = _old_dir(home)
    (old / "browser.json").write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
    (old / ".browser-profile").mkdir()

    r = common_state.migrate_launch(proj)
    assert "browser.json" not in r["moved"] and ".browser-profile" not in r["moved"]
    assert any("브라우저" in w for w in r["warnings"])
    # 옛 자리를 계속 읽는다 — 기능이 멈추지 않는다
    assert common_state.launch_file(proj, "browser.json") == old / "browser.json"


def test_migration_is_reported_in_the_output(tmp_path):
    home = tmp_path / "home"
    proj = _repo(tmp_path)
    _old_dir(home)
    _, out, _ = run_cli("access", "show", "--root", str(proj), home=home)
    d = _j(out)
    assert "access.json" in d.get("migrated", []), d
    assert d["access"] == {"base_url": "http://x"}, "옮긴 기록을 읽지 못했다"
    _, out, _ = run_cli("access", "show", "--root", str(proj), home=home)
    assert "migrated" not in _j(out), "두 번째에도 옮겼다고 한다"


def test_venv_falls_back_to_the_old_place(tmp_path, monkeypatch):
    """옛 venv 를 옮기지 않는다 — 약 100MB 를 다시 받게 만들 이유가 없다."""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    old = home / ".projectops" / "agent-test" / ".venv" / "bin"
    old.mkdir(parents=True)
    (old / "python").write_text("", encoding="utf-8")
    if os.name == "nt":
        pytest.skip("POSIX venv 구조만 본다")
    assert common_state.venv_dir() == home / ".projectops" / "agent-test" / ".venv"
    new = home / ".projectops" / "launch" / ".venv" / "bin"
    new.mkdir(parents=True)
    (new / "python").write_text("", encoding="utf-8")
    assert common_state.venv_dir() == home / ".projectops" / "launch" / ".venv"


# ── access ───────────────────────────────────────────────────────────────

def test_access_refuses_raw_secret(tmp_path):
    proj = _repo(tmp_path)
    _, out, _ = run_cli("access", "set", "--root", str(proj), "--key", "db",
                        "--json", '{"password": "hunter2supersecret"}', home=tmp_path)
    d = _j(out)
    assert d["code"] == "secret_in_value" and "hunter2" not in json.dumps(d["found"])


def test_access_roundtrip(tmp_path):
    proj = _repo(tmp_path)
    run_cli("access", "set", "--root", str(proj), "--key", "db",
            "--json", '{"how":"direct","password_env":"DB_PASSWORD"}', home=tmp_path)
    _, out, _ = run_cli("access", "show", "--root", str(proj), home=tmp_path)
    assert _j(out)["access"]["db"]["password_env"] == "DB_PASSWORD"
    _, out, _ = run_cli("access", "unset", "--root", str(proj), "--key", "db", home=tmp_path)
    assert _j(out)["access"] == {}


# ── 캡처 줄이기 ───────────────────────────────────────────────────────────

def test_webp_conversion_survives_without_any_tool(tmp_path, monkeypatch):
    png = tmp_path / "x.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    monkeypatch.setattr(common_image, "has_pillow", lambda: False)
    monkeypatch.setattr(common_image, "venv_python", lambda: None)
    monkeypatch.setattr(common_image.shutil, "which", lambda _n: None)
    assert common_image.to_webp(png) is None
    assert png.exists(), "변환에 실패했다고 원본을 지우면 안 된다"


def test_doctor_tells_how_screens_are_shrunk(tmp_path):
    _, out, _ = run_cli("doctor", "--root", str(_repo(tmp_path)), home=tmp_path)
    d = _j(out)
    assert d["image_resize"] and "browser" in d and d["state_dir"]


# ── 산출물 자리 (#611) ────────────────────────────────────────────────────

def test_output_path_lands_under_the_umbrella(tmp_path):
    proj = _repo(tmp_path)
    rc, out, err = run_cli("get-output-path", "--title", "화면 캡처", cwd=proj, home=tmp_path)
    assert rc == 0, out + err
    d = _j(out)
    umbrella = (proj / "docs" / "projectops" / "launch").resolve()
    assert Path(d["run_dir"]).resolve().parent == umbrella
    assert Path(d["screenshots"]).is_dir() and Path(d["env_file"]).is_file()


def test_evidence_folder_is_really_untracked(tmp_path):
    proj = _repo(tmp_path)
    _, out, _ = run_cli("get-output-path", "--title", "추적 제외", cwd=proj, home=tmp_path)
    d = _j(out)
    (Path(d["screenshots"]) / "01.png").write_bytes(b"\x89PNG" + b"0" * 4096)
    subprocess.run(["git", "-C", str(proj), "add", "-A"], check=True)
    staged = subprocess.run(["git", "-C", str(proj), "diff", "--cached", "--name-only"],
                            capture_output=True, text=True, check=True).stdout.split()
    assert staged == ["docs/projectops/launch/.gitignore"], staged


def test_output_path_does_not_touch_root_gitignore(tmp_path):
    proj = _repo(tmp_path)
    (proj / ".gitignore").write_text("build/\n", encoding="utf-8")
    run_cli("get-output-path", "--title", "루트 보존", cwd=proj, home=tmp_path)
    assert (proj / ".gitignore").read_text(encoding="utf-8") == "build/\n"


def test_output_path_can_run_twice(tmp_path):
    proj = _repo(tmp_path)
    _, o1, _ = run_cli("get-output-path", "--title", "두 번", cwd=proj, home=tmp_path)
    _, o2, _ = run_cli("get-output-path", "--title", "두 번", cwd=proj, home=tmp_path)
    assert _j(o1)["gitignore"] == "created" and _j(o2)["gitignore"] == "already"


def test_output_path_refuses_a_document_skill(tmp_path):
    """문서 스킬 폴더에 캡처를 쌓으면 추적 제외가 없어 커밋된다."""
    proj = _repo(tmp_path)
    _, out, _ = run_cli("get-output-path", "--skill", "report", cwd=proj, home=tmp_path)
    assert _j(out)["code"] == "not_evidence_skill"


def test_output_path_for_a_calling_skill_names_its_run(tmp_path):
    """부르는 작업 스킬 폴더에 받고, 실행 변수도 그 스킬 이름을 쓴다."""
    proj = _repo(tmp_path)
    _, out, _ = run_cli("get-output-path", "--skill", "agent-test", "--title", "x",
                        cwd=proj, home=tmp_path)
    d = _j(out)
    assert "/agent-test/" in d["run_dir"].replace("\\", "/")
    body = Path(d["env_file"]).read_text(encoding="utf-8")
    assert "export AGENT_TEST_RUN=" in body and "LAUNCH_RUN" not in body


def test_env_sh_points_inside_the_run(tmp_path):
    proj = _repo(tmp_path)
    _, out, _ = run_cli("get-output-path", "--title", "하네스", "--package", "com.acme.x",
                        cwd=proj, home=tmp_path)
    d = _j(out)
    body = Path(d["env_file"]).read_text(encoding="utf-8")
    assert "export LAUNCH_RUN=" in body and "export SHOT_DIR=" in body
    assert "export PKG='com.acme.x'" in body
    assert str(Path(d["screenshots"]).resolve()) in body
    assert re.search(r"^export DEV=", body, re.M), "DEV 가 없으면 adb -s 가 죽는다"


# ── 역할 ↔ 기기 (#583) ────────────────────────────────────────────────────

def _env_of(tmp: Path, *bind_args):
    proj = _repo(tmp)
    _, out, _ = run_cli("get-output-path", "--title", "역할", cwd=proj, home=tmp)
    run_dir = Path(_j(out)["run_dir"])
    for args in bind_args:
        run_cli("device", "bind", "--root", str(proj), *args, cwd=proj, home=tmp,
                env_extra={"RUN_DIR": str(run_dir)})
    f = run_dir / "env.sh"
    return proj, run_dir, f, f.read_text(encoding="utf-8")


def test_role_names_never_become_shell_variable_names(tmp_path):
    _, _, _, body = _env_of(tmp_path,
                            ["--role", "A", "--serial", "emulator-5554", "--note", "만드는 쪽"],
                            ["--role", "받는 쪽", "--serial", "emulator-5556"],
                            ["--role", "it's-a/role", "--serial", "emulator-5558"])
    names = re.findall(r"\bexport ([^=\s]+)=", body)
    assert names and [n for n in names if not _SH_NAME.match(n)] == []
    assert "받는 쪽" in body


@pytest.mark.skipif(not shutil.which("bash"), reason="bash 가 없는 환경")
def test_env_sh_actually_sources_in_bash(tmp_path):
    _, _, env_file, _ = _env_of(tmp_path,
                                ["--role", "A", "--serial", "emulator-5554"],
                                ["--role", "받는 쪽", "--serial", "emulator-5556", "--note", "it's B"],
                                ["--role", "it's-a/role", "--serial", "emulator-5558"])
    r = subprocess.run(["bash", "-c", f'source "{env_file}"; echo "$ROLE2|$ROLE3|$DEV2|$DEV_COUNT|$DEV"'],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "받는 쪽|it's-a/role|emulator-5556|3|emulator-5554"


def test_binding_order_and_unbind(tmp_path):
    proj, run_dir, env_file, body = _env_of(tmp_path, ["--role", "A", "--serial", "s-a"],
                                            ["--role", "B", "--serial", "s-b"])
    assert "export ROLE1='A'; export DEV1='s-a'" in body
    run_cli("device", "unbind", "--root", str(proj), "--role", "A", cwd=proj, home=tmp_path,
            env_extra={"RUN_DIR": str(run_dir)})
    after = env_file.read_text(encoding="utf-8")
    assert "export ROLE1='B'; export DEV1='s-b'" in after and "export DEV2=" not in after
    # 스킬 이름은 처음 쓴 것을 이어받는다
    assert "export LAUNCH_RUN=" in after


def test_package_is_kept_when_bindings_change(tmp_path):
    _, _, env_file, _ = _env_of(tmp_path, ["--role", "A", "--serial", "s-a", "--package", "com.acme.x"])
    assert "com.acme.x" in env_file.read_text(encoding="utf-8")


def test_build_mismatch_needs_hashes_not_versions():
    found = launch_cli._build_mismatch([
        {"role": "A", "build": {"apk": "aaa", "version": "1.2.0+45"}},
        {"role": "B", "build": {"apk": "bbb", "version": "1.2.0+45"}}])
    assert found and "한쪽만 다시 설치" in found[0]["detail"]
    assert launch_cli._build_mismatch([
        {"role": "A", "build": {"apk": "aaa"}}, {"role": "B", "build": {"apk": None}}]) == []


# ── app ──────────────────────────────────────────────────────────────────

_DEV2 = {"android": ["emulator-5554"],
         "ios_booted": ["iPhone 16 [3F328F1A-16D1-453B-A0D3-94CDC21C4189]"],
         "android_avds": [], "adb_path": "/x/adb", "emulator_path": None}


def test_pick_device_refuses_to_guess_between_several(monkeypatch):
    """여러 대인데 고르지 않으면 엉뚱한 기기를 찍는다 — 멈춘다."""
    monkeypatch.setattr(launch_cli, "_devices", lambda: _DEV2)
    monkeypatch.delenv("DEV", raising=False)
    assert launch_cli._pick_device(None)[0] is None
    assert launch_cli._pick_device("emulator-5554")[:2] == ("android", "emulator-5554")
    assert launch_cli._pick_device("3F328F1A-16D1-453B-A0D3-94CDC21C4189")[0] == "ios"
    monkeypatch.setenv("DEV", "emulator-5554")
    assert launch_cli._pick_device(None)[1] == "emulator-5554"


def _shot_args(tmp, **over):
    import argparse
    a = argparse.Namespace(root=str(tmp), device="emulator-5554", out="s1", clean_status=False,
                           keep_format=True, max_side=0, quality=75)
    for k, v in over.items():
        setattr(a, k, v)
    return a


def test_android_shot_writes_png_and_restores_demo_mode(tmp_path, monkeypatch, capsys):
    """상태바를 고정했으면 찍은 뒤 되돌린다 — 남의 기기 설정을 바꿔 두지 않는다."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SHOT_DIR", str(tmp_path / "shots"))
    monkeypatch.setattr(launch_cli, "_devices", lambda: _DEV2)
    monkeypatch.setattr(launch_cli, "sdk_tool", lambda n: "/x/adb")
    calls = []
    monkeypatch.setattr(launch_cli, "_adb_shell",
                        lambda serial, *a, **k: calls.append(a) or ("null" if a[:2] == ("settings", "get") else ""))

    class R:
        stdout = b"\x89PNG\r\n\x1a\nfake"
        stderr = b""
    monkeypatch.setattr(launch_cli.subprocess, "run", lambda *a, **k: R())
    monkeypatch.setattr(launch_cli.time, "sleep", lambda s: None)

    rc = launch_cli._app_shot(_shot_args(tmp_path, clean_status=True))
    d = json.loads(capsys.readouterr().out)
    assert rc == 0 and d["platform"] == "android"
    assert Path(d["file"]).read_bytes().startswith(b"\x89PNG")
    flat = [" ".join(c) for c in calls]
    assert any("command enter" in c for c in flat)
    assert any("command exit" in c for c in flat), "데모 모드를 끄지 않았다"
    assert "settings delete global sysui_demo_allowed" in flat, "허용 설정을 원래대로 돌리지 않았다"


def test_android_shot_rejects_a_non_png(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SHOT_DIR", str(tmp_path / "shots"))
    monkeypatch.setattr(launch_cli, "_devices", lambda: _DEV2)
    monkeypatch.setattr(launch_cli, "sdk_tool", lambda n: "/x/adb")

    class R:
        stdout = b"error: device offline"
        stderr = b""
    monkeypatch.setattr(launch_cli.subprocess, "run", lambda *a, **k: R())
    launch_cli._app_shot(_shot_args(tmp_path))
    assert json.loads(capsys.readouterr().out)["code"] == "capture_failed"


# ── web viewport · route (브라우저 없이 기록된다) ──────────────────────────

def _root_for_web(tmp):
    return _repo(tmp, "webproj", remote=None)


def test_viewport_presets_and_custom(tmp_path):
    proj = _root_for_web(tmp_path)
    _, out, _ = run_cli("web", "viewport", "--root", str(proj), "--preset", "mobile", home=tmp_path)
    assert _j(out)["viewport"] == [390, 844]
    _, out, _ = run_cli("web", "viewport", "--root", str(proj), "--preset", "700x500", home=tmp_path)
    assert _j(out)["viewport"] == [700, 500]
    _, out, _ = run_cli("web", "viewport", "--root", str(proj), "--preset", "huge", home=tmp_path)
    assert _j(out)["code"] == "bad_viewport"


def test_route_rules_are_saved_replaced_and_cleared(tmp_path):
    proj = _root_for_web(tmp_path)
    body = tmp_path / "empty.json"
    body.write_text("[]", encoding="utf-8")
    run_cli("web", "route", "--root", str(proj), "--match", "**/api/items*",
            "--status", "200", "--body", str(body), home=tmp_path)
    run_cli("web", "route", "--root", str(proj), "--match", "**/api/items*",
            "--status", "500", "--body", "oops", home=tmp_path)
    _, out, _ = run_cli("web", "route", "--root", str(proj), home=tmp_path)
    rules = _j(out)["routes"]
    assert len(rules) == 1, "같은 주소 규칙이 쌓였다"
    assert rules[0]["status"] == 500 and rules[0]["content_type"].startswith("text/plain")
    _, out, _ = run_cli("web", "route", "--root", str(proj), "--clear", home=tmp_path)
    _, out, _ = run_cli("web", "route", "--root", str(proj), home=tmp_path)
    assert _j(out)["routes"] == []


def test_route_needs_a_status_or_a_delay(tmp_path):
    proj = _root_for_web(tmp_path)
    _, out, _ = run_cli("web", "route", "--root", str(proj), "--match", "**/x", home=tmp_path)
    assert _j(out)["code"] == "missing_argument"


def test_route_handler_takes_the_request_as_second_argument():
    """Playwright 는 handler(route, request) 로 부른다. 기본 인자로 규칙을 묶으면 request 가 덮는다 (실측)."""
    got = {}

    class FakeRoute:
        def fulfill(self, **kw):
            got.update(kw)

        def continue_(self):
            got["continued"] = True

    h = launch_cli._route_handler({"status": 500, "body": "x", "content_type": "text/plain"})
    h(FakeRoute(), object())
    assert got["status"] == 500 and got["body"] == "x"

    got.clear()
    launch_cli._route_handler({"status": None, "delay_ms": 0})(FakeRoute(), object())
    assert got == {"continued": True}


# ── http ─────────────────────────────────────────────────────────────────

def _serve_json(status: int, body: bytes):
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        do_GET = do_POST = _send
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_port}", srv.shutdown


def test_http_returns_failures_as_results(tmp_path):
    """500 도 결과다 — 예외로 끝내지 않는다."""
    base, stop = _serve_json(500, b'{"error":"boom"}')
    try:
        _, out, _ = run_cli("http", "--url", base + "/x", "--root", str(_root_for_web(tmp_path)),
                            "--header", "Authorization: Bearer secret-token", home=tmp_path)
        d = _j(out)
        assert d["ok"] is True and d["status"] == 500 and d["json"] == {"error": "boom"}
        assert "secret-token" not in out, "요청 헤더 값이 결과에 남았다"
        _, out, _ = run_cli("http", "--url", base + "/x", "--expect-status", "200",
                            "--root", str(_root_for_web(tmp_path)), home=tmp_path)
        assert _j(out)["code"] == "unexpected_status"
    finally:
        stop()


def test_http_relative_url_uses_recorded_base(tmp_path):
    proj = _root_for_web(tmp_path)
    _, out, _ = run_cli("http", "--url", "/health", "--root", str(proj), home=tmp_path)
    assert _j(out)["code"] == "base_url_required"
    base, stop = _serve_json(200, b'{"ok":1}')
    try:
        run_cli("access", "set", "--root", str(proj), "--key", "base_url",
                "--json", json.dumps({"url": base}), home=tmp_path)
        _, out, _ = run_cli("http", "--url", "/health", "--method", "POST", "--data", '{"a":1}',
                            "--root", str(proj), home=tmp_path)
        d = _j(out)
        assert d["status"] == 200 and d["url"] == base + "/health"
    finally:
        stop()


# ── stealth (gstack 이식) ─────────────────────────────────────────────────

def test_stealth_hides_the_automation_flag_at_launch():
    """실행 인자라야 연결을 끊은 뒤 뜨는 로그인 팝업에도 걸린다."""
    args = stealth.launch_args(sys.executable)   # --version 을 못 읽어도 폴백 UA 가 나와야 한다
    assert "--disable-blink-features=AutomationControlled" in args
    ua = [a for a in args if a.startswith("--user-agent=")][0]
    assert "HeadlessChrome" not in ua and "Chrome/" in ua


def test_stealth_scripts_cover_the_checked_tells():
    joined = "\n".join(stealth.init_scripts())
    for needle in ("'webdriver'", "chrome.runtime", "Notification", "cdc_",
                   "permissions.query", "[native code]"):
        assert needle in joined, f"{needle} 을 다루지 않는다"
    assert "__HW_CONCURRENCY__" not in joined, "자리표시자가 남았다"


def test_stealth_keeps_the_upstream_license():
    """MIT — 옮겨 온 쪽의 저작권 고지를 지워서는 안 된다."""
    text = Path(stealth.__file__).read_text(encoding="utf-8")
    assert "Copyright (c) 2026 Garry Tan" in text and "MIT License" in text


def test_console_hook_covers_every_way_an_error_shows_up():
    hook = launch_cli._CONSOLE_HOOK
    assert 'addEventListener("error"' in hook and 'addEventListener("unhandledrejection"' in hook
    assert "if (window.__projectops_console) return;" in hook


# ── 진짜 브라우저 (local_only) ────────────────────────────────────────────

_PAGE = (
    b'<!doctype html><meta charset="utf-8"><title>t</title>'
    b'<input id="v"><button id="go" onclick="document.getElementById(\'out\').textContent='
    b'document.getElementById(\'v\').value">go</button><p id="out"></p><ul id="l"></ul>'
    b'<p id="bot"></p><script>'
    b'document.getElementById("bot").textContent="webdriver="+navigator.webdriver+'
    b'" headless="+/Headless/.test(navigator.userAgent);'
    b'console.error("LOAD_ERROR_MARK");'
    b'fetch("/api/items").then(r=>{if(!r.ok)throw new Error("HTTP "+r.status);return r.json()})'
    b'.then(xs=>{document.getElementById("l").textContent=xs.length?"n="+xs.length:"EMPTY_MARK"})'
    b'.catch(e=>{document.getElementById("l").textContent="FAIL_MARK "+e.message});'
    b'</script>')


@contextlib.contextmanager
def _browser_session(tmp_path):
    ok, _ = launch_cli._require_playwright()
    if ok is None:
        pytest.skip("Playwright 없음 — web setup 후 실행된다")

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = b'["a","b"]' if self.path.startswith("/api/") else _PAGE
            ctype = "application/json" if self.path.startswith("/api/") else "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    # HOME 은 그대로 — 원격 없는 임시 레포로 상태 폴더만 나눈다
    proj = _repo(tmp_path, f"launchtest-{os.getpid()}", remote=None)
    state = common_state.state_dir("launch", proj)
    try:
        yield proj, f"http://127.0.0.1:{srv.server_port}/"
    finally:
        run_cli("web", "close", "--root", str(proj))
        srv.shutdown()
        shutil.rmtree(state, ignore_errors=True)


@pytest.mark.local_only
def test_web_walks_real_browser_across_separate_calls(tmp_path):
    """호출이 쪼개져도 같은 브라우저에 붙는지가 이 설계의 전부다."""
    with _browser_session(tmp_path) as (proj, url):
        r = str(proj)
        assert _j(run_cli("web", "open", "--root", r, "--url", url)[1]).get("ok"), "열지 못했다"
        run_cli("web", "type", "--root", r, "--selector", "#v", "--text", "남아야 한다")
        run_cli("web", "click", "--root", r, "--selector", "#go")
        assert _j(run_cli("web", "assert", "--root", r, "--text", "남아야 한다")[1])["ok"] is True
        # stealth 가 켜져 있으면 자동화 표식이 없다
        assert _j(run_cli("web", "assert", "--root", r, "--text", "webdriver=false headless=false")[1])["ok"]
        d = _j(run_cli("web", "console", "--root", r)[1])
        assert "LOAD_ERROR_MARK" in " ".join(l["text"] for l in d["logs"]), "로드 중 오류를 놓쳤다"


@pytest.mark.local_only
def test_route_stages_empty_and_failing_states(tmp_path):
    """서버를 건드리지 않고 빈 목록·실패를 연출한다. 폭도 바꿔 찍는다."""
    with _browser_session(tmp_path) as (proj, url):
        r = str(proj)
        run_cli("web", "open", "--root", r, "--url", url)
        assert _j(run_cli("web", "assert", "--root", r, "--text", "n=2")[1])["ok"], "진짜 응답이 안 보인다"

        run_cli("web", "route", "--root", r, "--match", "**/api/items", "--status", "200", "--body", "[]")
        run_cli("web", "goto", "--root", r, "--url", url)
        assert _j(run_cli("web", "assert", "--root", r, "--text", "EMPTY_MARK")[1])["ok"], "빈 목록을 연출하지 못했다"

        run_cli("web", "route", "--root", r, "--match", "**/api/items", "--status", "500", "--body", "{}")
        run_cli("web", "viewport", "--root", r, "--preset", "mobile")
        run_cli("web", "goto", "--root", r, "--url", url)
        assert _j(run_cli("web", "assert", "--root", r, "--text", "FAIL_MARK HTTP 500")[1])["ok"]
        shot = _j(run_cli("web", "shot", "--root", r, "--out", str(tmp_path / "m.png"))[1])
        from PIL import Image
        with Image.open(shot["file"]) as im:
            assert im.width == 390, f"모바일 폭이 아니다: {im.size}"

        run_cli("web", "route", "--root", r, "--clear")
        run_cli("web", "goto", "--root", r, "--url", url)
        assert _j(run_cli("web", "assert", "--root", r, "--text", "n=2")[1])["ok"], "규칙을 지웠는데 남아 있다"


@pytest.mark.local_only
def test_hook_survives_navigation_driven_by_a_later_call(tmp_path):
    """훅은 연결이 끊기면 사라진다 — 붙을 때마다 다시 심지 않으면 조용히 빈다 (#625 실측)."""
    with _browser_session(tmp_path) as (proj, url):
        r = str(proj)
        run_cli("web", "open", "--root", r)                  # 빈 탭으로 연다
        run_cli("web", "goto", "--root", r, "--url", url)    # 별도 호출로 이동
        d = _j(run_cli("web", "console", "--root", r)[1])
        assert d.get("code") != "console_hook_missing", d
        assert "LOAD_ERROR_MARK" in " ".join(l["text"] for l in d["logs"]), d

