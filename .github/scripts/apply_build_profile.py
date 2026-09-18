#!/usr/bin/env python3
# ===================================================================
# apply_build_profile.py — 빌드 프로파일을 두 층에 함께 적용한다 (#603)
# ===================================================================
#
# 크로스 플랫폼(Windows/macOS/Linux) 표준 라이브러리 전용 — PyYAML/jq 불필요.
#
# ## 왜 있나
#
# 앱의 개발 스위치는 **두 층**에 있다.
#
#   런타임      `.env`           dotenv가 에셋으로 읽는다. Secret으로 주입된다.
#   컴파일타임  `--dart-define`  바이너리에 박힌다. Secret으로 위조할 수 없다.
#
# 기능 하나를 켜려면 **두 층이 모두 맞아야 한다.** 그런데 워크플로에서 이 둘이 따로
# 놀면 **한쪽만 적용돼도 그대로 통과한다.** 실측 사고: `.env`에 개발 플래그가 찍히고
# 로그는 "적용 완료"를 냈는데, 설치해 보니 디버깅 도구가 없었다 — 릴리스 빌드라
# 컴파일타임 게이트가 닫혀 있었다. 로그만 봐서는 알 수 없었다.
#
# 이 스크립트가 **한 곳에서 두 층을 모두 정한다.** 워크플로는 결과를 그대로 쓴다:
#
#   - name: 빌드 프로파일 적용
#     id: build_profile
#     run: python3 .github/scripts/apply_build_profile.py test .env
#
#   - name: Build
#     # 🔴 여기에 dart-define을 직접 적지 않는다. 적는 순간 다시 두 곳이 된다.
#     run: flutter build apk --release ${{ steps.build_profile.outputs.build_flags }}
#
# ## 설정이 없으면 아무것도 하지 않는다 ⚠️
#
# 이 템플릿은 남의 저장소에 설치된다. 프로파일 정의가 없는 저장소에서 `.env`를
# 건드리거나 빌드 플래그를 만들어 내면 **멀쩡히 돌던 빌드가 깨진다.**
# 설정 파일이 없으면 빈 `build_flags`만 내보내고 성공으로 끝낸다.
#
# ## 설정 (.github/config/build-profile.json)
#
#   {
#     "dev_keys":    ["APP_SHOW_DEV_TOOLS", "APP_ENABLE_NETWORK_LOG"],
#     "secret_keys": ["APP_DEV_ACCESS_TOKEN"],
#     "profiles": {
#       "test":    {"env": {"APP_SHOW_DEV_TOOLS": "true"},
#                   "dart_define": {"APP_FLAVOR": "dev"}},
#       "release": {"env": {"APP_SHOW_DEV_TOOLS": "false"},
#                   "dart_define": {}}
#     }
#   }
#
#   dev_keys     개발 전용 런타임 키. 프로파일을 적용하기 전에 .env에서 걷어낸다
#                (Secret에 남아 있던 값이 살아남지 못하게 한다).
#   secret_keys  값이 있기만 해도 배포 빌드를 세울 키 (QA 토큰 등).
#   profiles     프로파일 이름 → 적용할 env / dart_define. 이름은 자유다.
#
# `release`라는 이름의 프로파일에는 **검증이 걸린다** — 개발 키가 켜진 채로,
# 또는 QA 토큰이 남은 채로 빌드가 나가지 않는다.
# ===================================================================

import argparse
import json
import os
import sys
from pathlib import Path

DEFAULT_CONFIG = Path(".github/config/build-profile.json")

# 이 이름의 프로파일에는 "꺼져 있어야 한다"는 검증이 걸린다.
GUARDED_PROFILE = "release"


def log(msg):
    print(msg, file=sys.stderr)


def fail(msg):
    # GitHub Actions 주석 형식 — 로그에서 눈에 띄고 요약에도 올라간다
    print(f"::error::{msg}", file=sys.stderr)
    sys.exit(1)


def load_config(path: Path):
    """설정을 읽는다. 없으면 None — 호출부가 '아무것도 하지 않음'으로 처리한다."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        # 깨진 설정을 조용히 무시하면 "왜 안 먹지"로 몇 시간이 간다
        fail(f"빌드 프로파일 설정을 읽을 수 없습니다: {path} ({e})")
    if not isinstance(data, dict):
        fail(f"빌드 프로파일 설정이 객체가 아닙니다: {path}")
    return data


def read_env_lines(env_file: Path):
    if not env_file.is_file():
        fail(f".env 파일이 없습니다: {env_file}")
    # 값에 비ASCII가 섞여도 죽지 않게 — 러너 로캘에 기대지 않는다
    return env_file.read_text(encoding="utf-8", errors="replace").splitlines()


def strip_keys(lines, keys):
    """주어진 키로 시작하는 줄을 걷어낸다.

    sed -i 를 쓰지 않는 이유: GNU(-i)와 BSD(-i '') 문법이 갈려 Linux 러너와
    macOS 러너에서 동작이 달라진다. 조용히 통과하고 아무것도 안 바뀌는
    사고가 실제로 있었다(#523).
    """
    prefixes = tuple(f"{k}=" for k in keys)
    return [ln for ln in lines if not ln.lstrip().startswith(prefixes)]


def env_value(lines, key):
    """마지막에 선언된 값이 이긴다 — dotenv 구현들의 일반적 동작."""
    found = None
    for ln in lines:
        s = ln.lstrip()
        if s.startswith(f"{key}="):
            found = s.split("=", 1)[1]
    return found


def mask(key, value):
    """토큰·비밀번호류는 값을 찍지 않는다 — 빌드 로그는 누구나 본다."""
    if value is None or value == "":
        return "(없음)"
    upper = key.upper()
    if any(w in upper for w in ("TOKEN", "SECRET", "PASSWORD", "KEY_JSON", "CREDENTIAL")):
        return "(설정됨)"
    return value


def build_flags(dart_define: dict) -> str:
    # dict 순서를 그대로 쓴다 — 설정 파일에 적힌 순서가 로그에 그대로 나와야 읽기 쉽다
    return " ".join(f"--dart-define={k}={v}" for k, v in dart_define.items())


def emit_output(flags: str):
    """워크플로가 빌드 명령에 붙일 수 있게 내보낸다. 로컬 실행이면 화면 출력만."""
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"build_flags={flags}\n")


def verify_release(lines, dev_keys, secret_keys, flags, test_defines):
    """배포 빌드가 개발 상태로 나가지 않는지 양쪽 층을 모두 본다."""
    for k in dev_keys:
        v = env_value(lines, k)
        if v is not None and v.strip().lower() == "true":
            fail(f"배포 빌드에 개발 키가 켜져 있습니다: {k}")
    for k in secret_keys:
        v = env_value(lines, k)
        if v is not None and v.strip() != "":
            fail(f"배포 빌드에 개발용 비밀값이 남아 있습니다: {k}")
    # 컴파일타임 쪽도 본다. 여기가 뚫리면 .env가 아무리 깨끗해도 개발 빌드가 나간다.
    for k, v in test_defines.items():
        if f"--dart-define={k}={v}" in flags:
            fail(f"배포 빌드에 테스트 전용 플래그가 들어갔습니다: {k}={v}")
    log("✅ 런타임·컴파일타임 양쪽 모두 꺼진 것을 확인했습니다")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="빌드 프로파일을 .env와 dart-define 양쪽에 함께 적용한다")
    ap.add_argument("profile", help="프로파일 이름 (예: test · release)")
    ap.add_argument("env_file", help=".env 경로")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG),
                    help=f"설정 파일 (기본: {DEFAULT_CONFIG})")
    args = ap.parse_args(argv)

    cfg = load_config(Path(args.config))

    # ── 설정이 없다 → 아무것도 하지 않는다 (기존 저장소 무영향) ──
    if cfg is None:
        log(f"ℹ️  빌드 프로파일 설정이 없습니다 ({args.config}) — 건너뜁니다")
        emit_output("")
        return 0

    profiles = cfg.get("profiles") or {}
    if args.profile not in profiles:
        available = ", ".join(sorted(profiles)) or "(없음)"
        fail(f"알 수 없는 프로파일: {args.profile} — 설정에 있는 것: {available}")

    profile = profiles[args.profile] or {}
    dev_keys = list(cfg.get("dev_keys") or [])
    secret_keys = list(cfg.get("secret_keys") or [])
    want_env = dict(profile.get("env") or {})
    dart_define = dict(profile.get("dart_define") or {})

    env_file = Path(args.env_file)
    lines = read_env_lines(env_file)

    # 개발 키와 이번에 쓸 키를 함께 걷어낸 뒤 다시 쓴다.
    # dev_keys 를 지우는 이유: Secret 에 남아 있던 값이 살아남으면 프로파일이
    # 의미를 잃는다. want_env 를 지우는 이유: 같은 키가 두 번 적히는 것을 막는다.
    lines = strip_keys(lines, set(dev_keys) | set(want_env))
    for k, v in want_env.items():
        lines.append(f"{k}={v}")

    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    flags = build_flags(dart_define)
    emit_output(flags)

    # ── 결과 — 두 층을 함께 보여준다 ──
    # 한 층만 찍으면 "적용 완료"가 거짓말이 된다. 그게 이 스크립트가 생긴 이유다.
    log(f"✅ 빌드 프로파일 적용: {args.profile}")
    log("── 런타임 스위치 (.env) ──")
    shown = list(dict.fromkeys(list(want_env) + dev_keys + secret_keys))
    if shown:
        for k in shown:
            log(f"  {k:<28} {mask(k, env_value(lines, k))}")
    else:
        log("  (정의된 키 없음)")
    log("── 컴파일타임 플래그 (dart-define) ──")
    log(f"  {flags}" if flags else "  (없음)")

    if args.profile == GUARDED_PROFILE:
        test_defines = {}
        for name, p in profiles.items():
            if name != GUARDED_PROFILE:
                test_defines.update((p or {}).get("dart_define") or {})
        # 배포 프로파일이 같은 키를 **다른 값으로** 덮어썼다면 위반이 아니다
        # (예: test 는 APP_FLAVOR=dev, release 는 APP_FLAVOR=prod).
        # 값까지 같다면 덮어쓴 것이 아니라 테스트 값이 그대로 나가는 것이므로 막는다.
        for k, v in dart_define.items():
            if test_defines.get(k) != v:
                test_defines.pop(k, None)
        verify_release(lines, dev_keys, secret_keys, flags, test_defines)

    return 0


if __name__ == "__main__":
    sys.exit(main())
