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
    p.add_argument("mode", nargs="?", default=None, help="appearance: light or dark · text-size: default · large · largest (or a scale such as 1.3)")
    p.add_argument("--root", default=".")
    p.add_argument("--device", default=None,
                   help="claim·release·reboot·locale·appearance: Android serial · iOS UDID. boot: UDID · simulator name · AVD name")
    p.add_argument("--role", default=None, help="bind·unbind: role key. Must match a key in the scenario's roles")
    p.add_argument("--serial", default=None, help="bind: device serial (shown by device list)")
    p.add_argument("--note", default=None, help="bind: human-readable note. Added to env.sh as a comment")
    p.add_argument("--package", default=None, help="list: package name to check the installed build against")
    p.add_argument("--run-dir", default=None, help="list·bind: run folder to write env.sh into. Defaults to $RUN_DIR")
    p.add_argument("--window", choices=WINDOW_MODES, default=None,
                   help="boot·reboot: headless (no window, default) · small (scale 0.4) · normal (default size). Does not affect capture size")
    p.add_argument("--scale", type=float, default=None, help="boot·reboot: window scale 0.3–1.0 (opens a window when given)")
    p.add_argument("--cold", action="store_true", help="boot·reboot: start the emulator from scratch without a snapshot (reboot force-stops it first)")
    p.add_argument("--yes", action="store_true",
                   help="Proceed even on a device held by another session, with prepared state, or low disk (only after asking the user). Does not bypass memory risk")
    p.add_argument("--user-approved", action="store_true",
                   help="acquire·boot: the memory risk (needs_user · host_memory_pressure · device_budget_exceeded) was shown "
                        "to the user and they said to proceed — only this passes the risk gate")
    p.add_argument("--lang", default=None, help="locale: language code (en · ko · ja)")
    p.add_argument("--region", default=None, help="locale: region code (US · KR)")
    p.add_argument("--app", default=None, help="locale: package name or bundle ID to set a per-app language for")
    p.add_argument("--restore", action="store_true", help="locale·appearance·text-size: restore the value from before the change")
    p.add_argument("--platform", choices=("ios", "android"), default=None, help="acquire: platform of the device to borrow (required)")
    p.add_argument("--form", choices=("phone", "tablet"), default=None, help="acquire: form factor (default phone)")
    p.add_argument("--os", default=None, help="acquire: minimum OS version (e.g. 17 · >=17.2; API level on Android)")
    p.add_argument("--purpose", default=None,
                   help="acquire: purpose shown to other sessions (issue number recommended, e.g. #953 login screen) · alias of --reason in create·clone")
    p.add_argument("--wait", type=float, default=0, help="acquire: if someone else is using it, wait this long (seconds, max 90) and check again")
    p.add_argument("--lease", default=None, help="release: lease_id to return (in the acquire response)")
    p.add_argument("--all", action="store_true", help="release: return every lease of this session (used by the session-end hook)")
    p.add_argument("--keep-booted", action="store_true", help="release: return the device without shutting it down")
    p.add_argument("--need", action="append", default=None,
                   help="acquire: required prepared state kind:name (repeatable, e.g. --need login:kakao)")
    p.add_argument("--fresh", action="store_true", help="acquire: a fresh phone nobody has used (creates a temporary device if none)")
    p.add_argument("--count", type=int, default=1, help="acquire: N distinct devices (max 4)")
    p.add_argument("--reason", default=None,
                   help="create·clone: why a new device is needed (required — shown at cleanup) · alias of --purpose in acquire")
    p.add_argument("--name", default=None, help="create·clone: device name · mark·unmark: state name (e.g. kakao)")
    p.add_argument("--ttl-days", type=float, default=None, help="create: retention period (days, default 3) — eligible for cleanup after that")
    p.add_argument("--kind", default=None, help="mark·unmark: state kind (recommended login · data · permission · config · other)")
    p.add_argument("--apply", action="store_true", help="gc: delete and shut down per the reported plan (otherwise report only)")
    p.add_argument("--full", action="store_true",
                   help="benchmark: add devices one at a time until stall signals appear (slow · only when no other session is active)")
    p.add_argument("--sizes", action="store_true", help="gc: measure the disk size of every device (slow — scans tens of GB)")
    p.add_argument("--verify", action="store_true", help="mark: confirmed the recorded state is still valid (updates the verified time)")
    option_dests = {dest for dests in OPTIONS_BY_ACTION.values() for dest in dests}
    DEVICE_OPTION_DEFAULTS.update({dest: p.get_default(dest) for dest in sorted(option_dests)})


COMMANDS = [
    Command(name="devices", help="Attached devices · booted simulators · AVDs", run=bindings.run_devices,
            configure=configure_devices),
    Command(name="device",
            help="Borrow and return devices (acquire·release·shutdown), create, clone and delete them (create·clone·erase·delete·gc), "
                 "record prepared state (mark·unmark·adopt·records), bind roles (list·bind), claim (claim), boot (boot·reboot), "
                 "and change language, appearance and text size (locale·appearance·text-size)",
            run=cmd_device, configure=configure_device),
]
