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
    assert c.main(["resolve", "--platform", "android", "--file", str(cfg)]) == 0
    assert env.read_text(encoding="utf-8") == "DEPLOY_MODE=store_prepare\n"

    cfg.write_text(json.dumps({"android": {"deploy_mode": "nope"}}), encoding="utf-8")
    assert c.main(["resolve", "--platform", "android", "--file", str(cfg)]) == 1
