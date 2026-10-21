#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ssh_connect.py — paramiko 기반 범용 SSH 접속 스크립트  [사용 중단 예정 — 호환용]

정본은 `pro-launch` 의 `launch_cli.py ssh --cred <서버> --command '…'` 다 (#841).
그쪽은 서버 이름으로 접속하고, 비밀번호를 명령줄에 싣지 않으며, 출력의 비밀을 가리고,
서버별 기억(OS · docker 경로)을 응답에 싣는다. 이 스크립트는 launch 를 쓸 수 없는 환경
(sshpass 가 없는 Windows 등)을 위한 대체 경로로만 남긴다.

  - 비밀번호는 `--password` 대신 환경변수 SSH_PASSWORD 로 받는 것을 권장한다 (argv 는 ps 로 보인다).
  - 출력에 비밀번호가 섞이면 `***` 로 가린다.

지원:
  - 비밀번호 인증 (auth=password)
  - PEM 키 인증 (auth=key, AWS EC2 등)
  - macOS / Linux / Windows (PowerShell 5.x 포함) 크로스플랫폼

사용법:
  python ssh_connect.py --host HOST --port PORT --user USER
                        --auth password --password PASS
                        --command "CMD"

  python ssh_connect.py --host HOST --port PORT --user USER
                        --auth key --key-path ~/.ssh/my-key.pem
                        --command "CMD"
"""

from __future__ import print_function  # Python 2 하위 호환 (만약을 위해)

import sys
import os
import argparse

# ──────────────────────────────────────────────
# paramiko 는 실제 접속 직전에 불러온다 (--help·인자 오류는 paramiko 없이도 동작)
# ──────────────────────────────────────────────
paramiko = None


def _require_paramiko():
    """paramiko 를 지연 import 한다. 없으면 설치 안내 후 종료."""
    global paramiko
    try:
        import paramiko as _paramiko
    except ImportError:
        print("[ERROR] The paramiko module is missing.")
        print("Install: pip install paramiko   (or pip3 install paramiko)")
        sys.exit(1)
    paramiko = _paramiko


import socket
import traceback


def _expand_path(path):
    """~ 및 환경변수를 포함한 경로를 절대 경로로 변환한다."""
    if path is None:
        return None
    return os.path.expandvars(os.path.expanduser(path))


def _connect_password(host, port, user, password, timeout=15):
    """비밀번호 인증으로 SSH 클라이언트를 연결하고 반환한다."""
    client = paramiko.SSHClient()
    # 처음 접속하는 호스트의 키를 자동 수락 (StrictHostKeyChecking=no 동일 효과)
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        port=port,
        username=user,
        password=password,
        timeout=timeout,
        look_for_keys=False,   # 키 파일 자동 탐색 비활성화
        allow_agent=False,     # SSH 에이전트 비활성화 (비밀번호 전용 보장)
    )
    return client


def _connect_key(host, port, user, key_path, timeout=15):
    """PEM 키 인증으로 SSH 클라이언트를 연결하고 반환한다."""
    key_path = _expand_path(key_path)
    if not os.path.isfile(key_path):
        print("[ERROR] PEM key file not found: " + key_path)
        sys.exit(1)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        port=port,
        username=user,
        key_filename=key_path,
        timeout=timeout,
        look_for_keys=False,
        allow_agent=False,
    )
    return client


def run_command(client, command):
    """
    SSH 채널로 명령을 실행하고 stdout/stderr/exit_code를 반환한다.
    타임아웃 없이 명령 완료까지 대기한다 (get_pty=True로 sudo 대화형 대체).
    """
    # get_pty=True: sudo 등 터미널 필요한 명령 지원
    stdin, stdout, stderr = client.exec_command(command, get_pty=False)
    exit_code = stdout.channel.recv_exit_status()

    # 바이트 스트림을 UTF-8로 디코딩 (오류 문자는 replace 처리)
    out = stdout.read().decode("utf-8", errors="replace").rstrip()
    err = stderr.read().decode("utf-8", errors="replace").rstrip()
    return out, err, exit_code


def main():
    parser = argparse.ArgumentParser(
        description="paramiko-based SSH command runner (cross-platform)",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--host", required=True, help="SSH host name or IP")
    parser.add_argument("--port", type=int, default=22, help="SSH port (default: 22)")
    parser.add_argument("--user", required=True, help="SSH user name")
    parser.add_argument(
        "--auth",
        required=True,
        choices=["password", "key"],
        help="Auth method: password or key",
    )
    parser.add_argument("--password", default=None,
                        help="SSH password (not recommended — visible in argv; use the SSH_PASSWORD env var)")
    parser.add_argument("--key-path", default=None, help="PEM key path (required with auth=key)")
    parser.add_argument("--command", required=True, help="Command to run on the remote host")
    parser.add_argument(
        "--timeout", type=int, default=15, help="Connect timeout (seconds, default: 15)"
    )

    args = parser.parse_args()
    # 비밀번호는 환경변수가 우선 — argv 에 남기지 않는 경로
    if args.password is None:
        args.password = os.environ.get("SSH_PASSWORD") or None
    print("[NOTICE] ssh_connect.py is kept for compatibility. Use launch_cli.py ssh --cred <server>.", file=sys.stderr)

    # ── 인자 검증 ──────────────────────────────────
    if args.auth == "password" and not args.password:
        print("[ERROR] --auth password requires --password.")
        sys.exit(1)
    if args.auth == "key" and not args.key_path:
        print("[ERROR] --auth key requires --key-path.")
        sys.exit(1)

    # ── 접속 ───────────────────────────────────────
    _require_paramiko()
    client = None
    try:
        if args.auth == "password":
            client = _connect_password(
                args.host, args.port, args.user, args.password, args.timeout
            )
        else:
            client = _connect_key(
                args.host, args.port, args.user, args.key_path, args.timeout
            )
    except paramiko.AuthenticationException:
        print("[ERROR] Authentication failed: check the user name, password or key.")
        sys.exit(1)
    except paramiko.SSHException as e:
        print("[ERROR] SSH protocol error: " + str(e))
        sys.exit(1)
    except socket.timeout:
        print("[ERROR] Connect timeout ({0}s): check the host and port.".format(args.timeout))
        sys.exit(1)
    except socket.error as e:
        print("[ERROR] Socket error (check the port and firewall): " + str(e))
        sys.exit(1)
    except Exception as e:
        print("[ERROR] Unexpected connection error: " + str(e))
        traceback.print_exc()
        sys.exit(1)

    # ── 명령 실행 ──────────────────────────────────
    try:
        out, err, exit_code = run_command(client, args.command)
    except Exception as e:
        print("[ERROR] Error while running the command: " + str(e))
        traceback.print_exc()
        sys.exit(1)
    finally:
        client.close()

    # ── 결과 출력 ──────────────────────────────────
    # 서버가 환경변수 등을 되풀이해 찍으면 비밀번호가 화면에 남는다 — 가린다
    if args.password and len(args.password) >= 4:
        out = out.replace(args.password, "***")
        err = err.replace(args.password, "***")
    if out:
        print(out)
    if err:
        # stderr는 구분을 위해 접두어 표시
        for line in err.splitlines():
            print("[STDERR] " + line)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
