"""ssh 실패 분류: 연결·인증이 안 된 것과, 연결은 됐는데 원격 명령이 0 이 아니게 끝난 것을 가른다 (#946)."""
from __future__ import annotations

SSH_CONNECTION_ERROR_EXIT = 255  # ssh 자신의 오류(연결 실패·인증 실패 등)

# (stderr 에 들어 있는 문구, code, 다음 행동) — 위에서부터 먼저 맞는 것
_SSH_STDERR_RULES = (
    ("REMOTE HOST IDENTIFICATION HAS CHANGED", "host_key_changed",
     "서버가 바뀌었을 수 있다. 사용자에게 알리고 known_hosts 를 임의로 지우지 않는다"),
    ("Permission denied", "auth_failed",
     "계정·비밀번호·키가 맞는지 다시 시도하지 말고 사용자에게 값이 바뀌었는지 묻는다"),
    ("Host key verification failed", "host_key_unknown",
     "처음 보는 서버다. 사용자에게 지문을 확인받는다"),
    ("Connection refused", "connect_failed", "포트·방화벽·sshd 상태를 본다"),
    ("timed out", "connect_failed", "호스트 주소·포트·네트워크(VPN)를 본다"),
    ("Could not resolve hostname", "connect_failed", "호스트 이름 철자를 본다"),
    ("No route to host", "connect_failed", "호스트 주소·네트워크를 본다"),
)


def classify_ssh_failure(returncode: int, stderr_text: str) -> tuple[str, str]:
    """(code, next). 종료코드 255 이거나 ssh 오류 문구가 있으면 연결·인증 실패, 그 외 비정상 종료는 원격 명령 결과.

    sshpass 는 비밀번호 오류를 5 로 끝내는데 원격 명령의 5 와 겹치므로 종료코드가 아니라 stderr 문구로 가른다.
    """
    for needle, code, advice in _SSH_STDERR_RULES:
        if needle in stderr_text:
            return code, advice
    if returncode == SSH_CONNECTION_ERROR_EXIT:
        return "connect_failed", "stderr 를 보고 접속 정보를 고친다 (cred show --name)"
    return "remote_exit_nonzero", ("연결은 성공했고 원격 명령이 종료코드 %d 로 끝났다. "
                                  "grep 결과 없음처럼 정상일 수 있으니 stdout·stderr 로 판단한다" % returncode)
