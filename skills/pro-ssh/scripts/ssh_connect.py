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
# paramiko import (없으면 설치 안내 후 종료)
# ──────────────────────────────────────────────
try:
    import paramiko
except ImportError:
    print("[ERROR] paramiko 모듈이 없습니다.")
    print("설치 명령: pip install paramiko   (또는 pip3 install paramiko)")
    sys.exit(1)

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
        print("[ERROR] PEM 키 파일을 찾을 수 없습니다: " + key_path)
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
        description="paramiko 기반 SSH 명령 실행기 (크로스플랫폼)",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--host", required=True, help="SSH 호스트명 또는 IP")
    parser.add_argument("--port", type=int, default=22, help="SSH 포트 (기본: 22)")
    parser.add_argument("--user", required=True, help="SSH 사용자명")
    parser.add_argument(
        "--auth",
        required=True,
        choices=["password", "key"],
        help="인증 방식: password 또는 key",
    )
    parser.add_argument("--password", default=None,
                        help="SSH 비밀번호 (권장하지 않음 — argv 로 보인다. 환경변수 SSH_PASSWORD 를 쓴다)")
    parser.add_argument("--key-path", default=None, help="PEM 키 경로 (auth=key 시 필수)")
    parser.add_argument("--command", required=True, help="원격에서 실행할 명령")
    parser.add_argument(
        "--timeout", type=int, default=15, help="접속 타임아웃 (초, 기본: 15)"
    )

    args = parser.parse_args()
    # 비밀번호는 환경변수가 우선 — argv 에 남기지 않는 경로
    if args.password is None:
        args.password = os.environ.get("SSH_PASSWORD") or None
    print("[안내] ssh_connect.py 는 호환용이다. launch_cli.py ssh --cred <서버> 를 쓴다.", file=sys.stderr)

    # ── 인자 검증 ──────────────────────────────────
    if args.auth == "password" and not args.password:
        print("[ERROR] --auth password 사용 시 --password 가 필요합니다.")
        sys.exit(1)
    if args.auth == "key" and not args.key_path:
        print("[ERROR] --auth key 사용 시 --key-path 가 필요합니다.")
        sys.exit(1)

    # ── 접속 ───────────────────────────────────────
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
        print("[ERROR] 인증 실패: 사용자명/비밀번호/키를 확인하세요.")
        sys.exit(1)
    except paramiko.SSHException as e:
        print("[ERROR] SSH 프로토콜 오류: " + str(e))
        sys.exit(1)
    except socket.timeout:
        print("[ERROR] 접속 타임아웃 ({0}초): 호스트/포트를 확인하세요.".format(args.timeout))
        sys.exit(1)
    except socket.error as e:
        print("[ERROR] 소켓 오류 (포트/방화벽 확인): " + str(e))
        sys.exit(1)
    except Exception as e:
        print("[ERROR] 예상치 못한 접속 오류: " + str(e))
        traceback.print_exc()
        sys.exit(1)

    # ── 명령 실행 ──────────────────────────────────
    try:
        out, err, exit_code = run_command(client, args.command)
    except Exception as e:
        print("[ERROR] 명령 실행 중 오류: " + str(e))
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
