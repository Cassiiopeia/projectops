"""cloudflared quick tunnel processes: find > start (detached from the session) > stop, listening ports of an app"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from . import proc, state

IS_WINDOWS = sys.platform.startswith("win")
# Quick tunnel address printed in the cloudflared log
TUNNEL_URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
# --url http://127.0.0.1:6768 > 6768
LOCAL_PORT_PATTERN = re.compile(r"--url[ =]+https?://[^\s:/]+:(\d+)")


def _run(command: list[str], timeout: int = 15) -> str:
    try:
        completed = subprocess.run(command, capture_output=True, timeout=timeout,
                                   encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout or ""


def cloudflared_path() -> str | None:
    return shutil.which("cloudflared")


def _process_rows() -> list[tuple[int, str]]:
    """List of (pid, command line). Empty list on failure"""
    if IS_WINDOWS:
        script = ("Get-CimInstance Win32_Process -Filter \"Name='cloudflared.exe'\" | "
                  "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress")
        raw = _run(["powershell", "-NoProfile", "-Command", script], timeout=30).strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except ValueError:
            return []
        items = parsed if isinstance(parsed, list) else [parsed]
        return [(int(item.get("ProcessId") or 0), str(item.get("CommandLine") or "")) for item in items]
    rows = []
    for line in _run(["ps", "-ax", "-o", "pid=,command="]).splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            rows.append((int(parts[0]), parts[1]))
    return rows


def quick_tunnels() -> list[dict]:
    """Running quick tunnels (named tunnels have no --url, so they are left out)"""
    tunnels = []
    for pid, command in _process_rows():
        # Only processes whose executable is cloudflared (skip shell lines wrapping it)
        executable = Path(command.strip().strip('"').split()[0] if command.strip() else "").name.lower()
        if executable not in ("cloudflared", "cloudflared.exe") or " tunnel" not in command:
            continue
        match = LOCAL_PORT_PATTERN.search(command)
        if match:
            tunnels.append({"pid": pid, "port": int(match.group(1)), "command": command[:200]})
    return tunnels


def is_alive(pid: int) -> bool:
    # pid 0 or below signals a process group, so not a liveness target
    if pid <= 0:
        return False
    return proc.pid_alive(pid)


def live_tunnel(port: int) -> dict | None:
    """Tunnel this skill started for the port, if its process is still alive and its URL is known"""
    record = state.load()["tunnels"].get(str(port))
    if not record or not is_alive(int(record.get("pid") or 0)):
        return None
    url = record.get("url") or url_from_log(Path(record.get("log") or ""))
    return {**record, "url": url} if url else None


def stop(pid: int) -> bool:
    """Stop: ask to exit > force if not done within 3 seconds"""
    if IS_WINDOWS:
        _run(["taskkill", "/PID", str(pid), "/F"])
        return not is_alive(pid)
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return not is_alive(pid)
    for _ in range(30):
        if not is_alive(pid):
            return True
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    time.sleep(0.3)
    return not is_alive(pid)


def start(binary: str, port: int, log_path: Path) -> int:
    """Start detached from the session (the tunnel survives the agent session)"""
    log_handle = open(log_path, "w", encoding="utf-8")
    command = [binary, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"]
    options: dict = {"stdout": log_handle, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}
    if IS_WINDOWS:
        options["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    process = subprocess.Popen(command, **options)
    log_handle.close()
    return process.pid


def url_from_log(log_path: Path) -> str | None:
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = TUNNEL_URL_PATTERN.search(text)
    return match.group(0) if match else None


def wait_for_url(log_path: Path, pid: int, timeout_seconds: int = 45) -> str | None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        url = url_from_log(log_path)
        if url:
            return url
        if not is_alive(pid):
            return None
        time.sleep(0.5)
    return None


def _windows_process_names() -> dict[int, str]:
    names = {}
    for line in _run(["tasklist", "/FO", "CSV", "/NH"], timeout=30).splitlines():
        fields = [field.strip('"') for field in line.split('","')]
        if len(fields) >= 2 and fields[1].isdigit():
            names[int(fields[1])] = fields[0]
    return names


def listening_ports_of(process_word: str) -> list[int]:
    """TCP ports listened on by processes whose name contains process_word (macOS lsof · Linux ss · Windows netstat+tasklist)"""
    word = process_word.lower()
    ports: set[int] = set()
    if IS_WINDOWS:
        names = _windows_process_names()
        for line in _run(["netstat", "-ano", "-p", "TCP"], timeout=30).splitlines():
            fields = line.split()
            if len(fields) >= 5 and fields[3].upper() == "LISTENING" and fields[4].isdigit():
                if word in names.get(int(fields[4]), "").lower():
                    match = re.search(r":(\d+)$", fields[1])
                    if match:
                        ports.add(int(match.group(1)))
    elif shutil.which("lsof"):
        for line in _run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"]).splitlines()[1:]:
            fields = line.split()
            if len(fields) >= 9 and word in fields[0].lower():
                match = re.search(r":(\d+)$", fields[8])
                if match:
                    ports.add(int(match.group(1)))
    elif shutil.which("ss"):
        for line in _run(["ss", "-ltnpH"]).splitlines():
            if word in line.lower():
                match = re.search(r":(\d+)\s", line)
                if match:
                    ports.add(int(match.group(1)))
    return sorted(ports)
