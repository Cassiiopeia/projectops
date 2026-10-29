"""비밀번호 ssh 전달: sshpass 있으면 sshpass -e, 없으면 OpenSSH SSH_ASKPASS (#987)
비밀번호는 환경변수로만 전달 > 명령줄·파일·로그에 남지 않음
"""
from __future__ import annotations

import contextlib
import os
import shutil
import stat
import sys
import tempfile
from typing import Iterator

# askpass 스크립트가 읽는 환경변수 (비밀번호 값은 파일에 쓰지 않음)
ASKPASS_PASSWORD_ENV = "PROJECTOPS_SSH_ASKPASS_PASSWORD"
# 틀린 비밀번호 반복 시도로 계정 잠김 방지 > 시도 1회
SINGLE_PASSWORD_PROMPT_OPTIONS = ["-o", "NumberOfPasswordPrompts=1"]

_POSIX_ASKPASS_SCRIPT = '#!/bin/sh\nprintf \'%s\\n\' "$' + ASKPASS_PASSWORD_ENV + '"\n'


def _windows_askpass_script() -> str:
    """Windows .cmd: 비밀번호를 cmd 파싱에 넣지 않게 파이썬이 환경변수를 출력"""
    return ('@"%s" -I -c "import os,sys;sys.stdout.write(os.environ.get(\'%s\',\'\')+chr(10))"\r\n'
            % (sys.executable, ASKPASS_PASSWORD_ENV))


def _write_askpass_script(directory: str) -> str:
    """0700 임시 폴더에 askpass 스크립트 생성 > 경로"""
    is_windows = os.name == "nt"
    script_path = os.path.join(directory, "askpass.cmd" if is_windows else "askpass.sh")
    with open(script_path, "w", encoding="utf-8", newline="") as handle:
        handle.write(_windows_askpass_script() if is_windows else _POSIX_ASKPASS_SCRIPT)
    os.chmod(script_path, stat.S_IRWXU)
    return script_path


@contextlib.contextmanager
def password_transport(password: str, env: dict) -> Iterator[tuple[list[str], dict]]:
    """(ssh 앞에 붙일 argv, subprocess 추가 인자). env 는 제자리 갱신, 끝나면 askpass 파일 삭제 (성공·실패 공통)"""
    env_password_key = "SSHPASS" if shutil.which("sshpass") else ASKPASS_PASSWORD_ENV
    env[env_password_key] = str(password)
    if env_password_key == "SSHPASS":
        yield ["sshpass", "-e"], {}
        return
    askpass_directory = tempfile.mkdtemp(prefix="projectops-askpass-")   # mkdtemp 는 0700
    try:
        env["SSH_ASKPASS"] = _write_askpass_script(askpass_directory)
        env["SSH_ASKPASS_REQUIRE"] = "force"                 # OpenSSH 8.4+: 터미널 있어도 askpass 사용
        env.setdefault("DISPLAY", "projectops:0")             # 8.4 미만: DISPLAY 있어야 askpass 사용
        # 8.4 미만: 제어 터미널 있으면 tty 로 물음 > 새 세션으로 분리 (POSIX 만)
        popen_options = {} if os.name == "nt" else {"start_new_session": True}
        yield [], popen_options
    finally:
        shutil.rmtree(askpass_directory, ignore_errors=True)
