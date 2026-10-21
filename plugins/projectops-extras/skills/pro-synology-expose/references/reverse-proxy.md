> When to read: when you build the Step 2 (DSM reverse proxy) guide. Field tables for the 2 rules, the 9 WebSocket headers and advanced settings, and output examples (regular and WebSocket).

## Step 2: Synology DSM reverse proxy setup

**Location**: DSM > Control Panel > Login Portal > Advanced tab > Reverse Proxy > "Create"
(Korean DSM: 제어판 > 로그인 포털 > 고급 > 역방향 프록시 > "생성")

Create **2 rules** in total: one for HTTPS (443) and one for the HTTP→HTTPS redirect (80→443).

### Rule 1: HTTPS proxy (443 → local port)

**General tab:**

| Field | Value |
|------|-----|
| Reverse proxy name | `{service_name} 443→{local_port}` |
| **Source** | |
| Protocol | `HTTPS` |
| Hostname | `{subdomain}.{domain}` |
| Port | `443` |
| Enable HSTS | checked |
| Access control profile | `Not configured` |
| **Destination** | |
| Protocol | `HTTP` |
| Hostname | `localhost` |
| Port | `{local_port}` |

### Rule 2: HTTP → HTTPS redirect (80 → 443)

**General tab:**

| Field | Value |
|------|-----|
| Reverse proxy name | `{service_name} 80→443` |
| **Source** | |
| Protocol | `HTTP` |
| Hostname | `{subdomain}.{domain}` |
| Port | `80` |
| Enable HSTS | unchecked |
| **Destination** | |
| Protocol | `HTTPS` |
| Hostname | `{subdomain}.{domain}` |
| Port | `443` |

---

### (Conditional) Extra settings for WebSocket services

Add the settings below to **Rule 1 (the HTTPS proxy)** only when the service uses WebSocket. Skip this section for regular services that do not use WebSocket.

#### Custom Header tab

Press "Create" and add all 9 headers below:

| Header name | Value |
|-------------|-----|
| `Upgrade` | `$http_upgrade` |
| `Connection` | `$connection_upgrade` |
| `Sec-WebSocket-Key` | `$http_sec_websocket_key` |
| `Sec-WebSocket-Version` | `13` |
| `Sec-WebSocket-Extensions` | `$http_sec_websocket_extensions` |
| `X-Forwarded-Proto` | `https` |
| `X-Forwarded-For` | `$proxy_add_x_forwarded_for` |
| `Authorization` | `$http_authorization` |
| `Proxy-Authorization` | `$http_authorization` |

#### Advanced Settings tab (optional)

The default timeout is 60 seconds. If the service has operations that take longer than 60 seconds, raise it to the value the user gave.

| Field | Value |
|------|-----|
| Proxy connection timeout (s) | `{timeout}` (default 60) |
| Proxy send timeout (s) | `{timeout}` (default 60) |
| Proxy read timeout (s) | `{timeout}` (default 60) |
| Proxy HTTP version | `HTTP 1.1` |
| Use the error page sent back from the destination server | checked |

---

### Output example (regular service)

```
[Step 2] Reverse proxy setup (create 2)

[Rule 1] {service_name} 443→{local_port}
  General tab:
    Source: HTTPS://{subdomain}.{domain}:443 (HSTS enabled)
    Destination: HTTP://localhost:{local_port}

[Rule 2] {service_name} 80→443
  General tab:
    Source: HTTP://{subdomain}.{domain}:80
    Destination: HTTPS://{subdomain}.{domain}:443
```

### Output example (WebSocket service)

```
[Step 2] Reverse proxy setup (create 2)

[Rule 1] {service_name} 443→{local_port}
  General tab:
    Source: HTTPS://{subdomain}.{domain}:443 (HSTS enabled)
    Destination: HTTP://localhost:{local_port}
  Custom Header tab (add 9):
    Upgrade: $http_upgrade
    Connection: $connection_upgrade
    Sec-WebSocket-Key: $http_sec_websocket_key
    Sec-WebSocket-Version: 13
    Sec-WebSocket-Extensions: $http_sec_websocket_extensions
    X-Forwarded-Proto: https
    X-Forwarded-For: $proxy_add_x_forwarded_for
    Authorization: $http_authorization
    Proxy-Authorization: $http_authorization
  Advanced Settings tab:
    Proxy connection/send/read timeout: {timeout}s
    Proxy HTTP version: HTTP 1.1
    Use destination server's error page: checked

[Rule 2] {service_name} 80→443
  General tab:
    Source: HTTP://{subdomain}.{domain}:80
    Destination: HTTPS://{subdomain}.{domain}:443
```
