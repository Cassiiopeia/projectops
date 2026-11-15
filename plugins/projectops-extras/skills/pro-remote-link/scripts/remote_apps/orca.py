"""Orca adapter (tunnel): find Orca Web on this computer, the live quick tunnel for it, the saved pairing link
Port and page title mirror harness/orca.md; when Orca changes them, update both
"""
from __future__ import annotations

from tunnel import links, probe, processes

NAME = "orca"
CONNECTION = "tunnel"
# Orca Web built-in server (harness/orca.md "Where Orca Web listens")
ORCA_WEB_PORT = 6768
ORCA_WEB_PATH = "/web-index.html"
ORCA_WEB_TITLE = "Orca Web"


def _is_orca_web(port: int) -> bool:
    return probe.local_page(port, "/")["title"] == ORCA_WEB_TITLE


def find_port() -> int | None:
    """Orca Web port: the known port first, then every port the orca process listens on"""
    if _is_orca_web(ORCA_WEB_PORT):
        return ORCA_WEB_PORT
    for port in processes.listening_ports_of(NAME):
        if port != ORCA_WEB_PORT and _is_orca_web(port):
            return port
    return None


def inspect() -> dict:
    """Running (Orca Web answers locally) > reachable (a live tunnel for that port answers from outside)"""
    port = find_port()
    tunnel = processes.live_tunnel(port) if port else None
    is_reachable = probe.check(tunnel["url"], ORCA_WEB_PATH)["answers"] if tunnel else False
    if port is None:
        next_step = "start Orca desktop (harness/orca.md 'If Orca is not running')"
    else:
        next_step = f"open --port {port} --path {ORCA_WEB_PATH}, then link get --app orca --url <url>"
    return {"is_running": port is not None, "port": port, "path": ORCA_WEB_PATH,
            "tunnel_url": tunnel["url"] if tunnel else None, "is_reachable": is_reachable,
            "has_saved_link": links.load(NAME) is not None, "next": next_step}
