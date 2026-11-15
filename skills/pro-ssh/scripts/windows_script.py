#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Run PowerShell·Python scripts on a Windows host: encode > (small: one call / large: upload in chunks) > launch_cli ssh (#1189)
No quoting or cmd parsing: the remote command is a single `powershell -EncodedCommand <base64>` (works with cmd or PowerShell as default shell)

  python windows_script.py run --cred <server> --file check.py
  python windows_script.py run --cred <server> --lang powershell --code 'Get-Service sshd'
  python windows_script.py run --cred <server> --file big.ps1 --dry-run   # print commands only, no connection
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import secrets
import subprocess
import sys
import zlib
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="replace")

# cmd.exe command line limit is 8191 chars (Windows OpenSSH runs via cmd /c) > 8000 with headroom
MAX_REMOTE_COMMAND_CHARS = 8000
# base64 chars per upload chunk (about 2.7x as UTF-16 base64 + wrapper code > stays under 8000)
UPLOAD_CHUNK_CHARS = 2700
POWERSHELL_LAUNCH = "powershell -NoProfile -NonInteractive -EncodedCommand "
LANGUAGE_BY_SUFFIX = {".ps1": "powershell", ".py": "python"}
# Remote temp folder: %TEMP%\projectops-ssh-{token} (deleted after running, on success or failure)
REMOTE_FOLDER_PREFIX = "projectops-ssh-"
# Exit code when python is not found (ssh passes only the low 8 bits > 9009 shows up as 49)
PYTHON_NOT_FOUND_EXIT_CODE = 127

# Turn off progress output (CLIXML progress) — the reason a 'preparing modules' line lands in stderr on every call
_POWERSHELL_PRELUDE = "$ProgressPreference='SilentlyContinue'\n"

# Python lookup order: --python > PATH (python·python3, excluding the Store stub) > install folders > py launcher
# (the py launcher fails with 'No installed Python found!' when the ssh account has no registered Python)
_FIND_PYTHON = r"""
$py=$null
foreach($n in 'python','python3'){
  $c=Get-Command $n -CommandType Application -ErrorAction SilentlyContinue | Where-Object { $_.Source -notlike '*\WindowsApps\*' } | Select-Object -First 1
  if($c){ $py=$c.Source; break }
}
if(-not $py){
  $c=Get-ChildItem 'C:\Users\*\AppData\Local\Programs\Python\Python3*\python.exe','C:\Program Files\Python3*\python.exe','C:\Python3*\python.exe' -ErrorAction SilentlyContinue | Sort-Object { [int]($_.Directory.Name -replace '\D','') } -Descending | Select-Object -First 1
  if($c){ $py=$c.FullName }
}
if(-not $py){ $c=Get-Command py -CommandType Application -ErrorAction SilentlyContinue; if($c){ $py=$c.Source } }
"""

# Pin Python output to UTF-8 (avoids garbled Korean and emoji on a cp949 console)
_PYTHON_ENVIRONMENT = (
    "$u=New-Object System.Text.UTF8Encoding $false; [Console]::OutputEncoding=$u; $OutputEncoding=$u\n"
    "$env:PYTHONIOENCODING='utf-8'; $env:PYTHONUTF8='1'\n"
)

# PowerShell errors > plain-text stderr (redirected stderr goes out as CLIXML)
# Script errors exit with code 1; stderr lines from external programs are only passed through
_POWERSHELL_RUNNER = r"""
$rc=0
try {
  $global:LASTEXITCODE=0
  & __INVOKE__ 2>&1 3>&1 | ForEach-Object {
    if ($_ -is [System.Management.Automation.ErrorRecord]) {
      if ($_.Exception -is [System.Management.Automation.RemoteException]) { [Console]::Error.WriteLine($_.Exception.Message) }
      else { $rc=1; [Console]::Error.WriteLine(($_ | Out-String).TrimEnd()) }
    } elseif ($_ -is [System.Management.Automation.WarningRecord]) { [Console]::Error.WriteLine('WARNING: ' + $_.Message) }
    else { $_ }
  }
  if ($LASTEXITCODE) { $rc=$LASTEXITCODE }
} catch { $rc=1; [Console]::Error.WriteLine(($_ | Out-String).TrimEnd()) }
"""


def quote_powershell_literal(text: str) -> str:
    """Any string > PowerShell single-quoted literal"""
    return "'" + text.replace("'", "''") + "'"


def to_encoded_command(powershell_source: str) -> str:
    """PowerShell source > `powershell -EncodedCommand` remote command (UTF-16LE base64)"""
    return POWERSHELL_LAUNCH + base64.b64encode(powershell_source.encode("utf-16-le")).decode("ascii")


def to_deflated_base64(text: str) -> str:
    """UTF-8 text > raw deflate > base64 (same format as .NET DeflateStream)"""
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    return base64.b64encode(compressor.compress(text.encode("utf-8")) + compressor.flush()).decode("ascii")


def build_python_locator(python_path: str | None) -> str:
    """Set $py (ends with 127 if none)"""
    locator = f"$py={quote_powershell_literal(python_path)}\n" if python_path else _FIND_PYTHON
    # End with 127 if the path does not run (with an empty LASTEXITCODE it would become exit 0)
    locator += "if($py -and -not (Get-Command $py -ErrorAction SilentlyContinue)){ $py=$null }\n"
    return locator + (
        "if(-not $py){ [Console]::Error.WriteLine('[windows script] python not found: pass --python <path to python.exe>'); "
        f"exit {PYTHON_NOT_FOUND_EXIT_CODE} }}\n")


def build_inline_source(language: str, script_text: str, python_path: str | None) -> str:
    """PowerShell source that embeds the script in the command (small scripts)"""
    if language == "python":
        payload = to_deflated_base64(script_text)
        # No double quotes or spaces in the -c argument > avoids PowerShell 5.1's argument quote stripping
        python_code = ("import base64,zlib;exec(compile(zlib.decompress(base64.b64decode('"
                       + payload + "'),-15).decode('utf-8'),'<script>','exec'))")
        return (_POWERSHELL_PRELUDE + _PYTHON_ENVIRONMENT + build_python_locator(python_path)
                + f'& $py -c "{python_code}"\nexit $LASTEXITCODE\n')
    block = "{\n" + script_text + "\n}"
    return _POWERSHELL_PRELUDE + _POWERSHELL_RUNNER.replace("__INVOKE__", block) + "exit $rc\n"


def build_remote_folder_expression(token: str) -> str:
    return f"$d=Join-Path $env:TEMP {quote_powershell_literal(REMOTE_FOLDER_PREFIX + token)}\n"


def build_upload_chunk_source(token: str, chunk: str) -> str:
    """Append one base64 chunk to the remote temp file"""
    return (_POWERSHELL_PRELUDE + build_remote_folder_expression(token)
            + "[void](New-Item -ItemType Directory -Force -Path $d)\n"
            + f"[IO.File]::AppendAllText((Join-Path $d 'payload.b64'),{quote_powershell_literal(chunk)})\n")


def build_upload_run_source(language: str, token: str, python_path: str | None) -> str:
    """Uploaded chunks > restore the script file > run > delete the temp folder (on success or failure)"""
    # .ps1 must be UTF-8 with BOM for PowerShell 5.1 to read Korean; .py goes without BOM
    file_name, has_bom = ("script.py", "$false") if language == "python" else ("script.ps1", "$true")
    if language == "python":
        run = _PYTHON_ENVIRONMENT + build_python_locator(python_path) + "  & $py $f\n  $rc=$LASTEXITCODE\n"
    else:
        run = _POWERSHELL_RUNNER.replace("__INVOKE__", "$f")
    return (_POWERSHELL_PRELUDE + build_remote_folder_expression(token) + "$rc=1\ntry {\n"
            "  $b=[IO.File]::ReadAllText((Join-Path $d 'payload.b64'))\n"
            "  $m=New-Object IO.MemoryStream(,[Convert]::FromBase64String($b))\n"
            "  $z=New-Object IO.Compression.DeflateStream($m,[IO.Compression.CompressionMode]::Decompress)\n"
            "  $t=(New-Object IO.StreamReader($z,[Text.Encoding]::UTF8)).ReadToEnd(); $z.Dispose()\n"
            f"  $f=Join-Path $d '{file_name}'\n"
            f"  [IO.File]::WriteAllText($f,$t,(New-Object Text.UTF8Encoding {has_bom}))\n"
            + run + "} finally { Remove-Item -LiteralPath $d -Recurse -Force -ErrorAction SilentlyContinue }\n"
            "exit $rc\n")


def build_cleanup_source(token: str) -> str:
    return (_POWERSHELL_PRELUDE + build_remote_folder_expression(token)
            + "Remove-Item -LiteralPath $d -Recurse -Force -ErrorAction SilentlyContinue\n")


def plan_remote_commands(language: str, script_text: str, python_path: str | None,
                         should_force_upload: bool) -> dict:
    """Remote command list: one inline command if it fits, otherwise upload (n chunks + 1 run)"""
    inline_command = to_encoded_command(build_inline_source(language, script_text, python_path))
    if len(inline_command) <= MAX_REMOTE_COMMAND_CHARS and not should_force_upload:
        return {"mode": "inline", "commands": [inline_command], "token": None}
    token = secrets.token_hex(4)
    payload = to_deflated_base64(script_text)
    chunks = [payload[start:start + UPLOAD_CHUNK_CHARS] for start in range(0, len(payload), UPLOAD_CHUNK_CHARS)]
    commands = [to_encoded_command(build_upload_chunk_source(token, chunk)) for chunk in chunks]
    commands.append(to_encoded_command(build_upload_run_source(language, token, python_path)))
    return {"mode": "upload", "commands": commands, "token": token}


def strip_clixml(stderr_text: str) -> str:
    """PowerShell CLIXML stderr > only the error lines as plain text (also handles truncated XML)"""
    if not stderr_text.lstrip().startswith("#< CLIXML"):
        return stderr_text
    pieces = re.findall(r'<S S="Error">(.*?)</S>', stderr_text, flags=re.DOTALL)
    text = "".join(html.unescape(piece) for piece in pieces)
    return re.sub(r"_x([0-9A-Fa-f]{4})_", lambda match: chr(int(match.group(1), 16)), text).strip()


def find_launch_cli(override: str | None) -> Path | None:
    """pro-launch's launch_cli.py (the skill folder is installed as a sibling)"""
    candidate = Path(override).expanduser() if override else (
        Path(__file__).resolve().parents[2] / "pro-launch" / "scripts" / "launch_cli.py")
    return candidate if candidate.is_file() else None


def run_launch_ssh(launch_cli: Path, connection_arguments: list[str], remote_command: str, timeout_seconds: int) -> dict:
    """One launch_cli ssh call > response JSON"""
    environment = dict(os.environ, PYTHONIOENCODING="utf-8")
    completed = subprocess.run(
        [sys.executable, str(launch_cli), "ssh", *connection_arguments, "--timeout", str(timeout_seconds),
         "--command", remote_command],
        capture_output=True, encoding="utf-8", errors="replace", env=environment)
    try:
        return json.loads(completed.stdout)
    except (json.JSONDecodeError, TypeError):
        return {"ok": False, "code": "launch_output_unreadable",
                "error": (completed.stdout or "")[-500:] + (completed.stderr or "")[-500:],
                "next": "launch ssh did not return JSON. Read error, then run launch ssh with the same connection to see it directly"}


def read_script(args) -> tuple[str | None, str | None, dict | None]:
    """(script body, language, error response)"""
    if bool(args.file) == bool(args.code):
        return None, None, {"ok": False, "code": "bad_args", "error": "Give exactly one of --file or --code"}
    language = args.lang
    if args.file:
        path = Path(args.file).expanduser()
        if not path.is_file():
            return None, None, {"ok": False, "code": "file_not_found", "error": f"No such file: {path}"}
        language = language or LANGUAGE_BY_SUFFIX.get(path.suffix.lower())
        # utf-8-sig: strips a Notepad BOM
        script_text = path.read_text(encoding="utf-8-sig")
    else:
        script_text = args.code
    if not language:
        return None, None, {"ok": False, "code": "bad_args",
                            "error": "Cannot tell the language: pass --lang powershell|python"}
    return script_text, language, None


def build_connection_arguments(args) -> list[str]:
    """Connection arguments passed straight to launch_cli ssh (no password value accepted — only --password-env)"""
    pairs = (("--cred", args.cred), ("--host", args.host), ("--port", args.port), ("--user", args.user),
             ("--password-env", args.password_env), ("--key-path", args.key_path))
    return [item for flag, value in pairs if value not in (None, "") for item in (flag, str(value))]


def emit(response: dict) -> int:
    """JSON output (4 required fields: ok·code·summary·next)"""
    response.setdefault("summary", response.get("error") or response.get("code"))
    response.setdefault("next", None)
    print(json.dumps(response, ensure_ascii=False))
    return 0 if response.get("ok") else 1


def cmd_run(args) -> int:
    """Run one script: read > plan commands > (stop here on dry-run) > ssh per step > tidy up the result"""
    script_text, language, error = read_script(args)
    if error:
        return emit(error)
    plan = plan_remote_commands(language, script_text, args.python, args.upload)
    summary_base = f"{language} script, {plan['mode']} ({len(plan['commands'])} ssh call(s))"
    if args.dry_run:
        return emit({"ok": True, "code": "dry_run", "language": language, "mode": plan["mode"],
                     "commands": plan["commands"], "summary": summary_base + ", not run", "next": None})
    connection_arguments = build_connection_arguments(args)
    if not connection_arguments:
        return emit({"ok": False, "code": "cred_required", "error": "Give --cred <server> or --host/--user …",
                     "next": "launch_cli.py cred list"})
    launch_cli = find_launch_cli(args.launch_cli)
    if not launch_cli:
        return emit({"ok": False, "code": "launch_cli_not_found",
                     "error": "pro-launch scripts/launch_cli.py not found next to pro-ssh",
                     "next": "pass --launch-cli <path to pro-launch/scripts/launch_cli.py>"})
    response: dict = {}
    for step_index, remote_command in enumerate(plan["commands"], start=1):
        response = run_launch_ssh(launch_cli, connection_arguments, remote_command, args.timeout)
        is_last_step = step_index == len(plan["commands"])
        if not response.get("ok") and not is_last_step:
            # Upload failed: clean up leftover chunks (failure here does not affect the result)
            run_launch_ssh(launch_cli, connection_arguments, to_encoded_command(build_cleanup_source(plan["token"])),
                           args.timeout)
            response.update(failed_step=f"upload {step_index}/{len(plan['commands']) - 1}")
            break
    response["stderr"] = strip_clixml(response.get("stderr") or "")
    if response.get("exit_code") == PYTHON_NOT_FOUND_EXIT_CODE and language == "python":
        response.update(code="python_not_found", next="Find python.exe on the host, then rerun with --python <path>")
    response.update(language=language, mode=plan["mode"], steps=len(plan["commands"]))
    response["summary"] = summary_base + ": " + str(response.get("summary") or response.get("code"))
    return emit(response)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a PowerShell or Python script on a Windows host over ssh "
                                                 "without hand-quoting (cmd or PowerShell default shell)")
    sub = parser.add_subparsers(dest="subcommand", required=True)
    run = sub.add_parser("run", help="Encode and run one script; prints launch_cli ssh JSON plus mode/steps")
    run.add_argument("--file", default=None, help="Local script file (.ps1 or .py)")
    run.add_argument("--code", default=None, help="Script text instead of --file (needs --lang)")
    run.add_argument("--lang", choices=("powershell", "python"), default=None, help="Default: from the file suffix")
    run.add_argument("--python", default=None, help="python.exe path on the host (default: auto-detect)")
    run.add_argument("--upload", action="store_true", help="Always upload to a temp file first (default: only when too long)")
    run.add_argument("--dry-run", dest="dry_run", action="store_true", help="Print the remote commands, do not connect")
    run.add_argument("--cred", default=None, help="Saved server name (launch_cli cred list)")
    run.add_argument("--host", default=None)
    run.add_argument("--port", type=int, default=None)
    run.add_argument("--user", default=None)
    run.add_argument("--password-env", dest="password_env", default=None, help="Env var holding the password")
    run.add_argument("--key-path", dest="key_path", default=None)
    run.add_argument("--timeout", type=int, default=120, help="Seconds per ssh call")
    run.add_argument("--launch-cli", dest="launch_cli", default=None, help="Path to pro-launch launch_cli.py")
    run.set_defaults(handler=cmd_run)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
