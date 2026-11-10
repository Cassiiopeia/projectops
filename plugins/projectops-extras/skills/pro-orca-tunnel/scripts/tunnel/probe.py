"""주소 확인: Cloudflare DNS(HTTPS)로 이름 풀기 > 그 IP 로 직접 접속해 상태 코드 확인 (로컬 DNS 지연과 무관)"""
from __future__ import annotations

import json
import socket
import ssl
import urllib.parse
import urllib.request

DNS_OVER_HTTPS = "https://cloudflare-dns.com/dns-query"


def resolve_public(host: str) -> list[str]:
    query = urllib.parse.urlencode({"name": host, "type": "A"})
    request = urllib.request.Request(f"{DNS_OVER_HTTPS}?{query}", headers={"accept": "application/dns-json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            answer = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return []
    return [item["data"] for item in answer.get("Answer") or [] if item.get("type") == 1 and item.get("data")]


def resolves_locally(host: str) -> bool:
    try:
        socket.getaddrinfo(host, 443)
    except OSError:
        return False
    return True


def http_status(host: str, ip: str, path: str = "/") -> int | None:
    """host 이름(SNI)으로 ip 에 직접 접속한 응답 코드. 실패하면 None"""
    context = ssl.create_default_context()
    try:
        with socket.create_connection((ip, 443), timeout=10) as raw:
            with context.wrap_socket(raw, server_hostname=host) as connection:
                request = f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: projectops-tunnel\r\nConnection: close\r\n\r\n"
                connection.sendall(request.encode("ascii"))
                status_line = connection.recv(256).decode("latin-1").split("\r\n", 1)[0]
    except (OSError, ssl.SSLError):
        return None
    parts = status_line.split()
    return int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else None


def check(url: str, path: str = "/") -> dict:
    """{answers, status, local_dns_ready}: answers 는 2xx·3xx 로 응답했는가"""
    host = urllib.parse.urlparse(url).hostname or ""
    addresses = resolve_public(host)
    status = http_status(host, addresses[0], path) if addresses else None
    return {"answers": status is not None and 200 <= status < 400, "status": status,
            "local_dns_ready": resolves_locally(host)}
