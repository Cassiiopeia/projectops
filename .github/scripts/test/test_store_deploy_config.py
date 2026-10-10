"""스토어 배포 설정 파일 우선순위와 검증 (#767)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import store_deploy_config as c  # noqa: E402


def test_파일이_없으면_아무것도_적용하지_않는다():
    assert c.resolve(None, "android") == {}
    assert c.load("/no/such/file.json") is None


def test_파일_값이_적용된다():
    data = {"android": {"deploy_mode": "store_prepare", "production_rollout": "0.1"}}
    assert c.resolve(data, "android") == {"DEPLOY_MODE": "store_prepare", "PRODUCTION_ROLLOUT": "0.1"}


def test_수동_실행_입력이_있으면_모드는_파일보다_우선한다():
    data = {"android": {"deploy_mode": "store_submit", "production_rollout": "0.5"}}
    got = c.resolve(data, "android", input_deploy_mode="store_only")
    assert "DEPLOY_MODE" not in got          # 입력이 이긴다
    assert got["PRODUCTION_ROLLOUT"] == "0.5"  # 비율은 입력이 없으니 파일을 따른다


def test_플랫폼별로_분리된다():
    data = {"android": {"deploy_mode": "store_submit"}, "ios": {"deploy_mode": "store_only"}}
    assert c.resolve(data, "ios") == {"DEPLOY_MODE": "store_only"}


@pytest.mark.parametrize("bad", [
    {"android": {"deploy_mode": "store_submt"}},                 # 오타
    {"android": {"production_rollout": "0"}},                    # 범위 밖
    {"android": {"production_rollout": "1.5"}},
    {"android": {"production_rollout": "abc"}},
    {"ios": {"production_rollout": "0.5"}},                      # iOS 에는 없는 개념
])
def test_잘못된_값은_조용히_무시하지_않고_실패한다(bad):
    plat = "ios" if "ios" in bad else "android"
    with pytest.raises(c.ConfigError):
        c.resolve(bad, plat)


def test_main은_GITHUB_ENV에_쓰고_잘못된_설정은_종료코드_1(tmp_path, monkeypatch):
    cfg = tmp_path / "store-deploy.json"
    cfg.write_text(json.dumps({"android": {"deploy_mode": "store_prepare"}}), encoding="utf-8")
    env = tmp_path / "env"
    monkeypatch.setenv("GITHUB_ENV", str(env))
    monkeypatch.delenv("INPUT_DEPLOY_MODE", raising=False)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")   # 수동 실행이면 파일 값 그대로
    assert c.main(["resolve", "--platform", "android", "--file", str(cfg)]) == 0
    assert env.read_text(encoding="utf-8") == "DEPLOY_MODE=store_prepare\n"

    cfg.write_text(json.dumps({"android": {"deploy_mode": "nope"}}), encoding="utf-8")
    assert c.main(["resolve", "--platform", "android", "--file", str(cfg)]) == 1


# ── push 배포는 심사 단계를 타지 않는다 (#816) ─────────────────────────────
# Google Play 는 심사 중에 새 변경이 오면 그 심사에 합쳐 다시 심사한다 (2026-10-10 EarLocAlert 실측 —
# 제출 #44 에 ERROR_IF_IN_REVIEW 로 보낸 변경이 오류 없이 합쳐져 그대로 출시됐다).

@pytest.mark.parametrize("platform", ["android", "ios"])
@pytest.mark.parametrize("mode", ["store_prepare", "store_submit", "appstore_submit"])
def test_push_에서는_심사_단계를_store_only_로_낮춘다(platform, mode):
    override, note = c.push_policy(None, platform, "push", mode)
    assert override == {"DEPLOY_MODE": "store_only"}
    assert "수동 실행" in note and "auto_submit_on_push" in note


def test_수동_실행에서는_고른_모드를_그대로_둔다():
    assert c.push_policy(None, "android", "workflow_dispatch", "store_submit") == ({}, None)


def test_auto_submit_on_push_를_명시한_레포만_push_에서도_제출한다():
    data = {"android": {"auto_submit_on_push": True}}
    override, note = c.push_policy(data, "android", "push", "store_submit")
    assert override == {} and "auto_submit_on_push" in note


def test_store_only_는_push_에서도_그대로다():
    assert c.push_policy(None, "ios", "push", "store_only") == ({}, None)


def test_레포_변수로_들어온_store_submit_도_push_에서는_막는다(tmp_path, monkeypatch):
    """EarLocAlert 실사고 경로 — 설정 파일이 아니라 레포 변수(ANDROID_DEPLOY_MODE)가 store_submit 이었다."""
    env = tmp_path / "env"
    monkeypatch.setenv("GITHUB_ENV", str(env))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("DEPLOY_MODE", "store_submit")          # 워크플로 env 가 레포 변수에서 받은 값
    monkeypatch.delenv("INPUT_DEPLOY_MODE", raising=False)
    assert c.main(["resolve", "--platform", "android", "--file", str(tmp_path / "none.json")]) == 0
    assert env.read_text(encoding="utf-8") == "DEPLOY_MODE=store_only\n"


def test_비공개_승급_설정과_쿨다운은_android_전용이고_형식을_검사한다():
    assert c.resolve({"android": {"promote_closed_testing": False}}, "android") == {"PROMOTE_TO_CLOSED_TESTING": "false"}
    for bad in ({"android": {"promote_closed_testing": "yes"}}, {"android": {"auto_submit_on_push": 1}},
                {"ios": {"promote_closed_testing": True}}, {"android": {"review_cooldown_hours": -1}},
                {"ios": {"review_cooldown_hours": 24}}):
        with pytest.raises(c.ConfigError):
            c.resolve(bad, "android" if "android" in bad else "ios")


def _run(title, event="workflow_dispatch", conclusion="success", updated="2026-10-10T01:00:00Z"):
    return {"display_title": title, "event": event, "conclusion": conclusion, "updated_at": updated,
            "html_url": "https://x/runs/1"}


def test_최근_수동_프로덕션_제출이_있으면_찾는다():
    import datetime as dt
    now = dt.datetime(2026, 10, 11, 1, 0, tzinfo=dt.timezone.utc).timestamp()   # 24시간 뒤
    assert c.recent_production_submit([_run("PLAYSTORE deploy_mode=store_submit")], now, 48)
    assert not c.recent_production_submit([_run("PLAYSTORE deploy_mode=store_submit")], now, 12)   # 지났다
    assert not c.recent_production_submit([_run("PLAYSTORE deploy_mode=store_only")], now, 48)     # 제출 아님
    assert not c.recent_production_submit([_run("PLAYSTORE deploy_mode=store_submit", conclusion="failure")], now, 48)
    assert not c.recent_production_submit([_run("store_submit", event="push")], now, 48)


def test_review_guard_는_수동_실행에서는_아무것도_하지_않는다(monkeypatch, tmp_path):
    env = tmp_path / "env"
    monkeypatch.setenv("GITHUB_ENV", str(env))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("PROMOTE_TO_CLOSED_TESTING", "true")
    assert c.main(["review-guard", "--file", str(tmp_path / "none.json")]) == 0
    assert not env.exists()


def test_review_guard_는_확인에_실패해도_배포를_막지_않는다(monkeypatch, tmp_path):
    env = tmp_path / "env"
    monkeypatch.setenv("GITHUB_ENV", str(env))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("PROMOTE_TO_CLOSED_TESTING", "true")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_WORKFLOW_REF", "o/r/.github/workflows/X.yaml@refs/heads/main")
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("network")))
    assert c.main(["review-guard", "--file", str(tmp_path / "none.json")]) == 0
    assert not env.exists(), "확인 실패로 승급을 끄면 안 된다 — 경고만 남긴다"
