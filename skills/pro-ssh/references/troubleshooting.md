# Synology specifics · Windows hosts · Windows PowerShell · common pitfalls

> When to read: when the target is a Synology NAS or a Windows host, when running from Windows PowerShell, or when `launch_cli ssh` or the compatibility `ssh_connect.py` fails.
> On the first connection, `launch_cli ssh` checks the Synology docker path and records it as the `server.<server>.docker` memory.

## Synology NAS specifics

A Synology NAS differs from a regular Linux server.

| Item | Regular server | Synology NAS |
|------|-----------|--------------|
| Docker path | `docker` | `/var/packages/ContainerManager/target/usr/bin/docker` |
| curl inside containers | Usually present | Often missing → use `wget` instead |
| sudo | Usually works | Limited in non-interactive SSH |
| Default SSH port | 22 | Custom ports are common (e.g. 2022) |

**HTTP check on Synology (wget instead of curl):**
```bash
wget -q -O - --server-response http://localhost:{port}/{path} 2>&1 | head -5
```

## Windows PowerShell (including 5.x): find Python

```powershell
# Fall back from python3 to python (PowerShell 5.x has no ?.Source, so use if branches)
$py3 = Get-Command python3 -ErrorAction SilentlyContinue
if ($py3) { $PYTHON = $py3.Source }
else {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) { $PYTHON = $py.Source }
    else { Write-Error "[ERROR] Python is not installed."; exit 1 }
}

# Check that paramiko is installed
& $PYTHON -c "import paramiko" 2>$null
if ($LASTEXITCODE -ne 0) { & $PYTHON -m pip install paramiko }
```

## Windows host: scripts, quoting and output (#1189)

Run scripts with `windows_script.py run` (SKILL.md, Phase 1) instead of building `powershell -Command "…"` by hand.

| Symptom | Cause | Fix |
|------|------|------|
| `SyntaxError` from `python -c "…'…'…"` | cmd and PowerShell 5.1 strip the quotes inside the argument | `windows_script.py run --file x.py` (sent as `-EncodedCommand`, no quotes reach cmd) |
| `#< CLIXML …` (a "preparing modules for first use" progress record) in stderr | PowerShell writes progress and errors as CLIXML when stderr is redirected | `windows_script.py` turns progress off and prints errors as plain text |
| `No installed Python found!` | The `py` launcher has no Python registered for the ssh account | Let `windows_script.py` find `python.exe`, or pass `--python <path>` |
| Exit code 49 instead of 9009 | ssh passes only the low 8 bits of a Windows exit code | Compare with `exit_code % 256` |
| Korean text garbled from a PowerShell script that calls a native tool | Native tools print in the console code page (cp949) | Leave the console encoding alone in PowerShell scripts; `launch_cli` decodes cp949 |

## Common pitfalls

The symptom column shows the literal message `ssh_connect.py` prints.

| Symptom | Cause | Fix |
|------|------|------|
| `[ERROR] The paramiko module is missing.` | paramiko not installed | `pip install paramiko` or `pip3 install paramiko` |
| `[ERROR] Python is not installed.` | Python not installed | Install from python.org (on Windows, adding it to PATH is required) |
| `sshpass_missing` (launch_cli) | Plugin older than #987 (needed sshpass for password auth) | Update the plugin (OpenSSH `SSH_ASKPASS` path), key auth, or `ssh_connect.py` |
| `[ERROR] Authentication failed` | Wrong password or key | Check the `password` / `key_path` values in the config |
| `[ERROR] Socket error` | Wrong port or firewall | Check the config `port` and the server firewall rules |
| `[ERROR] PEM key file not found` | Wrong key_path | Enter an absolute path, `~` allowed (e.g. `~/.ssh/my-key.pem`) |
| `command not found` | Binary not on PATH | Run it by absolute path (find it first with `which`) |
| `sudo: a terminal is required` | sudo not possible in non-interactive SSH | Use the `echo '{password}' \| sudo -S {command}` pattern |
| `WARNING: UNPROTECTED PRIVATE KEY FILE` | PEM key permission problem | Run `chmod 400 {key_path}` and retry |
| `?` symbol error on Windows (`?.Source`) | PowerShell 5.x has no null-conditional operator | Use the `if ($x) { $x.Source }` pattern instead |
