# Orca facts (harness)

> Orca is open source and changes often. Everything here can go stale. When a step below fails, find the new fact,
> write it into the local copy `~/.projectops/tunnel/harness/orca.md` (create it from this file), add a line under
> "Change log", and tell the user. The local copy wins over this file.

Last checked: Orca 1.4.253 on macOS, 2026-11-11. Windows and Linux lines marked "not checked yet" are best guesses.

## Where Orca Web listens

- Port **6768** (the desktop app's built-in web server, bound to all interfaces).
- Check: `local --port 6768` returns `title: "Orca Web"`.
- If 6768 does not answer: `ports --process orca` lists the ports the Orca process listens on (works on macOS, Windows
  and Linux); run `local --port N` on each and take the one titled `Orca Web`.
- Not Orca Web: the second, loopback-only port (for example `127.0.0.1:61115`) answers 404 at `/`.

## If Orca is not running

- macOS: `open -a Orca`.
- Windows (PowerShell, not checked yet): `Start-Process "$env:LOCALAPPDATA\Programs\Orca\Orca.exe"`;
  if that path is missing, find `Orca.exe` under `$env:LOCALAPPDATA\Programs` or the Start menu shortcut.
- Linux (not checked yet): start the `orca` desktop entry or AppImage the user installed.
- Wait up to 30 seconds and check again. Still nothing: tell the user Orca desktop is not running on that computer and stop.
- When you confirm a Windows or Linux path, replace "not checked yet" with the version and date.

## The link the user opens

- Shape: `https://<tunnel>/web-index.html#pairing=<percent-encoded orca://pair?code=...>`
- The `code` is base64 of a JSON object. Its `endpoint` is `wss://<tunnel host>`; the rest
  (`deviceToken`, `pairedDeviceId`, `publicKeyB64`, `hostDescriptor`) binds the browser to this Mac.
- Only the tunnel host changes between tunnels. `link get` swaps every `*.trycloudflare.com` inside the link,
  including inside the base64 JSON, without knowing the field names.
- The page to check through the tunnel: `/web-index.html`.

## Getting a fresh pairing link

- In Orca desktop the user creates a link for a browser or phone (Orca 모바일 / web pairing in the sidebar).
  The user pastes it in chat. Save it with `link save --app orca` (the link goes in `TUNNEL_LINK`, never on the command line).
- A saved link keeps working while that paired device is still listed in Orca. Paired device ids are in
  `orca-devices.json` in Orca's app data folder: macOS `~/Library/Application Support/orca/`,
  Windows `%APPDATA%\orca\` (not checked yet), Linux `~/.config/orca/` (not checked yet).
  If the user removed the device in Orca, the old link is refused and a fresh one is needed.

## Change log

- 2026-11-11: first version.
