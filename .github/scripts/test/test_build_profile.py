"""apply_build_profile.py 계약 테스트 (#603).

**이 스크립트가 틀리면 개발 도구가 켜진 앱이 스토어에 나간다.** 그래서
"되는 경우"보다 "막아야 하는 경우"를 더 많이 본다.

가장 중요한 것은 맨 위 두 개다 — 설정이 없는 저장소에서 아무 일도 일어나지
않아야 한다. 이 템플릿은 남의 저장소에 설치되고, 그중 대부분은 프로파일을
쓰지 않는다.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "apply_build_profile.py"


def run(profile, env_file, config=None, cwd=None, github_output=None):
    cmd = [sys.executable, str(SCRIPT), profile, str(env_file)]
    if config is not None:
        cmd += ["--config", str(config)]
    env = None
    if github_output is not None:
        import os
        env = {**os.environ, "GITHUB_OUTPUT": str(github_output)}
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", cwd=cwd, env=env)


def write_config(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def cfg(tmp_path):
    return write_config(tmp_path / "build-profile.json", {
        "dev_keys": ["APP_SHOW_DEV_TOOLS", "APP_ENABLE_NETWORK_LOG"],
        "secret_keys": ["APP_DEV_ACCESS_TOKEN"],
        "profiles": {
            "test": {"env": {"APP_SHOW_DEV_TOOLS": "true"},
                     "dart_define": {"APP_FLAVOR": "dev"}},
            "release": {"env": {"APP_SHOW_DEV_TOOLS": "false"},
                        "dart_define": {}},
        },
    })


@pytest.fixture
def envf(tmp_path):
    f = tmp_path / ".env"
    f.write_text("API_URL=https://example.com\n", encoding="utf-8")
    return f


# ── 설정이 없는 저장소 — 아무것도 하지 않는다 ────────────────────────

def test_missing_config_changes_nothing_and_succeeds(tmp_path, envf):
    before = envf.read_text(encoding="utf-8")
    r = run("test", envf, config=tmp_path / "없는파일.json")
    assert r.returncode == 0
    assert envf.read_text(encoding="utf-8") == before


def test_missing_config_emits_empty_flags(tmp_path, envf):
    out = tmp_path / "gh_out"
    out.touch()
    run("test", envf, config=tmp_path / "없는파일.json", github_output=out)
    assert out.read_text(encoding="utf-8").strip() == "build_flags="


# ── 두 층이 함께 적용된다 ────────────────────────────────────────────

def test_test_profile_sets_env_and_flags(tmp_path, cfg, envf):
    out = tmp_path / "gh_out"
    out.touch()
    r = run("test", envf, config=cfg, github_output=out)
    assert r.returncode == 0
    assert "APP_SHOW_DEV_TOOLS=true" in envf.read_text(encoding="utf-8")
    assert out.read_text(encoding="utf-8").strip() == \
        "build_flags=--dart-define=APP_FLAVOR=dev"


def test_existing_values_are_preserved(tmp_path, cfg, envf):
    run("test", envf, config=cfg)
    assert "API_URL=https://example.com" in envf.read_text(encoding="utf-8")


def test_release_profile_produces_no_flags(tmp_path, cfg, envf):
    out = tmp_path / "gh_out"
    out.touch()
    r = run("release", envf, config=cfg, github_output=out)
    assert r.returncode == 0
    assert out.read_text(encoding="utf-8").strip() == "build_flags="


# ── 막아야 하는 것 ───────────────────────────────────────────────────

def test_release_fails_when_a_dev_key_is_left_on(tmp_path, envf):
    """Secret 이 개발 키를 켠 채 들어와도 배포 빌드는 서야 한다."""
    cfg = write_config(tmp_path / "c.json", {
        "dev_keys": ["APP_SHOW_DEV_TOOLS"],
        # release 프로파일이 이 키를 명시하지 않는다 → 걷어내기만 하고 끝
        "profiles": {"release": {"env": {}, "dart_define": {}}},
    })
    envf.write_text("APP_SHOW_DEV_TOOLS=true\n", encoding="utf-8")
    r = run("release", envf, config=cfg)
    # 걷어냈으므로 통과해야 한다 — 이것이 strip 의 존재 이유다
    assert r.returncode == 0
    assert "APP_SHOW_DEV_TOOLS=true" not in envf.read_text(encoding="utf-8")


def test_release_fails_when_profile_itself_turns_a_dev_key_on(tmp_path, envf):
    """설정을 잘못 적어 배포 프로파일이 개발 키를 켜면 빌드를 세운다."""
    cfg = write_config(tmp_path / "c.json", {
        "dev_keys": ["APP_SHOW_DEV_TOOLS"],
        "profiles": {"release": {"env": {"APP_SHOW_DEV_TOOLS": "true"},
                                 "dart_define": {}}},
    })
    r = run("release", envf, config=cfg)
    assert r.returncode == 1
    assert "개발 키가 켜져 있습니다" in r.stderr
    assert "APP_SHOW_DEV_TOOLS" in r.stderr


def test_release_fails_when_a_qa_token_survives(tmp_path, envf):
    cfg = write_config(tmp_path / "c.json", {
        "secret_keys": ["APP_DEV_ACCESS_TOKEN"],
        "profiles": {"release": {"env": {"APP_DEV_ACCESS_TOKEN": "leftover"},
                                 "dart_define": {}}},
    })
    r = run("release", envf, config=cfg)
    assert r.returncode == 1
    assert "비밀값이 남아 있습니다" in r.stderr


def test_release_fails_when_a_test_only_flag_leaks_in(tmp_path, envf):
    """.env 가 깨끗해도 컴파일타임이 뚫리면 개발 빌드가 나간다."""
    cfg = write_config(tmp_path / "c.json", {
        "profiles": {
            "test": {"dart_define": {"APP_FLAVOR": "dev"}},
            "release": {"dart_define": {"APP_FLAVOR": "dev"}},  # 실수로 같은 값
        },
    })
    r = run("release", envf, config=cfg)
    assert r.returncode == 1
    assert "테스트 전용 플래그" in r.stderr


def test_release_allows_its_own_dart_define(tmp_path, envf):
    """배포 프로파일이 자기 값을 쓰는 것은 위반이 아니다."""
    cfg = write_config(tmp_path / "c.json", {
        "profiles": {
            "test": {"dart_define": {"APP_FLAVOR": "dev"}},
            "release": {"dart_define": {"APP_FLAVOR": "prod"}},
        },
    })
    r = run("release", envf, config=cfg)
    assert r.returncode == 0


# ── 조용히 넘어가면 안 되는 것 ───────────────────────────────────────

def test_unknown_profile_is_refused(tmp_path, cfg, envf):
    r = run("스테이징", envf, config=cfg)
    assert r.returncode == 1
    assert "알 수 없는 프로파일" in r.stderr
    assert "test" in r.stderr and "release" in r.stderr   # 뭐가 있는지 알려준다


def test_broken_config_is_refused_not_ignored(tmp_path, envf):
    bad = tmp_path / "bad.json"
    bad.write_text("{ 이건 json이 아니다", encoding="utf-8")
    r = run("test", envf, config=bad)
    assert r.returncode == 1
    assert "읽을 수 없습니다" in r.stderr


def test_missing_env_file_is_refused(tmp_path, cfg):
    r = run("test", tmp_path / "없는.env", config=cfg)
    assert r.returncode == 1
    assert ".env 파일이 없습니다" in r.stderr


# ── 로그 위생 ────────────────────────────────────────────────────────

def test_token_values_never_reach_the_log(tmp_path, envf):
    """빌드 로그는 누구나 본다. 값이 찍히면 그대로 유출이다."""
    cfg = write_config(tmp_path / "c.json", {
        "secret_keys": ["APP_DEV_ACCESS_TOKEN"],
        "profiles": {"test": {"env": {"APP_DEV_ACCESS_TOKEN": "s3cr3t-value"},
                              "dart_define": {}}},
    })
    r = run("test", envf, config=cfg)
    assert r.returncode == 0
    assert "s3cr3t-value" not in r.stderr
    assert "s3cr3t-value" not in r.stdout
    assert "(설정됨)" in r.stderr


def test_keys_are_not_written_twice(tmp_path, cfg, envf):
    """두 번 돌려도 같은 키가 쌓이지 않는다 — 워크플로가 재실행될 수 있다."""
    run("test", envf, config=cfg)
    run("test", envf, config=cfg)
    body = envf.read_text(encoding="utf-8")
    assert body.count("APP_SHOW_DEV_TOOLS=") == 1


def test_switching_profiles_does_not_leave_the_old_value(tmp_path, cfg, envf):
    run("test", envf, config=cfg)
    run("release", envf, config=cfg)
    body = envf.read_text(encoding="utf-8")
    assert "APP_SHOW_DEV_TOOLS=false" in body
    assert "APP_SHOW_DEV_TOOLS=true" not in body
