#!/usr/bin/env python3
"""tunnel_cli: pro-orca-tunnel 빠른 터널(cloudflared) 열기·재사용·정리, 앱 링크의 터널 주소 바꾸기 — 출력은 항상 JSON (ok·code·summary·next)
앱마다 바뀌는 사실(포트, 확인할 화면, 링크 모양)은 하네스 문서가 맡고 이 CLI 는 앱을 모름. 표준 라이브러리 전용
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tunnel import links, probe, processes, state  # noqa: E402

# 새 터널 주소가 응답할 때까지 기다리는 시간 (초)
ANSWER_WAIT_SECONDS = 40


class _BadArgumentsExit(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class JsonArgumentParser(argparse.ArgumentParser):
    """인자 오류를 stderr 대신 JSON 으로 돌려주기 위한 파서"""

    def error(self, message):
        raise _BadArgumentsExit(message)


def emit(payload: dict) -> int:
    payload.setdefault("ok", True)
    payload.setdefault("code", "ok" if payload["ok"] else "error")
    payload.setdefault("summary", None)
    payload.setdefault("next", None)
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()
    return 0 if payload["ok"] else 1


def _local_page(port: int, path: str) -> dict:
    """이 컴퓨터의 포트에 직접 물어본 결과: 응답 코드와 <title>"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=3) as response:
            body = response.read(16384).decode("utf-8", errors="replace")
            status = response.status
    except urllib.error.HTTPError as error:
        return {"status": error.code, "title": None}
    except OSError:
        return {"status": None, "title": None}
    match = re.search(r"<title>([^<]*)</title>", body, re.IGNORECASE)
    return {"status": status, "title": match.group(1).strip() if match else None}


def _local_answers(port: int, path: str) -> bool:
    status = _local_page(port, path)["status"]
    return status is not None and 200 <= status < 400


def _saved_tunnel(port: int) -> dict | None:
    record = state.load()["tunnels"].get(str(port))
    if not record or not processes.is_alive(int(record.get("pid") or 0)):
        return None
    url = record.get("url") or processes.url_from_log(Path(record.get("log") or ""))
    return {**record, "url": url} if url else None


def _wait_answer(url: str, path: str) -> dict:
    deadline = time.time() + ANSWER_WAIT_SECONDS
    result = probe.check(url, path)
    while not result["answers"] and time.time() < deadline:
        time.sleep(2)
        result = probe.check(url, path)
    return result


# 서브커맨드: 입력 해석 > 모듈 호출 > 결과 + next

def cmd_status(_args) -> dict:
    saved = state.load()["tunnels"]
    rows = []
    for tunnel in processes.quick_tunnels():
        record = saved.get(str(tunnel["port"])) or {}
        url = record.get("url") if record.get("pid") == tunnel["pid"] else None
        rows.append({**tunnel, "url": url, "is_managed": url is not None,
                     "answers": probe.check(url)["answers"] if url else None})
    return {"cloudflared": processes.cloudflared_path(), "tunnels": rows,
            "summary": f"{len(rows)} quick tunnel(s) running",
            "next": "open --port N to reuse or start one" if rows else "open --port N"}


def cmd_open(args) -> dict:
    binary = processes.cloudflared_path()
    if not binary:
        return {"ok": False, "code": "tool_missing", "summary": "cloudflared is not installed",
                "next": "install it: macOS `brew install cloudflared`, Windows `winget install Cloudflare.cloudflared`, then run open again"}
    if not _local_answers(args.port, args.path):
        return {"ok": False, "code": "local_not_listening",
                "summary": f"nothing answers on http://127.0.0.1:{args.port}{args.path}",
                "next": "start the app first, or find its port with the harness"}
    # 살아 있고 응답하면 그대로 씀
    saved = _saved_tunnel(args.port)
    if saved and not args.fresh:
        result = probe.check(saved["url"], args.path)
        if result["answers"]:
            return {"url": saved["url"], "port": args.port, "pid": saved["pid"], "is_reused": True, **result,
                    "summary": f"reused live tunnel {saved['url']}"}
    # 같은 포트의 죽은·옛 터널 정리 > 새로 띄움
    stopped = [tunnel["pid"] for tunnel in processes.quick_tunnels()
               if tunnel["port"] == args.port and processes.stop(tunnel["pid"])]
    log_path = state.log_path_for(args.port)
    pid = processes.start(binary, args.port, log_path)
    url = processes.wait_for_url(log_path, pid)
    if not url:
        return {"ok": False, "code": "no_tunnel_url", "pid": pid, "log": str(log_path),
                "summary": "cloudflared started but printed no trycloudflare address",
                "next": f"read {log_path}; check the network, then run open again"}
    state.remember_tunnel(args.port, pid, url, log_path)
    result = _wait_answer(url, args.path)
    return {"url": url, "port": args.port, "pid": pid, "is_reused": False, "stopped_pids": stopped, **result,
            "ok": result["answers"], "code": "ok" if result["answers"] else "not_answering",
            "summary": f"opened {url}" + ("" if result["local_dns_ready"] else " (this Mac's DNS may lag; other devices are fine)"),
            "next": None if result["answers"] else f"run `open --port {args.port}` again in a minute"}


def cmd_ports(args) -> dict:
    ports = processes.listening_ports_of(args.process)
    return {"process": args.process, "ports": ports,
            "summary": f"{len(ports)} listening port(s) for processes named like '{args.process}'",
            "next": "check each with `local --port N`" if ports else "is the app running?"}


def cmd_local(args) -> dict:
    page = _local_page(args.port, args.path)
    return {"port": args.port, "path": args.path, **page, "ok": page["status"] is not None,
            "code": "ok" if page["status"] is not None else "local_not_listening",
            "summary": f"{args.port}{args.path}: status {page['status']}, title {page['title']!r}"}


def cmd_stop(args) -> dict:
    targets = [tunnel for tunnel in processes.quick_tunnels() if args.all or tunnel["port"] == args.port]
    stopped = [tunnel["pid"] for tunnel in targets if processes.stop(tunnel["pid"])]
    for tunnel in targets:
        state.forget_tunnel(tunnel["port"])
    return {"stopped_pids": stopped, "summary": f"stopped {len(stopped)} of {len(targets)} quick tunnel(s)"}


def cmd_link_save(args) -> dict:
    # 링크는 명령줄 인자로 받지 않음 (프로세스 목록에 남지 않게)
    link = os.environ.get("TUNNEL_LINK", "").strip()
    if not link:
        return {"ok": False, "code": "no_link", "summary": "TUNNEL_LINK is empty",
                "next": "TUNNEL_LINK='<link the user pasted>' ... link save --app NAME"}
    links.save(args.app, link)
    return {"app": args.app, "summary": f"saved the {args.app} link (owner-only file)"}


def cmd_link_get(args) -> dict:
    link = links.load(args.app)
    if not link:
        return {"ok": False, "code": "no_saved_link",
                "summary": f"no saved {args.app} link",
                "next": f"ask the user for one fresh link from the app, then `link save --app {args.app}`"}
    new_host = urllib.parse.urlparse(args.url).hostname or ""
    updated, replaced = links.retarget(link, new_host)
    if replaced == 0:
        return {"ok": False, "code": "host_not_found",
                "summary": "no trycloudflare address found in the saved link (the app's link format may have changed)",
                "next": "follow the harness: ask for a fresh link, save it, and note the change in the harness"}
    return {"link": updated, "replaced": replaced, "summary": f"{replaced} address(es) switched to {new_host}"}


def build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(prog="tunnel_cli")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=JsonArgumentParser)
    commands.add_parser("status").set_defaults(handler=cmd_status)
    opener = commands.add_parser("open")
    opener.add_argument("--port", type=int, required=True)
    opener.add_argument("--path", default="/", help="page to check through the tunnel")
    opener.add_argument("--fresh", action="store_true", help="always start a new tunnel")
    opener.set_defaults(handler=cmd_open)
    porter = commands.add_parser("ports")
    porter.add_argument("--process", required=True, help="part of the process name, e.g. orca")
    porter.set_defaults(handler=cmd_ports)
    local = commands.add_parser("local")
    local.add_argument("--port", type=int, required=True)
    local.add_argument("--path", default="/")
    local.set_defaults(handler=cmd_local)
    stopper = commands.add_parser("stop")
    target = stopper.add_mutually_exclusive_group(required=True)
    target.add_argument("--port", type=int)
    target.add_argument("--all", action="store_true")
    stopper.set_defaults(handler=cmd_stop)
    link = commands.add_parser("link")
    link_commands = link.add_subparsers(dest="link_command", required=True, parser_class=JsonArgumentParser)
    saver = link_commands.add_parser("save")
    saver.add_argument("--app", required=True)
    saver.set_defaults(handler=cmd_link_save)
    getter = link_commands.add_parser("get")
    getter.add_argument("--app", required=True)
    getter.add_argument("--url", required=True, help="current tunnel URL from `open`")
    getter.set_defaults(handler=cmd_link_get)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except _BadArgumentsExit as error:
        return emit({"ok": False, "code": "bad_args", "summary": error.message,
                     "next": "commands: status, ports --process NAME, local --port N, open --port N, stop --port N|--all, link save|get --app NAME"})
    try:
        return emit(args.handler(args))
    except Exception as error:  # noqa: BLE001 — 예상 못 한 예외도 JSON 으로
        return emit({"ok": False, "code": "internal_error", "summary": f"{type(error).__name__}: {error}"})


if __name__ == "__main__":
    sys.exit(main())
