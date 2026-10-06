#!/usr/bin/env python3
"""스토어 배포 설정을 코드(.github/config/store-deploy.json)에서 읽는다 (#767) — stdlib 전용.

배포 모드는 예전에 `수동 실행 입력 || 레포 변수 || 기본값` 순으로 정해졌다. 레포 변수는
GitHub 설정 화면에서만 바꿀 수 있어 변경 이력이 git 에 남지 않고, 레포를 옮기거나 포크하면
따라오지 않아 기본값으로 **조용히** 돌아간다.

우선순위(높은 것부터):
  1. 수동 실행 입력      — 그 실행만
  2. 설정 파일           — 이 스크립트가 읽는다 (git 에 남고 리뷰된다)
  3. 레포 변수           — 기존 방식. 호환을 위해 유지
  4. 기본값(store_only)

설정 파일이 없으면 아무것도 하지 않는다 — 남의 저장소에 설치되는 템플릿이라 기존 동작이 기본이다.
값이 **잘못 적혀 있으면 실패한다.** 오타를 조용히 무시하면 설정이 먹었다고 믿은 채 다른 모드로
배포되고, 이 설정은 프로덕션 심사 자동 등록까지 정하기 때문이다.

설정 (.github/config/store-deploy.json — 마법사가 덮어쓰지 않는 파일):
  {
    "android": { "deploy_mode": "store_only", "production_rollout": "1.0" },
    "ios":     { "deploy_mode": "store_only" }
  }

사용 (워크플로 step):
  python3 .github/scripts/store_deploy_config.py resolve --platform android
  → 적용한 값을 $GITHUB_ENV 에 쓴다. 환경: INPUT_DEPLOY_MODE (수동 실행 입력, 있으면 파일보다 우선)
"""
import argparse
import json
import os
import sys

DEFAULT_PATH = ".github/config/store-deploy.json"
DEPLOY_MODES = {"store_only", "store_prepare", "store_submit",
                # 구 별칭 (Fastfile 이 호환한다)
                "testflight_only", "appstore_prepare", "appstore_submit"}
PLATFORMS = ("android", "ios")


class ConfigError(Exception):
    pass


def load(path: str) -> dict | None:
    """설정을 읽는다. 파일이 없으면 None."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise ConfigError(f"{path} 를 읽을 수 없습니다: {e}")
    if not isinstance(data, dict):
        raise ConfigError(f"{path} 의 최상위는 객체여야 합니다")
    return data


def resolve(data: dict | None, platform: str, input_deploy_mode: str = "") -> dict:
    """파일에서 적용할 값을 정한다. 반환: {환경변수 이름: 값} (적용할 것이 없으면 빈 dict)."""
    if not data or platform not in PLATFORMS:
        return {}
    section = data.get(platform) or {}
    if not isinstance(section, dict):
        raise ConfigError(f"'{platform}' 는 객체여야 합니다")
    out: dict = {}

    mode = section.get("deploy_mode")
    if mode is not None:
        mode = str(mode).strip()
        if mode not in DEPLOY_MODES:
            raise ConfigError(
                f"{platform}.deploy_mode 값 '{mode}' 이 올바르지 않습니다. "
                f"{' | '.join(sorted(DEPLOY_MODES - {'testflight_only', 'appstore_prepare', 'appstore_submit'}))} 중 하나여야 합니다")
        # 수동 실행 입력이 있으면 그 실행만 우선한다
        if not (input_deploy_mode or "").strip():
            out["DEPLOY_MODE"] = mode

    rollout = section.get("production_rollout")
    if rollout is not None:
        if platform != "android":
            raise ConfigError("production_rollout 은 android 에서만 쓴다")
        try:
            value = float(str(rollout).strip())
        except ValueError:
            value = None
        if value is None or not (0 < value <= 1):
            raise ConfigError(f"android.production_rollout 값 '{rollout}' 은 0 초과 1.0 이하의 숫자여야 합니다 (예: 1.0, 0.1)")
        out["PRODUCTION_ROLLOUT"] = str(rollout).strip()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("resolve")
    r.add_argument("--platform", required=True, choices=PLATFORMS)
    r.add_argument("--file", default=DEFAULT_PATH)
    a = ap.parse_args(argv)

    try:
        values = resolve(load(a.file), a.platform, os.environ.get("INPUT_DEPLOY_MODE", ""))
    except ConfigError as e:
        print(f"::error title=store-deploy.json 설정 오류::{e}")
        print(f"❌ {e}", file=sys.stderr)
        return 1

    if not values:
        print("store-deploy.json 에서 적용할 값이 없습니다 (파일이 없거나 수동 입력이 우선) — 레포 변수와 기본값을 따릅니다.")
        return 0
    env_file = os.environ.get("GITHUB_ENV")
    for k, v in values.items():
        print(f"📄 store-deploy.json → {k}={v}")
        if env_file:
            with open(env_file, "a", encoding="utf-8") as f:
                f.write(f"{k}={v}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
