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
                "summary": f"{n} devices available · memory pressure {resources['pressure']}",
                "next": advice or (None if n else "Boot one with device boot --device <AVD name|simulator name|UDID>")})


def run_binding_action(args) -> int:
    """역할을 기기에 묶고, 무엇이 깔려 있는지 대조한다 (list · bind · unbind · show)."""
    root = project_root(args)
    known = load_devices(root)
    bindings = known["bindings"]
    package = args.package or known["package"]

    if args.action in ("bind", "unbind"):
        if not args.role:
            return out({"ok": False, "code": "args_required", "error": "--role is required",
                        "hint": "Use the same value as a key in the scenario's roles"})
        bindings = [b for b in bindings if b["role"] != args.role]
        if args.action == "bind":
            if not args.serial:
                return out({"ok": False, "code": "args_required",
                            "error": "--serial is required",
                            "hint": "See the attached devices with device list first"})
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
            "summary": f"{len(bindings)} roles" + ("" if env else " (env.sh not written yet)"),
            "next": (None if env else
                     "Create a run folder with get-output-path first, set $RUN_DIR, "
                     "then call again to write env.sh"),
        })

    if args.action == "show":
        return out({"bindings": bindings, "package": package,
                    "file": str(devices_path(root)), "summary": f"{len(bindings)} roles"})

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
        nxt = "Install the same build on both and check again — if only one is reinstalled, the screens you step through will differ"
    elif stale:
        nxt = f"Bound devices are not attached: {', '.join(stale)}"
    elif len(rows) > 1 and unbound:
        nxt = ("Bind roles with device bind --role {KEY} --serial {SERIAL} — "
               "otherwise adb cannot tell which device to target")
    # 기기는 get-output-path 뒤에 부팅되기도 한다. 환경을 새로 고쳐 두지 않으면 DEV 가 빈다.
    run_dir = resolve_run_dir(args)
    env = write_env_sh(run_dir, package, bindings) if (run_dir and run_dir.is_dir()) else None
    return out({
        "devices": rows, "env_file": str(env) if env else None,
        "ios_booted": dev["ios_booted"], "owners": owners, "package": package,
        "build_mismatch": mismatch, "stale_bindings": stale,
        "summary": (f"{len(rows)} devices · {len(bindings)} roles"
                    + (f" · {len(mismatch)} build mismatches" if mismatch else "")),
        "next": nxt, "ok": not mismatch,
        "code": "build_mismatch" if mismatch else "ok",
    })
