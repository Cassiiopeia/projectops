#!/usr/bin/env python3
"""remote_link_cli: pro-remote-link one link to open a desktop app from outside — output is always JSON (ok·code·summary·next)
Tunnel apps (Orca): cloudflared quick tunnel open, reuse, cleanup + swap the tunnel host in the saved link
Relay apps (Paseo): the app's own CLI makes a fresh pairing link. Per-app facts live in harness/<app>.md. Standard library only
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from remote_apps import SUPPORTED_APPS, harness_path  # noqa: E402
from tunnel import links, probe, processes, state  # noqa: E402

# Time to wait for the new tunnel address to respond (seconds)
ANSWER_WAIT_SECONDS = 40


class _BadArgumentsExit(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class JsonArgumentParser(argparse.ArgumentParser):
    """Parser that returns argument errors as JSON instead of stderr"""

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


def _local_answers(port: int, path: str) -> bool:
    status = probe.local_page(port, path)["status"]
    return status is not None and 200 <= status < 400


def _wait_answer(url: str, path: str) -> dict:
    deadline = time.time() + ANSWER_WAIT_SECONDS
    result = probe.check(url, path)
    while not result["answers"] and time.time() < deadline:
        time.sleep(2)
        result = probe.check(url, path)
    return result


# Subcommands: parse input > call module > result + next

def cmd_apps(_args) -> dict:
    rows = []
    for name, adapter in SUPPORTED_APPS.items():
        harness = harness_path(name)
        rows.append({"app": name, "connection": adapter.CONNECTION,
                     "harness": str(harness) if harness else None, **adapter.inspect()})
    reachable = [row["app"] for row in rows if row["is_reachable"]]
    return {"apps": rows, "summary": f"{len(rows)} supported app(s); reachable from outside now: {', '.join(reachable) or 'none'}",
            "next": "link get --app NAME (tunnel apps also need --url from open)"}


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
    # Alive and responding > reuse as is
    saved = processes.live_tunnel(args.port)
    if saved and not args.fresh:
        result = probe.check(saved["url"], args.path)
        if result["answers"]:
            return {"url": saved["url"], "port": args.port, "pid": saved["pid"], "is_reused": True, **result,
                    "summary": f"reused live tunnel {saved['url']}"}
    # Clean up dead or old tunnels on the same port > start a new one
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
    page = probe.local_page(args.port, args.path)
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
    adapter = SUPPORTED_APPS.get(args.app)
    if adapter and adapter.CONNECTION == "relay":
        return {"ok": False, "code": "not_needed", "summary": f"{args.app} makes a fresh link each time; nothing to save",
                "next": f"link get --app {args.app}"}
    # The link is not taken as a command-line argument (so it doesn't show in the process list)
    link = os.environ.get("TUNNEL_LINK", "").strip()
    if not link:
        return {"ok": False, "code": "no_link", "summary": "TUNNEL_LINK is empty",
                "next": "TUNNEL_LINK='<link the user pasted>' ... link save --app NAME"}
    links.save(args.app, link)
    return {"app": args.app, "summary": f"saved the {args.app} link (owner-only file)"}


def _tunnel_link(args) -> dict:
    if not args.url:
        return {"ok": False, "code": "url_required", "summary": f"{args.app} is reached through a tunnel; --url is required",
                "next": f"open --port N (port from harness/{args.app}.md), then link get --app {args.app} --url <url>"}
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


def cmd_link_get(args) -> dict:
    """Relay apps > the app's CLI makes the link. Every other app > saved link pointed at the tunnel URL"""
    adapter = SUPPORTED_APPS.get(args.app)
    if adapter and adapter.CONNECTION == "relay":
        return adapter.fresh_link(should_enable_relay=args.enable_relay)
    return _tunnel_link(args)


def build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(prog="remote_link_cli")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=JsonArgumentParser)
    commands.add_parser("apps").set_defaults(handler=cmd_apps)
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
    getter.add_argument("--url", help="current tunnel URL from `open` (tunnel apps only)")
    getter.add_argument("--enable-relay", action="store_true",
                        help="relay apps: turn the relay on while pairing (only after the user agreed)")
    getter.set_defaults(handler=cmd_link_get)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except _BadArgumentsExit as error:
        return emit({"ok": False, "code": "bad_args", "summary": error.message,
                     "next": "commands: apps, status, ports --process NAME, local --port N, open --port N, stop --port N|--all, link save --app NAME, link get --app NAME [--url URL] [--enable-relay]"})
    try:
        return emit(args.handler(args))
    except Exception as error:  # noqa: BLE001 — unexpected exceptions also go out as JSON
        return emit({"ok": False, "code": "internal_error", "summary": f"{type(error).__name__}: {error}",
                     "next": "An unexpected error in the CLI. Report it with pro-skill-bug"})


if __name__ == "__main__":
    sys.exit(main())
