"""`devices` · `device list|bind|unbind|show` — 붙은 기기를 보고 역할을 기기에 묶는다."""
from __future__ import annotations


from pro_launch.runtime import host_resources
from pro_launch.runtime.context import project_root
from pro_launch.runtime.device_claims import owners_by_device
from pro_launch.runtime.devices import build_info, build_mismatch, devices_path, ios_udids, list_devices, load_devices, save_devices
from pro_launch.runtime.envfile import resolve_run_dir, write_env_sh
from pro_launch.runtime.output import out


def run_devices(args) -> int:
    dev = list_devices()
    n = len(dev["android"]) + len(dev["ios_booted"])
    # 호스트 메모리 압박 요약 — 기기를 더 띄우기 전에 보게 한다 (#883). 자세히는 doctor --resources
    resources = host_resources.memory_summary()
    advice = host_resources.pressure_advice(resources["pressure"])
    return out({**dev, "resources": resources, "owners": owners_by_device(),
                "summary": f"사용 가능한 기기 {n}대 · 메모리 압박 {resources['pressure']}",
                "next": advice or (None if n else "emulator -avd {AVD명} 으로 부팅하세요")})


def run_binding_action(args) -> int:
    """역할을 기기에 묶고, 무엇이 깔려 있는지 대조한다 (list · bind · unbind · show)."""
    root = project_root(args)
    known = load_devices(root)
    bindings = known["bindings"]
    package = args.package or known["package"]

    if args.action in ("bind", "unbind"):
        if not args.role:
            return out({"ok": False, "code": "args_required", "error": "--role 이 필요합니다",
                        "hint": "시나리오 roles 의 키와 같은 값을 쓰세요"})
        bindings = [b for b in bindings if b["role"] != args.role]
        if args.action == "bind":
            if not args.serial:
                return out({"ok": False, "code": "args_required",
                            "error": "--serial 이 필요합니다",
                            "hint": "device list 로 붙어 있는 기기를 먼저 보세요"})
            entry = {"role": args.role, "serial": args.serial}
            if args.note:
                entry["note"] = args.note
            bindings.append(entry)
        save_devices(root, package, bindings)
        run_dir = resolve_run_dir(args)
        env = write_env_sh(run_dir, package, bindings) if (run_dir and run_dir.is_dir()) else None
        return out({
            "bindings": bindings, "file": str(devices_path(root)),
            "env_file": str(env) if env else None,
            "summary": f"역할 {len(bindings)}개" + ("" if env else " (env.sh 는 아직 안 씀)"),
            "next": (None if env else
                     "get-output-path 로 실행 자리를 먼저 만들고 $RUN_DIR 을 세운 뒤 "
                     "다시 부르면 env.sh 에 반영됩니다"),
        })

    if args.action == "show":
        return out({"bindings": bindings, "package": package,
                    "file": str(devices_path(root)), "summary": f"역할 {len(bindings)}개"})

    # list — 붙어 있는 기기 + 역할 + 설치된 빌드
    dev = list_devices()
    by_role = {b["serial"]: b for b in bindings}
    # 기기 소유(device claim) — 다른 세션이 쥔 기기를 목록에서 바로 본다 (#925)
    owners = owners_by_device()
    rows = []
    for serial in dev["android"]:
        b = by_role.get(serial, {})
        rows.append({"serial": serial, "role": b.get("role"), "note": b.get("note"),
                     "owner": owners.get(serial), "build": build_info(serial, package)})
    unbound = [r["serial"] for r in rows if not r["role"]]
    mismatch = build_mismatch(rows)
    ios_ids = ios_udids(dev)
    stale = [b["serial"] for b in bindings
             if b["serial"] not in dev["android"] and b["serial"] not in ios_ids]
    nxt = None
    if mismatch:
        nxt = "양쪽에 같은 빌드를 설치한 뒤 다시 확인하세요 — 한쪽만 재설치되면 밟는 화면이 달라집니다"
    elif stale:
        nxt = f"묶어 둔 기기가 붙어 있지 않습니다: {', '.join(stale)}"
    elif len(rows) > 1 and unbound:
        nxt = ("device bind --role {키} --serial {시리얼} 로 역할을 잡으세요 — "
               "안 잡으면 adb 가 어느 기기로 갈지 정해지지 않습니다")
    # 기기는 get-output-path 뒤에 부팅되기도 한다. 환경을 새로 고쳐 두지 않으면 DEV 가 빈다.
    run_dir = resolve_run_dir(args)
    env = write_env_sh(run_dir, package, bindings) if (run_dir and run_dir.is_dir()) else None
    return out({
        "devices": rows, "env_file": str(env) if env else None,
        "ios_booted": dev["ios_booted"], "owners": owners, "package": package,
        "build_mismatch": mismatch, "stale_bindings": stale,
        "summary": (f"기기 {len(rows)}대 · 역할 {len(bindings)}개"
                    + (f" · 빌드 불일치 {len(mismatch)}건" if mismatch else "")),
        "next": nxt, "ok": not mismatch,
        "code": "build_mismatch" if mismatch else "ok",
    })
