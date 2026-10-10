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

push 배포는 심사 단계를 타지 않는다 (#816):
  Google Play 는 심사 중에 새 변경이 오면 그 심사에 합쳐 다시 심사한다(2026-10-10 EarLocAlert 실측).
  배포마다 프로덕션을 제출하면 심사가 끝나지 않는다. 그래서 push(자동 배포)에서는
  store_prepare · store_submit 을 store_only 로 낮춘다 — 레포 변수·설정 파일에 적혀 있어도 그렇다.
  프로덕션 승급과 App Store 심사는 수동 실행(workflow_dispatch)에서 고른다.
  자동을 원하는 레포만 설정 파일에 "auto_submit_on_push": true 를 명시한다.

비공개 테스트 자동 승급과 프로덕션 심사의 충돌 (#816):
  비공개 테스트 승급도 심사 제출이라, 수동으로 올린 프로덕션 심사가 도는 동안 push 가 비공개 승급을 하면
  프로덕션 심사가 다시 시작된다. Play API 에는 심사 상태가 없어서, 수동 store_submit 실행 뒤
  review_cooldown_hours(기본 48) 동안은 push 의 중간 트랙 승급을 건너뛴다 → review-guard 서브커맨드.
"""
import argparse
import json
import os
import sys

DEFAULT_PATH = ".github/config/store-deploy.json"
# 심사로 이어지는 프로덕션 단계. push 에서는 auto_submit_on_push 없이 쓰지 않는다 (#816).
REVIEW_MODES = {"store_prepare", "store_submit", "appstore_prepare", "appstore_submit"}
DEFAULT_REVIEW_COOLDOWN_HOURS = 48
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

    for key in ("auto_submit_on_push", "promote_closed_testing"):
        v = section.get(key)
        if v is not None and not isinstance(v, bool):
            raise ConfigError(f"{platform}.{key} 는 true 또는 false 여야 합니다 (받은 값: {v!r})")
    if section.get("promote_closed_testing") is not None:
        if platform != "android":
            raise ConfigError("promote_closed_testing 은 android 에서만 쓴다")
        out["PROMOTE_TO_CLOSED_TESTING"] = "true" if section["promote_closed_testing"] else "false"
    hours = section.get("review_cooldown_hours")
    if hours is not None:
        if platform != "android":
            raise ConfigError("review_cooldown_hours 는 android 에서만 쓴다")
        if not isinstance(hours, (int, float)) or isinstance(hours, bool) or hours < 0:
            raise ConfigError(f"android.review_cooldown_hours 는 0 이상의 숫자여야 합니다 (받은 값: {hours!r})")
    return out


def push_policy(data: dict | None, platform: str, event: str, effective_mode: str) -> tuple[dict, str | None]:
    """push(자동 배포)에서 심사 단계를 막는다. 반환: (덮어쓸 값, 안내 문구 또는 None)."""
    if (event or "") == "workflow_dispatch":
        return {}, None
    mode = (effective_mode or "").strip()
    if mode not in REVIEW_MODES:
        return {}, None
    section = ((data or {}).get(platform) or {}) if isinstance((data or {}).get(platform), dict) else {}
    if section.get("auto_submit_on_push") is True:
        return {}, f"auto_submit_on_push: true — push 에서도 {mode} 로 진행합니다"
    what = "프로덕션 승급" if platform == "android" else "App Store 심사 준비·제출"
    return {"DEPLOY_MODE": "store_only"}, (
        f"push 배포라 {what}({mode})을 건너뛰고 store_only 로 진행합니다. "
        f"{what}은 Actions 에서 이 워크플로를 수동 실행(deploy_mode)해 올립니다. "
        "push 마다 자동으로 하려면 .github/config/store-deploy.json 에 "
        f'"{platform}": {{"auto_submit_on_push": true}} 를 적습니다 — 심사 중에 다음 배포가 오면 그 심사가 다시 시작됩니다.')


def recent_production_submit(runs: list[dict], now_ts: float, hours: float) -> dict | None:
    """수동 store_submit 실행 중 cooldown 안에 끝난 것을 찾는다. runs 는 Actions API 의 workflow_runs."""
    import datetime as _dt
    for r in runs:
        if r.get("event") != "workflow_dispatch" or r.get("conclusion") != "success":
            continue
        if "store_submit" not in (r.get("display_title") or ""):
            continue
        try:
            ts = _dt.datetime.strptime(r["updated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc).timestamp()
        except (KeyError, ValueError):
            continue
        if now_ts - ts < hours * 3600:
            return r
    return None


def _write_env(values: dict) -> None:
    env_file = os.environ.get("GITHUB_ENV")
    for k, v in values.items():
        if env_file:
            with open(env_file, "a", encoding="utf-8") as f:
                f.write(f"{k}={v}\n")


def review_guard(a) -> int:
    """push 의 중간 트랙 승급이 진행 중인 프로덕션 심사를 다시 시작시키지 않게 한다 (#816).

    실패해도 배포를 막지 않는다 — 확인을 못 하면 경고만 남기고 설정대로 진행한다.
    """
    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        print("수동 실행 — 비공개·공개 승급은 고른 값대로 진행합니다.")
        return 0
    if os.environ.get("PROMOTE_TO_CLOSED_TESTING", "false") != "true" and os.environ.get("PROMOTE_TO_OPEN_TESTING", "false") != "true":
        return 0
    try:
        data = load(a.file)
    except ConfigError as e:
        print(f"::error title=store-deploy.json 설정 오류::{e}")
        return 1
    hours = ((data or {}).get("android") or {}).get("review_cooldown_hours", DEFAULT_REVIEW_COOLDOWN_HOURS)
    if not hours:
        return 0
    import json as _json
    import time as _time
    import urllib.request
    repo, token = os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GITHUB_TOKEN", "")
    wf = (os.environ.get("GITHUB_WORKFLOW_REF", "").split("@")[0].rsplit("/", 1)[-1])
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{wf}/runs?event=workflow_dispatch&status=success&per_page=20"
    try:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            runs = _json.load(resp).get("workflow_runs", [])
    except Exception as e:  # noqa: BLE001 — 확인 실패는 배포를 막지 않는다
        print(f"::warning title=프로덕션 심사 확인 실패::최근 수동 프로덕션 제출을 확인하지 못해 설정대로 진행합니다 ({e})")
        return 0
    hit = recent_production_submit(runs, _time.time(), float(hours))
    if not hit:
        print(f"최근 {hours}시간 안에 수동 프로덕션 제출이 없습니다 — 비공개·공개 승급을 진행합니다.")
        return 0
    _write_env({"PROMOTE_TO_CLOSED_TESTING": "false", "PROMOTE_TO_OPEN_TESTING": "false"})
    print(f"::warning title=비공개·공개 승급을 건너뜀::{hit.get('updated_at')} 에 수동 프로덕션 제출이 있었습니다. "
          f"그 심사가 도는 동안 승급하면 프로덕션 심사가 다시 시작되므로 {hours}시간 동안은 내부 테스트에만 올립니다 "
          f"({hit.get('html_url')}). 바로 올리려면 수동 실행에서 promote_to_closed_testing 을 켭니다.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("resolve")
    r.add_argument("--platform", required=True, choices=PLATFORMS)
    r.add_argument("--file", default=DEFAULT_PATH)
    g = sub.add_parser("review-guard", help="push 의 중간 트랙 승급이 진행 중인 프로덕션 심사를 건드리지 않게 한다")
    g.add_argument("--file", default=DEFAULT_PATH)
    a = ap.parse_args(argv)
    if a.cmd == "review-guard":
        return review_guard(a)

    try:
        data = load(a.file)
        values = resolve(data, a.platform, os.environ.get("INPUT_DEPLOY_MODE", ""))
    except ConfigError as e:
        print(f"::error title=store-deploy.json 설정 오류::{e}")
        print(f"❌ {e}", file=sys.stderr)
        return 1

    # push 에서는 심사 단계를 막는다 — 레포 변수(이미 env 에 있음)·설정 파일 어느 쪽에서 왔든 (#816)
    effective = (os.environ.get("INPUT_DEPLOY_MODE") or values.get("DEPLOY_MODE")
                 or os.environ.get("DEPLOY_MODE", "store_only"))
    override, note = push_policy(data, a.platform, os.environ.get("GITHUB_EVENT_NAME", ""), effective)
    if note:
        print(f"::notice title=심사 단계는 수동 실행에서::{note}" if override else f"ℹ️ {note}")
    values.update(override)

    if not values:
        print("store-deploy.json 에서 적용할 값이 없습니다 (파일이 없거나 수동 입력이 우선) — 레포 변수와 기본값을 따릅니다.")
        return 0
    for k, v in values.items():
        print(f"📄 적용 → {k}={v}")
    _write_env(values)
    return 0


if __name__ == "__main__":
    sys.exit(main())
