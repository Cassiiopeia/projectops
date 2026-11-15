---
name: pro-remote-link
description: "Give one link to open a desktop agent app (Orca, Paseo) on this computer from outside: Orca through a cloudflared quick tunnel and its saved pairing link, Paseo through its relay pairing link. Use for 'Orca link', 'Orca URL', 'Orca tunnel', 'Paseo link', 'remote link', 'open from outside'."
---

# Remote link

## When to use

- "Give me the Orca URL / Orca link", "Paseo link", "remote link", "I want to open Orca / Paseo from outside", "make the link again"
- The user is away from the computer (Claude remote control, another account or device) and wants a desktop app in a browser.
- Not this skill: exposing a service on a domain for good is `pro-synology-expose`.

**Goal: answer with one link the user can open.** Say nothing about tunnels, relays, logs or retries unless something failed.
Reply in the user's language. If the user names no app, run `apps` and use the one that is running (ask only if both are).

## Supported apps

| App | Connection | Needs | Harness |
|---|---|---|---|
| `orca` | tunnel: cloudflared quick tunnel (`*.trycloudflare.com`) + the user's saved pairing link | `cloudflared` installed; no Cloudflare account | `harness/orca.md` |
| `paseo` | relay: the Paseo CLI makes a fresh `https://app.paseo.sh/#offer=...` link; no tunnel, nothing saved | Paseo desktop running, relay on | `harness/paseo.md` |

Each app has a harness with its facts (port, CLI location, link shape, what to do when it is not running).
A local copy `~/.projectops/remote-link/harness/<app>.md` wins over the bundled one. Read the harness first (`apps` shows
which file is in effect). If a fact there turns out wrong, fix the local copy and add a line to its change log.

**Adding an app:** write `harness/<app>.md` and `scripts/remote_apps/<app>.py` (`NAME`, `CONNECTION`, `inspect()`;
relay apps add `fresh_link()`), then register it in `scripts/remote_apps/__init__.py`.

## Find the scripts

macOS, Linux, Git Bash:

```bash
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
SKILL_DIR="$(git rev-parse --show-toplevel 2>/dev/null)/plugins/projectops-extras/skills/pro-remote-link"
[ -d "$SKILL_DIR" ] || SKILL_DIR=$(find ~/.claude/plugins/cache ~/.codex/plugins/cache -maxdepth 8 -type d -path "*/projectops-extras/*skills/pro-remote-link" 2>/dev/null | sort -V | tail -1)
echo "PYTHON=$PYTHON SKILL_DIR=$SKILL_DIR"
```

Windows PowerShell:

```powershell
$SkillDir = Get-ChildItem "$HOME\.claude\plugins\cache","$HOME\.codex\plugins\cache" -Directory -Recurse -Filter pro-remote-link -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -like "*projectops-extras*" } | Sort-Object FullName | Select-Object -Last 1 -ExpandProperty FullName
$SkillDir
```

On Windows run `python "$SkillDir\scripts\remote_link_cli.py" <command>`; the commands are the same.

Every command is `PYTHONIOENCODING=utf-8 {PYTHON} {SKILL_DIR}/scripts/remote_link_cli.py <command>`. Output is JSON (`ok`, `code`, `summary`, `next`).

| Command | Does |
|---|---|
| `apps` | Supported apps, how each connects, whether each is running and reachable from outside now, harness in effect |
| `status` | Quick tunnels running on this machine, which one this skill manages, whether it answers |
| `ports --process NAME` | TCP ports a process (name contains NAME) listens on: macOS, Windows, Linux |
| `local --port N [--path P]` | Status code and `<title>` of a local page (use it instead of curl, so it works the same on Windows) |
| `open --port N [--path P] [--fresh]` | Reuse the live tunnel for the port, or stop stale ones for that port and start a new detached one. Waits until it answers |
| `stop --port N` · `stop --all` | Stop quick tunnels |
| `link save --app orca` | Save the link in `TUNNEL_LINK` (owner-only file under `~/.projectops/remote-link/`). Tunnel apps only |
| `link get --app orca --url URL` | Tunnel apps: the saved link with every tunnel host switched to URL |
| `link get --app paseo [--enable-relay]` | Relay apps: a fresh pairing link from the app's CLI. `--enable-relay` only after the user agreed |

## Flow: Orca (tunnel)

1. Read the harness. Check the port it names with `local`; if it is not Orca Web, use `ports` and the harness "not running" steps.
2. `open --port <port> --path /web-index.html` → `url`. A reused tunnel is normal and fast.
3. `link get --app orca --url <url>` → `link`. Send the user only that link.
4. `no_saved_link` or `host_not_found`: ask the user once for a fresh pairing link from Orca desktop, then
   `TUNNEL_LINK='<link>' ... link save --app orca` and repeat step 3. On `host_not_found`, also note in the harness that
   the link format changed.
5. `local_dns_ready: false` only means this computer's resolver has not seen the new name yet. Other devices are fine; do not retry for that.

## Flow: Paseo (relay)

1. Read the harness. `link get --app paseo` → `link` (`https://app.paseo.sh/#offer=...`). It is new on every call.
2. Send the user only that link. If the reply has `warning` (no daemon password), add it in one line with `warning_fix`.
3. `relay_off`: ask the user whether to turn on the Paseo relay. Only if they agree, run `link get --app paseo --enable-relay`.
4. `app_not_running` or `tool_missing`: follow the harness ("If Paseo is not running", "Where the CLI is").

## Rules

- **The link is a key** to this computer's agents and terminals. Send it only to the user in this chat.
  Never put it in issues, commits, logs, reports or other services.
- Never restart or stop an app's daemon, change its listen address or turn on its web UI. A restart can cut off the
  session that asked. Turning on the Paseo relay or setting a password happens only when the user asks.
- Stop only quick tunnels for the port you are opening, or all of them when the user asks.
- Tunnels started by `open` are detached, so they outlive the agent session. They still die when the computer sleeps or the
  network changes; the next request opens a new one.

## Codes

| `code` | Do |
|---|---|
| `tool_missing` | Orca: install cloudflared (`next` has the command). Paseo: the CLI was not found, see the harness |
| `local_not_listening` | Orca Web is not on that port: follow the harness |
| `no_tunnel_url` · `not_answering` | Read the log path in the reply; retry `open` once |
| `no_saved_link` · `host_not_found` | Ask for a fresh Orca pairing link (Orca step 4) |
| `url_required` | Tunnel app without `--url`: run `open` first |
| `relay_off` | Ask the user before `--enable-relay` (Paseo step 3) |
| `app_not_running` | Start the app as the harness says, then `apps` again |
| `pair_failed` | The app's CLI gave no link: read `stderr` and the harness; the output shape may have changed |
| `not_needed` | Relay apps have nothing to save; use `link get` |
