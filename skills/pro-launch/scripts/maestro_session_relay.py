"""iOS 상주 Maestro 세션의 중계 프로세스 (#894 2단계) — `maestro mcp` 의 표준입출력을 소유하고 127.0.0.1 TCP 로 요청을 넘긴다.

`app session start` 가 백그라운드로 띄운다: python3 maestro_session_relay.py serve --device <UDID> ...
준비 > 상태 파일 ready (포트·토큰) > 요청 처리 > 유휴 N분 · stop 요청이면 maestro mcp 와 함께 끝난다.
표준 라이브러리 + 같은 폴더의 maestro_session(상태 파일·도구 이름)만 쓴다.
"""
from __future__ import annotations

import argparse
import collections
import hmac
import json
import os
import queue
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from maestro_session import DEFAULT_IDLE_MINUTES, resolve_tool_names, write_session

# 다른 maestro test 가 같은 기기에 붙으면 세션의 드라이버 연결이 끊긴다 (실측) — 이 문구면 다시 붙는다
DEVICE_UNREACHABLE_MARKERS = ("became unreachable", "Device unreachable", "Connection refused")
# maestro mcp 기동·초기화 대기 · 기기 연결 예열 대기 · accept 확인 간격 (초)
CHILD_START_TIMEOUT_SECONDS = 40
WARM_UP_TIMEOUT_SECONDS = 120
ACCEPT_POLL_SECONDS = 2
# 요청 한 줄 최대 크기 (바이트)
MAXIMUM_REQUEST_BYTES = 1_000_000
MCP_PROTOCOL_VERSION = "2024-11-05"


def _log(message: str) -> None:
    # 중계의 stderr 는 상태 폴더의 <UDID>.log 로 간다. 도구 인자(flow·화면 문구)는 적지 않는다
    sys.stderr.write(time.strftime("%H:%M:%S ") + message + "\n")
    sys.stderr.flush()


class MaestroChild:
    """`maestro mcp` 프로세스 하나와 JSON-RPC 주고받기. 줄 읽기는 스레드 + 큐 (select 는 윈도우 파이프에서 안 된다)."""

    def __init__(self, maestro_path: str, working_folder: str):
        self.maestro_path, self.working_folder = maestro_path, working_folder
        self.process: subprocess.Popen | None = None
        self.lines: queue.Queue = queue.Queue()
        self.stderr_tail: collections.deque = collections.deque(maxlen=40)
        self.next_id = 0
        self.viewer_url: str | None = None
        self.is_viewer_disabled = False

    def start(self) -> list[str]:
        """기동 > initialize > tools/list. 도구 이름 목록을 돌려준다. --no-viewer 를 모르는 옛 버전이면 빼고 다시."""
        for extra in (["--no-viewer"], []):
            self._spawn(["mcp", *extra])
            try:
                self.rpc("initialize", {"protocolVersion": MCP_PROTOCOL_VERSION, "capabilities": {},
                                        "clientInfo": {"name": "pro-launch", "version": "1"}},
                         CHILD_START_TIMEOUT_SECONDS)
            except RuntimeError:
                # 표준출력이 먼저 닫혀도 stderr 줄이 아직 덜 읽혔을 수 있다 — 끝날 때까지 잠깐 기다린다
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
                time.sleep(0.2)
                if extra and any("Unknown option" in line for line in self.stderr_tail):
                    self.stop()
                    continue
                raise
            self.is_viewer_disabled = bool(extra)
            self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            listed = self.rpc("tools/list", {}, CHILD_START_TIMEOUT_SECONDS)
            return [tool.get("name", "") for tool in listed.get("tools", [])]
        raise RuntimeError("maestro mcp did not start")

    def _spawn(self, arguments: list[str]) -> None:
        self.lines, self.stderr_tail = queue.Queue(), collections.deque(maxlen=40)
        self.process = subprocess.Popen([self.maestro_path, *arguments], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                        encoding="utf-8", errors="replace", cwd=self.working_folder)
        threading.Thread(target=self._pump, args=(self.process.stdout, self.lines.put), daemon=True).start()
        threading.Thread(target=self._pump, args=(self.process.stderr, self._remember_stderr), daemon=True).start()

    @staticmethod
    def _pump(stream, sink) -> None:
        for line in stream:
            sink(line)
        sink(None)

    def _remember_stderr(self, line: str | None) -> None:
        if line is None:
            return
        self.stderr_tail.append(line.rstrip())
        # 뷰어를 끄지 못한 옛 버전: 'mcp_viewer_ready http://127.0.0.1:9999' (포트가 차 있으면 다음 빈 포트)
        match = re.search(r"mcp_viewer_ready\s+(\S+)", line)
        if match:
            self.viewer_url = match.group(1)

    def is_alive(self) -> bool:
        return bool(self.process and self.process.poll() is None)

    def _send(self, message: dict) -> None:
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def rpc(self, method: str, params: dict, timeout_seconds: float) -> dict:
        """요청 하나 > result. 죽었거나 시간 초과·오류면 RuntimeError."""
        if not self.is_alive():
            raise RuntimeError("maestro mcp is not running")
        self.next_id += 1
        request_id = self.next_id
        try:
            self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        except (OSError, ValueError) as error:
            raise RuntimeError(f"maestro mcp stdin closed: {error}") from error
        deadline = time.monotonic() + timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"{method} timed out after {timeout_seconds}s")
            try:
                line = self.lines.get(timeout=remaining)
            except queue.Empty:
                continue
            if line is None:
                raise RuntimeError("maestro mcp exited: " + " | ".join(list(self.stderr_tail)[-3:]))
            try:
                message = json.loads(line)
            except ValueError:
                continue   # 진행 안내 등 JSON 이 아닌 줄
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(str(message["error"].get("message", message["error"])))
            return message.get("result") or {}

    def call_tool(self, name: str, arguments: dict, timeout_seconds: float) -> tuple[bool, str]:
        """tools/call > (오류 여부, 본문 글자)."""
        result = self.rpc("tools/call", {"name": name, "arguments": arguments}, timeout_seconds)
        text = "\n".join(part.get("text", "") for part in result.get("content", []) if isinstance(part, dict))
        return bool(result.get("isError")), text

    def stop(self) -> None:
        """표준입력을 닫아 스스로 끝나게 > 안 끝나면 terminate > kill."""
        if not self.process:
            return
        try:
            self.process.stdin.close()
        except OSError:
            pass
        for stopper in (None, self.process.terminate, self.process.kill):
            if stopper:
                stopper()
            try:
                self.process.wait(timeout=5)
                return
            except subprocess.TimeoutExpired:
                continue


class Relay:
    """중계 본체: 상태 파일 > maestro mcp 준비 > 127.0.0.1 요청 처리 > 유휴 종료."""

    def __init__(self, device: str, idle_minutes: float, maestro_path: str, state_path: Path):
        self.device, self.idle_seconds = device, idle_minutes * 60
        self.state_path = state_path
        self.child = MaestroChild(maestro_path, str(state_path.parent))
        self.tools: dict[str, str] = {}
        self.state = {"status": "starting", "device": device, "relay_pid": os.getpid(),
                      "idle_minutes": idle_minutes, "started_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        self.last_used = time.monotonic()

    def _save(self, **changes) -> None:
        self.state.update(changes)
        write_session(self.state_path, self.state)

    def prepare(self) -> bool:
        """도구 이름 확인 > 기기 연결 예열 (첫 호출 7~10초를 start 가 치른다). 실패면 상태에 사유를 적고 False."""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            available = self.child.start()
        except (RuntimeError, TimeoutError, OSError) as error:
            self._save(status="failed", reason="maestro_mcp_start_failed", detail=str(error)[-300:])
            return False
        self.tools, missing = resolve_tool_names(available)
        if missing:
            self._save(status="failed", reason="session_tools_missing", missing=missing, tools_available=available)
            return False
        is_error, text = self._warm_up()
        if is_error:
            self._save(status="failed", reason="device_unreachable", detail=text[-300:])
            return False
        self._save(tools=self.tools, maestro_pid=self.child.process.pid,
                   viewer={"is_disabled": self.child.is_viewer_disabled, "url": self.child.viewer_url})
        return True

    def _warm_up(self) -> tuple[bool, str]:
        try:
            return self.child.call_tool(self.tools["inspect"], {"device_id": self.device}, WARM_UP_TIMEOUT_SECONDS)
        except (RuntimeError, TimeoutError, OSError) as error:
            return True, str(error)

    def _restart_child(self) -> bool:
        _log("restarting maestro mcp (device connection lost)")
        self.child.stop()
        try:
            self.child.start()
        except (RuntimeError, TimeoutError, OSError) as error:
            _log(f"restart failed: {error}")
            return False
        is_error, _ = self._warm_up()
        self._save(maestro_pid=self.child.process.pid)
        return not is_error

    def handle_call(self, tool: str, arguments: dict, timeout_seconds: float) -> dict:
        """도구 호출. 기기 연결이 끊겼으면(다른 maestro test 가 붙었다) 다시 붙어 한 번 더."""
        name = self.tools.get(tool)
        if not name:
            return {"ok": False, "reason": "session_tool_unknown"}
        arguments = {**arguments, "device_id": self.device}
        is_reconnected = False
        for attempt in range(2):
            try:
                if not self.child.is_alive() and not self._restart_child():
                    return {"ok": False, "reason": "session_restart_failed"}
                is_error, text = self.child.call_tool(name, arguments, timeout_seconds)
            except TimeoutError:
                # 응답 없는 호출이 maestro mcp 안에 남아 있다 — 다음 호출을 위해 새로 띄운다
                self._restart_child()
                return {"ok": False, "reason": "session_timeout"}
            except (RuntimeError, OSError) as error:
                _log(f"call failed: {error}")
                is_error, text = True, "Device became unreachable: " + str(error)
            if not (is_error and any(marker in text for marker in DEVICE_UNREACHABLE_MARKERS)):
                return {"ok": True, "is_error": is_error, "text": text, "reconnected": is_reconnected}
            if attempt == 0 and self._restart_child():
                is_reconnected = True
                continue
            return {"ok": False, "reason": "device_unreachable"}
        return {"ok": False, "reason": "device_unreachable"}

    def serve(self) -> int:
        if not self.prepare():
            self.child.stop()
            return 1
        server = socket.create_server(("127.0.0.1", 0))
        server.settimeout(ACCEPT_POLL_SECONDS)
        token = secrets.token_hex(16)
        self._save(status="ready", port=server.getsockname()[1], token=token,
                   last_used=time.strftime("%Y-%m-%d %H:%M:%S"))
        _log(f"ready on port {server.getsockname()[1]} for {self.device}")
        try:
            while time.monotonic() - self.last_used < self.idle_seconds:
                try:
                    connection, _ = server.accept()
                except socket.timeout:
                    continue
                with connection:
                    if self._handle_connection(connection, token) == "stop":
                        _log("stop requested")
                        break
            else:
                _log("idle timeout reached")
        finally:
            server.close()
            self.child.stop()
            self._remove_own_state()
        return 0

    def _handle_connection(self, connection: socket.socket, token: str) -> str | None:
        connection.settimeout(10)
        received = b""
        try:
            while not received.endswith(b"\n") and len(received) < MAXIMUM_REQUEST_BYTES:
                chunk = connection.recv(65536)
                if not chunk:
                    break
                received += chunk
            payload = json.loads(received.decode("utf-8"))
        except (OSError, ValueError):
            return None
        if not hmac.compare_digest(str(payload.get("token", "")), token):
            self._reply(connection, {"ok": False, "reason": "session_token_mismatch"})
            return None
        operation = payload.get("op")
        if operation == "stop":
            self._reply(connection, {"ok": True})
            return "stop"
        if operation == "ping":
            self._reply(connection, {"ok": True, "is_maestro_alive": self.child.is_alive()})
            return None
        started = time.monotonic()
        timeout_seconds = float(payload.get("timeout_seconds") or 90)
        connection.settimeout(timeout_seconds + 60)
        reply = self.handle_call(str(payload.get("tool")), dict(payload.get("arguments") or {}), timeout_seconds)
        _log(f"call {payload.get('tool')} ok={reply.get('ok')} {time.monotonic() - started:.2f}s")
        self.last_used = time.monotonic()
        self._save(last_used=time.strftime("%Y-%m-%d %H:%M:%S"))
        self._reply(connection, reply)
        return None

    @staticmethod
    def _reply(connection: socket.socket, reply: dict) -> None:
        try:
            connection.sendall((json.dumps(reply, ensure_ascii=False) + "\n").encode("utf-8"))
        except OSError:
            pass

    def _remove_own_state(self) -> None:
        # 다른 중계가 이미 자리를 차지했으면 그 파일은 건드리지 않는다
        try:
            current = json.loads(self.state_path.read_text(encoding="utf-8"))
            if current.get("relay_pid") == os.getpid():
                self.state_path.unlink()
        except (OSError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="pro-launch Maestro session relay")
    parser.add_argument("command", choices=["serve"])
    parser.add_argument("--device", required=True)
    parser.add_argument("--idle-minutes", type=float, default=DEFAULT_IDLE_MINUTES)
    parser.add_argument("--maestro", required=True)
    parser.add_argument("--state-file", required=True)
    options = parser.parse_args(argv)
    return Relay(options.device, options.idle_minutes, options.maestro, Path(options.state_file)).serve()


if __name__ == "__main__":
    sys.exit(main())
