"""남은 Maestro iOS 드라이버 프로세스 찾기 · 가르기 · 정리 (#922).

Maestro 를 시간 초과로 끊거나 부른 쪽이 죽으면 xcodebuild 드라이버 · Runner · JVM 이 남는다.
남은 드라이버가 포트를 쥐고 있으면 다음 호출이 '응답 없음(90초)'·세션 시작 실패로 이어진다 (실측: 정리 후 바로 풀림).

가르기 (프로세스 하나 > owner)
  session  살아 있는 pro-launch 세션 중계(maestro-sessions 상태 파일의 relay_pid)의 자손
  orphan   Maestro 프로세스 사슬의 맨 위 부모가 1 (부른 쪽이 사라졌다) · Runner 는 붙은 드라이버가 없을 때
  active   그 밖 — 부른 쪽이 살아 있다 (다른 세션의 실행 중일 수 있다 > 보고만)
자동 정리는 같은 기기(UDID)를 가리키는 오래된 orphan 드라이버·JVM 만. 그 밖은 `app session stop --kill-stale` 로.
목록은 ps 가 있을 때만 (윈도우는 빈 목록) — top-level 은 표준 라이브러리만.
"""
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import time

KIND_XCODEBUILD_DRIVER = "xcodebuild_driver"   # xcodebuild test-without-building ... maestro-driver-ios-config.xctestrun
KIND_DRIVER_RUNNER = "driver_runner"           # 시뮬레이터 안의 maestro-driver-iosUITests-Runner
KIND_MAESTRO_JVM = "maestro_jvm"               # java ... ~/.maestro/lib · maestro.cli.AppKt
# 부모가 사라진 프로세스를 거두는 pid (macOS launchd · Linux init)
ORPHAN_PARENT_PID = 1
# 자동 정리 최소 나이 (초) — 막 떨어진 프로세스는 아직 정리 중일 수 있다
AUTO_CLEAN_MINIMUM_AGE_SECONDS = 60
# 종료 신호 뒤 기다림 (초) — 안 끝나면 SIGKILL
TERMINATE_GRACE_SECONDS = 2.0
# 이 프로세스에서 자동으로 끝낸 것 (launch_cli 는 호출마다 새 프로세스)
CLEANED_DRIVERS: list[dict] = []
UDID_PATTERN = r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
# 명령줄에서 기기를 가리키는 자리 4개: -destination id= · --device · --udid · 시뮬레이터 폴더
UDID_CONTEXT = re.compile(rf"(?:id=|--device[= ]|--udid[= ]|/Devices/)({UDID_PATTERN})")


def kind_of(command: str) -> str | None:
    """명령줄 > Maestro 프로세스 종류. Maestro 가 아니면 None."""
    if "maestro-driver-iosUITests-Runner" in command:
        return KIND_DRIVER_RUNNER
    if "xcodebuild" in command and "maestro-driver-ios" in command:
        return KIND_XCODEBUILD_DRIVER
    if "java" in command and ("maestro.cli.AppKt" in command or "maestro/lib" in command):
        return KIND_MAESTRO_JVM
    return None


def udid_of(command: str) -> str | None:
    match = UDID_CONTEXT.search(command)
    return match.group(1).upper() if match else None


def parse_elapsed(text: str) -> int | None:
    """ps etime '[[dd-]hh:]mm:ss' > 초."""
    match = re.fullmatch(r"(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+)", (text or "").strip())
    if not match:
        return None
    days, hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def list_processes() -> list[dict]:
    """[{pid, ppid, age_seconds, command}] — ps 가 없거나 실패하면 빈 목록."""
    if not shutil.which("ps"):
        return []
    try:
        # -ww: 긴 명령줄을 자르지 않는다 (xctestrun 경로 · UDID 가 뒤쪽에 온다)
        output = subprocess.run(["ps", "-ax", "-ww", "-o", "pid=,ppid=,etime=,command="], capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=5).stdout or ""
    except (OSError, subprocess.SubprocessError):
        return []
    rows = []
    for line in output.splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4 and parts[0].isdigit() and parts[1].isdigit():
            rows.append({"pid": int(parts[0]), "ppid": int(parts[1]), "age_seconds": parse_elapsed(parts[2]),
                         "command": parts[3]})
    return rows


def live_session_relay_pids() -> set[int]:
    """살아 있는 세션 중계 pid (maestro-sessions 상태 파일 기준)."""
    import maestro_session                 # maestro_session > maestro_runs > 여기 순환을 피해 부를 때 들인다
    from common.proc import pid_alive
    pids = set()
    try:
        files = list(maestro_session.session_folder().glob("*.json"))
    except OSError:
        return pids
    for path in files:
        session = maestro_session.read_session(path.stem) or {}
        relay_pid = session.get("relay_pid")
        if relay_pid and pid_alive(int(relay_pid)):
            pids.add(int(relay_pid))
    return pids


def classify(processes: list[dict], relay_pids: set[int], own_pid: int | None = None) -> list[dict]:
    """Maestro 프로세스만 골라 owner 를 붙인다: session · orphan · active (자기 자신의 자손은 뺀다)."""
    by_pid = {row["pid"]: row for row in processes}
    own_pid = own_pid if own_pid is not None else os.getpid()
    drivers = []
    for row in processes:
        kind = kind_of(row["command"])
        if not kind:
            continue
        ancestors = _ancestors(row, by_pid)
        if own_pid in ancestors:
            continue
        if relay_pids & set(ancestors):
            owner = "session"
        elif kind != KIND_DRIVER_RUNNER and _chain_top(row, by_pid)["ppid"] == ORPHAN_PARENT_PID:
            owner = "orphan"
        else:
            owner = "active"
        drivers.append({"pid": row["pid"], "ppid": row["ppid"], "kind": kind, "age_seconds": row["age_seconds"],
                        "udid": udid_of(row["command"]), "owner": owner})
    # Runner: 같은 기기에 orphan 아닌 드라이버·JVM 이 없으면 붙은 쪽이 없는 것
    for driver in drivers:
        if driver["kind"] == KIND_DRIVER_RUNNER and driver["owner"] == "active":
            has_live_host = any(other["kind"] != KIND_DRIVER_RUNNER and other["owner"] != "orphan"
                                and other["udid"] in (driver["udid"], None) for other in drivers)
            driver["owner"] = "active" if has_live_host else "orphan"
    return drivers


def _ancestors(row: dict, by_pid: dict) -> list[int]:
    chain, seen, parent = [], set(), row["ppid"]
    while parent in by_pid and parent not in seen:
        seen.add(parent)
        chain.append(parent)
        parent = by_pid[parent]["ppid"]
    return chain + ([parent] if parent not in seen else [])


def _chain_top(row: dict, by_pid: dict) -> dict:
    """Maestro 프로세스 사슬의 맨 위 (JVM > xcodebuild 처럼 이어진 것) — 그 부모가 1 이면 사슬 전체가 고아."""
    top, seen = row, {row["pid"]}
    while top["ppid"] in by_pid and top["ppid"] not in seen and kind_of(by_pid[top["ppid"]]["command"]):
        seen.add(top["ppid"])
        top = by_pid[top["ppid"]]
    return top


def is_for_device(driver: dict, device: str | None) -> bool:
    """기기 UDID 가 같거나 명령줄에서 기기를 알 수 없다."""
    return driver["udid"] is None or not device or driver["udid"] == device.upper()


def is_auto_cleanable(driver: dict, device: str | None) -> bool:
    """자동 정리 조건 4개: orphan · Runner 아님 · 같은 UDID 가 명령줄에 있음 · 최소 나이 이상."""
    return (driver["owner"] == "orphan" and driver["kind"] != KIND_DRIVER_RUNNER
            and bool(device) and driver["udid"] == (device or "").upper()
            and (driver["age_seconds"] or 0) >= AUTO_CLEAN_MINIMUM_AGE_SECONDS)


def public_entry(driver: dict) -> dict:
    return {"pid": driver["pid"], "kind": driver["kind"], "age_seconds": driver["age_seconds"]}


def survey(device: str | None) -> list[dict]:
    """이 기기에 관련된 Maestro 프로세스 (owner 포함)."""
    return [d for d in classify(list_processes(), live_session_relay_pids()) if is_for_device(d, device)]


def terminate(pids: list[int]) -> list[int]:
    """SIGTERM > 잠시 > 남은 것 SIGKILL. 끝난 pid 목록."""
    from common.proc import pid_alive
    for pid in pids:
        _send(pid, signal.SIGTERM)
    deadline = time.monotonic() + TERMINATE_GRACE_SECONDS
    while time.monotonic() < deadline and any(pid_alive(pid) for pid in pids):
        time.sleep(0.1)
    for pid in pids:
        if pid_alive(pid):
            _send(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
    return [pid for pid in pids if not pid_alive(pid)]


def _send(pid: int, signal_number: int) -> None:
    try:
        os.kill(pid, signal_number)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def clean_auto(device: str | None) -> list[dict]:
    """조작 전 자동 정리 (같은 UDID 의 오래된 orphan 드라이버·JVM 만) > 끝낸 것."""
    return _terminate_recorded([d for d in survey(device) if is_auto_cleanable(d, device)])


def clean_after_timeout(device: str | None, run_seconds: float) -> list[dict]:
    """시간 초과로 끊은 직후: 이번 실행 동안 생겨 고아가 된 드라이버 > 끝낸 것 (나이 제한 없이 — 우리 것이다)."""
    return _terminate_recorded([d for d in survey(device) if d["owner"] == "orphan" and d["kind"] != KIND_DRIVER_RUNNER
                                and (d["age_seconds"] or 0) <= run_seconds + 5])


def _terminate_recorded(targets: list[dict]) -> list[dict]:
    """끝내고 CLEANED_DRIVERS 에 남긴다 (응답의 cleaned_stale_drivers)."""
    killed = set(terminate([d["pid"] for d in targets])) if targets else set()
    cleaned = [public_entry(d) for d in targets if d["pid"] in killed]
    CLEANED_DRIVERS.extend(cleaned)
    return cleaned


def kill_stale(device: str, is_dry_run: bool = False) -> dict:
    """명시 정리(`app session stop --kill-stale`): 이 기기의 orphan 전부 (Runner 포함, 기기를 모르는 것 포함)."""
    drivers = survey(device)
    targets = [d for d in drivers if d["owner"] == "orphan"]
    killed = set(terminate([d["pid"] for d in targets])) if targets and not is_dry_run else set()
    return {"stale_found": [public_entry(d) for d in targets],
            "killed": [d["pid"] for d in targets if d["pid"] in killed],
            "other_maestro_processes": [public_entry(d) for d in drivers if d["owner"] == "active"]}


def failure_fields(device: str | None) -> dict:
    """실패 응답에 붙일 것: 남은 orphan · 지금 도는 다른 Maestro (비어 있으면 키 없음)."""
    drivers = survey(device)
    fields = {"stale_maestro_drivers": [public_entry(d) for d in drivers if d["owner"] == "orphan"],
              "other_maestro_processes": [public_entry(d) for d in drivers if d["owner"] == "active"]}
    return {key: value for key, value in fields.items() if value}
