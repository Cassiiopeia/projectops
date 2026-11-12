---
name: pro-orca-tunnel
description: "Give a public Orca Web URL on request: reuse the live cloudflared quick tunnel or open a new one, and return the user's saved Orca pairing link pointed at it. Orca-specific facts live in a harness the agent updates. Use for 'give me the Orca URL', 'open Orca remotely'."
---

# Orca tunnel

## When to use

- "Give me the Orca URL", "Orca address", "I want to open Orca from outside", "make the Orca link again"
- The user is away from the Mac (Claude remote control, another account or device) and wants Orca desktop in a browser.
- Not this skill: exposing a service on a domain for good is `pro-synology-expose`.
- No Cloudflare account or login: quick tunnels (`*.trycloudflare.com`) work without one. Only `cloudflared` must be installed.

**Goal: answer with one URL the user can open.** Say nothing about tunnels, logs or retries unless something failed.
Reply in the user's language.

## Two parts

| Part | Where | Changes when |
|---|---|---|
| Tunnel: open, reuse, stop, check, swap the host inside a link | `scripts/tunnel_cli.py` (standard library only) | Rarely |
| Orca facts: port, page to check, link shape, how to get a fresh link | `harness/orca.md`, overridden by `~/.projectops/tunnel/harness/orca.md` | Whenever Orca updates |

Read the harness first (local copy if it exists). If a fact there turns out wrong, fix the local copy and add a line to its change log.

## Find the scripts

macOS, Linux, Git Bash:

```bash
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
SKILL_DIR="$(git rev-parse --show-toplevel 2>/dev/null)/plugins/projectops-extras/skills/pro-orca-tunnel"
[ -d "$SKILL_DIR" ] || SKILL_DIR=$(find ~/.claude/plugins/cache ~/.codex/plugins/cache -maxdepth 8 -type d -path "*/projectops-extras/*skills/pro-orca-tunnel" 2>/dev/null | sort -V | tail -1)
echo "PYTHON=$PYTHON SKILL_DIR=$SKILL_DIR"
```

Windows PowerShell:

```powershell
$SkillDir = Get-ChildItem "$HOME\.claude\plugins\cache","$HOME\.codex\plugins\cache" -Directory -Recurse -Filter pro-orca-tunnel -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -like "*projectops-extras*" } | Sort-Object FullName | Select-Object -Last 1 -ExpandProperty FullName
$SkillDir
```

On Windows run `python "$SkillDir\scripts\tunnel_cli.py" <command>`; the commands are the same.

Every command is `PYTHONIOENCODING=utf-8 {PYTHON} {SKILL_DIR}/scripts/tunnel_cli.py <command>`. Output is JSON (`ok`, `code`, `summary`, `next`).

| Command | Does |
|---|---|
| `status` | Quick tunnels running on this machine, which one this skill manages, whether it answers |
| `ports --process NAME` | TCP ports a process (name contains NAME) listens on: macOS, Windows, Linux |
| `local --port N [--path P]` | Status code and `<title>` of a local page (use it instead of curl, so it works the same on Windows) |
| `open --port N [--path P] [--fresh]` | Reuse the live tunnel for the port, or stop stale ones for that port and start a new detached one. Waits until it answers |
| `stop --port N` · `stop --all` | Stop quick tunnels |
| `link save --app orca` | Save the link in `TUNNEL_LINK` (owner-only file under `~/.projectops/tunnel/`) |
| `link get --app orca --url URL` | The saved link with every tunnel host switched to URL |

## Flow for "give me the Orca URL"

1. Read the harness. Check the port it names with `local`; if it is not Orca Web, use `ports` and the harness "not running" steps.
2. `open --port <port> --path /web-index.html` → `url`. A reused tunnel is normal and fast.
3. `link get --app orca --url <url>` → `link`. Send the user only that link.
4. `no_saved_link` or `host_not_found`: ask the user once for a fresh pairing link from Orca desktop, then
   `TUNNEL_LINK='<link>' ... link save --app orca` and repeat step 3. On `host_not_found`, also note in the harness that
   the link format changed.
5. `local_dns_ready: false` only means this Mac's resolver has not seen the new name yet. Other devices are fine; do not retry for that.

## Rules

- The link contains a device token: it is a key to this Mac's terminals. Send it only to the user in this chat.
  Never put it in issues, commits, logs or other services.
- Stop only quick tunnels for the port you are opening, or all of them when the user asks.
- Tunnels started by `open` are detached, so they outlive the agent session. They still die when the Mac sleeps or the
  network changes; the next request opens a new one.

## Codes

| `code` | Do |
|---|---|
| `tool_missing` | Install cloudflared (`next` has the command), then retry |
| `local_not_listening` | Orca Web is not on that port: follow the harness |
| `no_tunnel_url` · `not_answering` | Read the log path in the reply; retry `open` once |
| `no_saved_link` · `host_not_found` | Ask for a fresh pairing link (step 4) |
