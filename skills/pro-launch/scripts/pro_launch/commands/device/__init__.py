"""`devices` · `device` — 붙은 기기를 보고, 역할을 묶고, 소유를 알리고, 띄우고 다시 띄우고, 언어·외관을 바꾼다.

동작마다 모듈 하나: bindings(list·bind·unbind·show) · claims(claim·release) · boot(boot·reboot) · settings(locale·appearance).
"""
from __future__ import annotations

from pro_launch.commands.device import bindings, boot, claims, settings, text_size
from pro_launch.registry import Command
from pro_launch.runtime.device_boot import WINDOW_MODES

# device <동작> → 실행 함수
_RUNNERS = {"list": bindings.run_binding_action, "bind": bindings.run_binding_action,
            "unbind": bindings.run_binding_action, "show": bindings.run_binding_action,
            "claim": claims.run_claim, "release": claims.run_release,
            "boot": boot.run_boot, "reboot": boot.run_reboot,
            "locale": settings.run_locale, "appearance": settings.run_appearance,
            "text-size": text_size.run_text_size}


def cmd_device(args) -> int:
    return _RUNNERS[args.action](args)


def configure_devices(p) -> None:
    pass


def configure_device(p) -> None:
    p.add_argument("action", choices=list(_RUNNERS))
    p.add_argument("mode", nargs="?", default=None, help="appearance: light 또는 dark · text-size: default · large · largest (또는 1.3 같은 배율)")
    p.add_argument("--root", default=".")
    p.add_argument("--device", default=None,
                   help="claim·release·reboot·locale·appearance: Android 시리얼 · iOS UDID. boot: UDID · 시뮬레이터 이름 · AVD 이름")
    p.add_argument("--role", default=None, help="bind·unbind: 역할 키. 시나리오 roles 의 키와 같아야 한다")
    p.add_argument("--serial", default=None, help="bind: 기기 시리얼 (device list 에 나온다)")
    p.add_argument("--note", default=None, help="bind: 사람이 읽을 설명. env.sh 에 주석으로 붙는다")
    p.add_argument("--package", default=None, help="list: 설치된 빌드를 대조할 패키지명")
    p.add_argument("--run-dir", default=None, help="list·bind: env.sh 를 쓸 실행 폴더. 없으면 $RUN_DIR")
    p.add_argument("--window", choices=WINDOW_MODES, default=None,
                   help="boot·reboot: headless(창 없음, 기본) · small(배율 0.4) · normal(기본 크기). 캡처 크기와는 무관하다")
    p.add_argument("--scale", type=float, default=None, help="boot·reboot: 창 배율 0.3~1.0 (주면 창을 연다)")
    p.add_argument("--cold", action="store_true", help="boot·reboot: 에뮬레이터를 스냅샷 없이 처음부터 (reboot 은 강제 종료 후)")
    p.add_argument("--yes", action="store_true", help="다른 세션이 쥔 기기 · 호스트 메모리 위험에서도 진행한다 (사용자에게 물은 뒤에만)")
    p.add_argument("--lang", default=None, help="locale: 언어 코드 (en · ko · ja)")
    p.add_argument("--region", default=None, help="locale: 지역 코드 (US · KR)")
    p.add_argument("--app", default=None, help="locale: 앱별 언어로 바꿀 패키지명·번들 ID")
    p.add_argument("--restore", action="store_true", help="locale·appearance·text-size: 바꾸기 전 값으로 되돌린다")


COMMANDS = [
    Command(name="devices", help="붙은 기기 · 부팅된 시뮬레이터 · AVD", run=bindings.run_devices,
            configure=configure_devices),
    Command(name="device",
            help="기기를 묶고(list·bind) 쥐고(claim·release) 띄우고(boot·reboot) 언어·외관·글자 크기를 바꾼다(locale·appearance·text-size)",
            run=cmd_device, configure=configure_device),
]
