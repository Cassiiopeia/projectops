"""ssh 실패 분류: 연결·인증이 안 된 것과, 연결은 됐는데 원격 명령이 0 이 아니게 끝난 것을 가른다 (#946)."""
from __future__ import annotations

SSH_CONNECTION_ERROR_EXIT = 255  # ssh 자신의 오류(연결 실패·인증 실패 등)

# (stderr 에 들어 있는 문구, code, 다음 행동) — 위에서부터 먼저 맞는 것
_SSH_STDERR_RULES = (
    ("REMOTE HOST IDENTIFICATION HAS CHANGED", "host_key_changed",
     "The server may have changed. Tell the user; do not delete known_hosts on your own"),
    ("Permission denied", "auth_failed",
     "Do not retry guessing the account, password or key — ask the user whether they changed"),
    ("Host key verification failed", "host_key_unknown",
     "Unknown server. Have the user confirm the fingerprint"),
    ("Connection refused", "connect_failed", "Check the port, firewall and sshd status"),
    ("timed out", "connect_failed", "Check the host address, port and network (VPN)"),
    ("Could not resolve hostname", "connect_failed", "Check the host name spelling"),
    ("No route to host", "connect_failed", "Check the host address and network"),
)


def classify_ssh_failure(returncode: int, stderr_text: str) -> tuple[str, str]:
    """(code, next). 종료코드 255 이거나 ssh 오류 문구가 있으면 연결·인증 실패, 그 외 비정상 종료는 원격 명령 결과.

    sshpass 는 비밀번호 오류를 5 로 끝내는데 원격 명령의 5 와 겹치므로 종료코드가 아니라 stderr 문구로 가른다.
    """
    for needle, code, advice in _SSH_STDERR_RULES:
        if needle in stderr_text:
            return code, advice
    if returncode == SSH_CONNECTION_ERROR_EXIT:
        return "connect_failed", "Read stderr and fix the connection details (cred show --name)"
    return "remote_exit_nonzero", ("Connected; the remote command exited with code %d. "
                                  "That can be normal (e.g. grep with no match) — judge by stdout and stderr" % returncode)
