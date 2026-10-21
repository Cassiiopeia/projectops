"""`devices` · `device` — 붙은 기기를 보고, 역할을 묶고, 소유를 알리고, 띄우고 다시 띄우고, 언어·외관을 바꾼다.

동작마다 모듈 하나: bindings(list·bind·unbind·show) · claims(claim) · acquire(acquire) · pool(release·shutdown) ·
lifecycle(create·clone·erase·delete·mark·unmark·adopt·records) · gc(gc) · benchmark(benchmark) · boot(boot·reboot) · settings(locale·appearance).
"""
from __future__ import annotations

from pro_launch.commands.device import acquire, benchmark, bindings, boot, claims, gc, lifecycle, pool, settings, text_size
from pro_launch.commands.device.action_options import OPTIONS_BY_ACTION, unused_options, unused_options_failure
from pro_launch.registry import Command
from pro_launch.runtime.context import project_root
from pro_launch.runtime.device_boot import WINDOW_MODES
from pro_launch.runtime.device_gate import gate_device_use
from pro_launch.runtime.output import out

# device <동작> → 실행 함수
_RUNNERS = {"list": bindings.run_binding_action, "bind": bindings.run_binding_action,
            "unbind": bindings.run_binding_action, "show": bindings.run_binding_action,
            "claim": claims.run_claim, "acquire": acquire.run_acquire, "release": pool.run_release,
            "shutdown": pool.run_shutdown,
            "create": lifecycle.run_create, "clone": lifecycle.run_clone, "erase": lifecycle.run_erase, "delete": lifecycle.run_delete,
            "mark": lifecycle.run_mark, "unmark": lifecycle.run_unmark, "adopt": lifecycle.run_adopt,
            "records": lifecycle.run_records, "gc": gc.run_gc, "benchmark": benchmark.run_benchmark,
            "boot": boot.run_boot, "reboot": boot.run_reboot,
            "locale": settings.run_locale, "appearance": settings.run_appearance,
            "text-size": text_size.run_text_size}


# device <동작> → 기기 사용 선언 (registry.DEVICE_USES). none 은 동작이 직접 소유를 판정한다
DEVICE_USE_BY_ACTION = {"list": "none", "bind": "none", "unbind": "none", "show": "none",
                        "claim": "none", "acquire": "none", "release": "none", "shutdown": "none",
                        "create": "none", "clone": "none", "erase": "none", "delete": "none", "mark": "none", "unmark": "none",
                        "adopt": "none", "records": "none", "gc": "none", "benchmark": "none",
                        "boot": "none", "reboot": "none",
                        "locale": "mutate", "appearance": "mutate", "text-size": "mutate"}


# device 옵션 dest > 기본값 (configure_device 가 채운다) — 동작이 안 읽는 옵션을 가려낸다
DEVICE_OPTION_DEFAULTS: dict = {}


def cmd_device(args) -> int:
    unused = unused_options(args.action, vars(args), DEVICE_OPTION_DEFAULTS)
    if unused:
        return out(unused_options_failure(args.action, unused))
    refusal = gate_device_use(DEVICE_USE_BY_ACTION[args.action], args.device, str(project_root(args)), args.yes)
    if refusal is not None:
        return refusal
    return _RUNNERS[args.action](args)


def configure_devices(p) -> None:
    # 다른 명령처럼 --root 를 받는다 — 거부하면 usage 가 stderr 로 섞인다 (#972)
    p.add_argument("--root", default=".")


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
    p.add_argument("--yes", action="store_true",
                   help="다른 세션이 쥔 기기 · 공들인 상태 · 디스크 부족에서도 진행한다 (사용자에게 물은 뒤에만). 메모리 위험은 넘지 않는다")
    p.add_argument("--user-approved", action="store_true",
                   help="acquire·boot: 메모리 위험(needs_user · host_memory_pressure · device_budget_exceeded)을 사용자에게 "
                        "보여 주고 진행하라는 답을 받았다 — 이것만 위험 게이트를 넘는다")
    p.add_argument("--lang", default=None, help="locale: 언어 코드 (en · ko · ja)")
    p.add_argument("--region", default=None, help="locale: 지역 코드 (US · KR)")
    p.add_argument("--app", default=None, help="locale: 앱별 언어로 바꿀 패키지명·번들 ID")
    p.add_argument("--restore", action="store_true", help="locale·appearance·text-size: 바꾸기 전 값으로 되돌린다")
    p.add_argument("--platform", choices=("ios", "android"), default=None, help="acquire: 빌릴 기기 플랫폼 (필수)")
    p.add_argument("--form", choices=("phone", "tablet"), default=None, help="acquire: 폼팩터 (기본 phone)")
    p.add_argument("--os", default=None, help="acquire: 최소 OS 버전 (예: 17 · >=17.2, Android 는 API 레벨)")
    p.add_argument("--purpose", default=None,
                   help="acquire: 다른 세션에게 보일 용도 (이슈 번호 권장, 예: #953 로그인 화면) · create·clone 에서는 --reason 별칭")
    p.add_argument("--wait", type=float, default=0, help="acquire: 남이 쓰는 중이면 이만큼(초, 최대 90) 기다리며 다시 본다")
    p.add_argument("--lease", default=None, help="release: 반납할 lease_id (acquire 응답에 있다)")
    p.add_argument("--all", action="store_true", help="release: 이 세션의 모든 lease 반납 (세션 종료 훅이 쓴다)")
    p.add_argument("--keep-booted", action="store_true", help="release: 켠 기기를 끄지 않고 반납한다")
    p.add_argument("--need", action="append", default=None,
                   help="acquire: 있어야 하는 공들인 상태 kind:name (여러 번, 예: --need login:kakao)")
    p.add_argument("--fresh", action="store_true", help="acquire: 아무도 쓰지 않은 새 폰 (없으면 임시 기기를 만든다)")
    p.add_argument("--count", type=int, default=1, help="acquire: 서로 다른 기기 N 대 (최대 4)")
    p.add_argument("--reason", default=None,
                   help="create·clone: 왜 새 기기가 필요한가 (필수 — 정리 때 보인다) · acquire 에서는 --purpose 별칭")
    p.add_argument("--name", default=None, help="create·clone: 기기 이름 · mark·unmark: 상태 이름 (예: kakao)")
    p.add_argument("--ttl-days", type=float, default=None, help="create: 보관 기한 (일, 기본 3) — 지나면 정리 대상")
    p.add_argument("--kind", default=None, help="mark·unmark: 상태 종류 (권장 login · data · permission · config · other)")
    p.add_argument("--apply", action="store_true", help="gc: 보고한 계획대로 지우고 끈다 (없으면 보고만)")
    p.add_argument("--full", action="store_true",
                   help="benchmark: 멈춤 신호가 보일 때까지 한 대씩 늘려 잰다 (느리다 · 다른 세션이 없을 때만)")
    p.add_argument("--sizes", action="store_true", help="gc: 모든 기기의 디스크 크기를 센다 (느리다 — 수십 GB 를 훑는다)")
    p.add_argument("--verify", action="store_true", help="mark: 기록한 상태가 아직 살아 있음을 확인했다 (확인 시각 갱신)")
    option_dests = {dest for dests in OPTIONS_BY_ACTION.values() for dest in dests}
    DEVICE_OPTION_DEFAULTS.update({dest: p.get_default(dest) for dest in sorted(option_dests)})


COMMANDS = [
    Command(name="devices", help="붙은 기기 · 부팅된 시뮬레이터 · AVD", run=bindings.run_devices,
            configure=configure_devices),
    Command(name="device",
            help="기기를 빌리고·반납하고(acquire·release·shutdown) 만들고·복제하고·지우고(create·clone·erase·delete·gc) "
                 "공들인 상태를 기록하고(mark·unmark·adopt·records) 묶고(list·bind) 쥐고(claim) 띄우고(boot·reboot) "
                 "언어·외관·글자 크기를 바꾼다(locale·appearance·text-size)",
            run=cmd_device, configure=configure_device),
]
