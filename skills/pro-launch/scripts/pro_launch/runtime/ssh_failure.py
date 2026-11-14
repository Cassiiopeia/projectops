"""ssh failure classification: tells connection·auth failures apart from a connected remote command that exited non-zero (#946)."""
from __future__ import annotations

SSH_CONNECTION_ERROR_EXIT = 255  # ssh's own errors (connection failure, auth failure, etc.)

# (text found in stderr, code, next action) — first match from the top wins
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
    """(code, next). Exit code 255 or ssh error text means connection·auth failure; other non-zero exits are remote command results.

    sshpass exits 5 on a wrong password, which clashes with a remote command's 5, so it is told apart by stderr text, not exit code.
    """
    for needle, code, advice in _SSH_STDERR_RULES:
        if needle in stderr_text:
            return code, advice
    if returncode == SSH_CONNECTION_ERROR_EXIT:
        return "connect_failed", "Read stderr and fix the connection details (cred show --name)"
    return "remote_exit_nonzero", ("Connected; the remote command exited with code %d. "
                                  "That can be normal (e.g. grep with no match) — judge by stdout and stderr" % returncode)
