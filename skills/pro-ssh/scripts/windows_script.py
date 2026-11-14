#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Windows 호스트에서 PowerShell·Python 스크립트 실행: 인코딩 > (작으면 한 번 / 크면 나눠 올림) > launch_cli ssh (#1189)
따옴표·cmd 파싱 없음: 원격 명령은 `powershell -EncodedCommand <base64>` 하나 (cmd·PowerShell 기본 셸 공통)

  python windows_script.py run --cred <server> --file check.py
  python windows_script.py run --cred <server> --lang powershell --code 'Get-Service sshd'
  python windows_script.py run --cred <server> --file big.ps1 --dry-run   # 접속 없이 명령만
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

# cmd.exe 명령줄 한도 8191자 (Windows OpenSSH 가 cmd /c 로 실행) > 여유 두고 8000
MAX_REMOTE_COMMAND_CHARS = 8000
# 나눠 올리기 1회분 base64 글자 수 (UTF-16 base64 로 약 2.7배 + 앞뒤 코드 > 8000 안쪽)
UPLOAD_CHUNK_CHARS = 2700
POWERSHELL_LAUNCH = "powershell -NoProfile -NonInteractive -EncodedCommand "
LANGUAGE_BY_SUFFIX = {".ps1": "powershell", ".py": "python"}
# 원격 임시 폴더: %TEMP%\projectops-ssh-{토큰} (실행 후 삭제, 성공·실패 공통)
REMOTE_FOLDER_PREFIX = "projectops-ssh-"
# python 못 찾음 종료 코드 (ssh 가 하위 8비트만 전달 > 9009 는 49 로 보임)
PYTHON_NOT_FOUND_EXIT_CODE = 127

# 진행 표시(CLIXML progress) 끔 — 매 호출 stderr 에 '모듈 준비 중' 이 섞이는 원인
_POWERSHELL_PRELUDE = "$ProgressPreference='SilentlyContinue'\n"

# Python 찾기 순서: --python > PATH(python·python3, Store 스텁 제외) > 설치 폴더 > py 런처
# (py 런처는 ssh 계정에 등록된 Python 이 없으면 'No installed Python found!' 로 실패)
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

# Python 출력 UTF-8 고정 (cp949 콘솔에서 한글·이모지 깨짐 방지)
_PYTHON_ENVIRONMENT = (
    "$u=New-Object System.Text.UTF8Encoding $false; [Console]::OutputEncoding=$u; $OutputEncoding=$u\n"
    "$env:PYTHONIOENCODING='utf-8'; $env:PYTHONUTF8='1'\n"
)

# PowerShell 오류 > 평문 stderr (리다이렉트된 stderr 는 CLIXML 로 나가기 때문)
# 스크립트 오류는 종료 코드 1, 외부 프로그램 stderr 줄은 그대로 옮기기만 함
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
    """임의 문자열 > PowerShell 작은따옴표 리터럴"""
    return "'" + text.replace("'", "''") + "'"


def to_encoded_command(powershell_source: str) -> str:
    """PowerShell 소스 > `powershell -EncodedCommand` 원격 명령 (UTF-16LE base64)"""
    return POWERSHELL_LAUNCH + base64.b64encode(powershell_source.encode("utf-16-le")).decode("ascii")


def to_deflated_base64(text: str) -> str:
    """UTF-8 텍스트 > raw deflate > base64 (.NET DeflateStream 과 같은 형식)"""
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    return base64.b64encode(compressor.compress(text.encode("utf-8")) + compressor.flush()).decode("ascii")


def build_python_locator(python_path: str | None) -> str:
    """$py 정하기 (없으면 127 로 끝냄)"""
    locator = f"$py={quote_powershell_literal(python_path)}\n" if python_path else _FIND_PYTHON
    # 실행 안 되는 경로면 127 로 끝나게 (LASTEXITCODE 비면 exit 0 이 됨)
    locator += "if($py -and -not (Get-Command $py -ErrorAction SilentlyContinue)){ $py=$null }\n"
    return locator + (
        "if(-not $py){ [Console]::Error.WriteLine('[windows script] python not found: pass --python <path to python.exe>'); "
        f"exit {PYTHON_NOT_FOUND_EXIT_CODE} }}\n")


def build_inline_source(language: str, script_text: str, python_path: str | None) -> str:
    """스크립트를 명령 안에 담는 PowerShell 소스 (작은 스크립트)"""
    if language == "python":
        payload = to_deflated_base64(script_text)
        # -c 인자에 큰따옴표·공백 없음 > PowerShell 5.1 의 인자 따옴표 제거 문제를 피함
        python_code = ("import base64,zlib;exec(compile(zlib.decompress(base64.b64decode('"
                       + payload + "'),-15).decode('utf-8'),'<script>','exec'))")
        return (_POWERSHELL_PRELUDE + _PYTHON_ENVIRONMENT + build_python_locator(python_path)
                + f'& $py -c "{python_code}"\nexit $LASTEXITCODE\n')
    block = "{\n" + script_text + "\n}"
    return _POWERSHELL_PRELUDE + _POWERSHELL_RUNNER.replace("__INVOKE__", block) + "exit $rc\n"


def build_remote_folder_expression(token: str) -> str:
    return f"$d=Join-Path $env:TEMP {quote_powershell_literal(REMOTE_FOLDER_PREFIX + token)}\n"


def build_upload_chunk_source(token: str, chunk: str) -> str:
    """base64 조각 1개를 원격 임시 파일에 이어 붙임"""
    return (_POWERSHELL_PRELUDE + build_remote_folder_expression(token)
            + "[void](New-Item -ItemType Directory -Force -Path $d)\n"
            + f"[IO.File]::AppendAllText((Join-Path $d 'payload.b64'),{quote_powershell_literal(chunk)})\n")


def build_upload_run_source(language: str, token: str, python_path: str | None) -> str:
    """올린 조각 > 스크립트 파일 복원 > 실행 > 임시 폴더 삭제 (성공·실패 공통)"""
    # .ps1 은 BOM 있는 UTF-8 이어야 PowerShell 5.1 이 한글을 읽음, .py 는 BOM 없이
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
    """원격 명령 목록: 한 번에 담기면 inline 1개, 아니면 upload (조각 n개 + 실행 1개)"""
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
    """PowerShell CLIXML stderr > 오류 줄만 평문 (잘린 XML 도 처리)"""
    if not stderr_text.lstrip().startswith("#< CLIXML"):
        return stderr_text
    pieces = re.findall(r'<S S="Error">(.*?)</S>', stderr_text, flags=re.DOTALL)
    text = "".join(html.unescape(piece) for piece in pieces)
    return re.sub(r"_x([0-9A-Fa-f]{4})_", lambda match: chr(int(match.group(1), 16)), text).strip()


def find_launch_cli(override: str | None) -> Path | None:
    """pro-launch 의 launch_cli.py (스킬 폴더가 형제로 설치됨)"""
    candidate = Path(override).expanduser() if override else (
        Path(__file__).resolve().parents[2] / "pro-launch" / "scripts" / "launch_cli.py")
    return candidate if candidate.is_file() else None


def run_launch_ssh(launch_cli: Path, connection_arguments: list[str], remote_command: str, timeout_seconds: int) -> dict:
    """launch_cli ssh 1회 > 응답 JSON"""
    environment = dict(os.environ, PYTHONIOENCODING="utf-8")
    completed = subprocess.run(
        [sys.executable, str(launch_cli), "ssh", *connection_arguments, "--timeout", str(timeout_seconds),
         "--command", remote_command],
        capture_output=True, encoding="utf-8", errors="replace", env=environment)
    try:
        return json.loads(completed.stdout)
    except (json.JSONDecodeError, TypeError):
        return {"ok": False, "code": "launch_output_unreadable",
                "error": (completed.stdout or "")[-500:] + (completed.stderr or "")[-500:]}


def read_script(args) -> tuple[str | None, str | None, dict | None]:
    """(스크립트 본문, 언어, 오류 응답)"""
    if bool(args.file) == bool(args.code):
        return None, None, {"ok": False, "code": "bad_args", "error": "Give exactly one of --file or --code"}
    language = args.lang
    if args.file:
        path = Path(args.file).expanduser()
        if not path.is_file():
            return None, None, {"ok": False, "code": "file_not_found", "error": f"No such file: {path}"}
        language = language or LANGUAGE_BY_SUFFIX.get(path.suffix.lower())
        # utf-8-sig: 메모장 BOM 제거
        script_text = path.read_text(encoding="utf-8-sig")
    else:
        script_text = args.code
    if not language:
        return None, None, {"ok": False, "code": "bad_args",
                            "error": "Cannot tell the language: pass --lang powershell|python"}
    return script_text, language, None


def build_connection_arguments(args) -> list[str]:
    """launch_cli ssh 에 그대로 넘길 접속 인자 (비밀번호 값은 받지 않음 — --password-env 만)"""
    pairs = (("--cred", args.cred), ("--host", args.host), ("--port", args.port), ("--user", args.user),
             ("--password-env", args.password_env), ("--key-path", args.key_path))
    return [item for flag, value in pairs if value not in (None, "") for item in (flag, str(value))]


def emit(response: dict) -> int:
    """JSON 출력 (필수 4필드: ok·code·summary·next)"""
    response.setdefault("summary", response.get("error") or response.get("code"))
    response.setdefault("next", None)
    print(json.dumps(response, ensure_ascii=False))
    return 0 if response.get("ok") else 1


def cmd_run(args) -> int:
    """스크립트 1개 실행: 읽기 > 명령 계획 > (dry-run 이면 끝) > 단계별 ssh > 결과 정리"""
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
            # 올리다 실패: 남은 조각 정리 (실패해도 결과에 영향 없음)
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
