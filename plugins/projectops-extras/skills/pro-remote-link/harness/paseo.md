# Paseo facts (harness)

> Paseo changes often. Everything here can go stale. When a step below fails, find the new fact,
> write it into the local copy `~/.projectops/remote-link/harness/paseo.md` (create it from this file), add a line under
> "Change log", and tell the user. The local copy wins over this file.
> Docs: https://paseo.sh/docs/connectivity.md , https://paseo.sh/docs/security.md , https://paseo.sh/docs/configuration.md

Last checked: Paseo desktop 0.15.4 (desktop-managed daemon) on macOS, 2026-11-15. Windows and Linux lines marked
"not checked yet" are best guesses.

## How it is reached

- **Relay, no tunnel.** The daemon keeps a connection to `relay.paseo.sh`; the hosted web app `https://app.paseo.sh`
  joins it with a pairing link. No cloudflared, no open port, nothing to save between requests.
- The daemon itself listens on `127.0.0.1:6767` (loopback only). Leave it there.

## Where the CLI is

`link get --app paseo` looks in this order: `PROJECTOPS_PASEO_CLI` (full path to the executable) > `paseo` on `PATH` >
the copy inside the desktop app.

- macOS: `/Applications/Paseo.app/Contents/Resources/bin/paseo` (also `~/Applications/...`). Not on `PATH` by default.
- Windows (not checked yet): `C:\Program Files\Paseo\resources\bin\paseo.cmd`; a per-user install may be under
  `%LOCALAPPDATA%\Programs\Paseo\resources\bin\paseo.cmd`.
- Linux (not checked yet): `<install-dir>/resources/bin/paseo`; the CLI checks `/opt/Paseo/resources/bin/paseo`.
  For another install dir set `PROJECTOPS_PASEO_CLI`.

## Run it from the home folder

- With a working directory the process may not read (macOS: a folder under `~/Desktop` without Full Disk Access),
  the CLI crashes at start: `Error: EPERM: process.cwd failed with error operation not permitted, uv_cwd`.
- `remote_link_cli.py` always runs it with the home folder as the working directory. Do the same when running it by hand.

## Daemon and relay checks (read only)

- Running: `paseo daemon status --json` has `"localDaemon": "running"` (also `listen`, `desktopManaged`, `daemonVersion`).
  A `note` about `DAEMON_REQUEST_TIMEOUT` is normal and does not mean it is down.
- Relay: `paseo daemon config get daemon.relay` returns `{"source":..., "path":"daemon.relay", "set":true, "value":{"enabled":true}}`.
  Relay is off on new installs.
- Relay off: do not turn it on silently. The CLI answers `relay_off`; ask the user. If they agree,
  `link get --app paseo --enable-relay` runs `paseo daemon pair --json --relay` (enables relay while pairing).
  Whether that needs a daemon restart was not checked yet.
- Never restart or stop the daemon, change `daemon.listen`, or turn on `features.webUi.enabled`. With a
  desktop-managed daemon a restart can cut off the session that asked.

## If Paseo is not running

- macOS: `open -a Paseo` (the desktop app starts its daemon).
- Windows (not checked yet): start Paseo from the Start menu.
- Linux (not checked yet): start the Paseo desktop entry or AppImage the user installed.
- Wait up to 30 seconds and run `apps` again. Still not running: tell the user and stop.

## The link the user opens

- `paseo daemon pair --json` prints a **new** link every call:
  `{"relayEnabled": true, "url": "https://app.paseo.sh/#offer=<base64url>", "qr": "...", "connectionUri": "relay://relay.paseo.sh:443/<serverId>?key=...&ssl=true"}`.
- The CLI returns only `url` as `link`. `qr` and `connectionUri` are dropped.
- The user opens the link in a browser (or pastes it in the Paseo phone app). The link is the trust anchor: anyone
  holding it can connect unless a password is set.

## Password

- A daemon password is a bcrypt hash at `daemon.auth.password` in `config.json`. The CLI reads only whether
  `daemon config get daemon.auth` has a password; the hash never leaves the adapter.
- No password: the reply carries `warning` and `warning_fix`. Pass the warning to the user in one line with the fix:
  `paseo daemon set-password` (prompts for the password; the daemon needs a restart afterwards, so the user decides when).
- Not visible to the CLI: a `PASEO_PASSWORD` set in the daemon's own environment. For a desktop-managed daemon that is
  unlikely, but `has_password: false` only means "none in config.json".
- Relay clients must send the password too when one is set (inside the encrypted channel).

## Change log

- 2026-11-15: first version.
