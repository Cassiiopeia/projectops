#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ssh_connect.py — general SSH script built on paramiko  [to be deprecated — kept for compatibility]

The canonical path is `pro-launch`'s `launch_cli.py ssh --cred <server> --command '…'` (#841).
It connects by server name, keeps the password off the command line, masks secrets in output,
and adds per-server memory (OS · docker path) to the response. This script stays only as a fallback
for environments that cannot use launch (e.g. Windows without sshpass).

  - Prefer passing the password through the SSH_PASSWORD env var instead of `--password` (argv is visible in ps).
  - If the password shows up in output, it is masked as `***`.

Supports:
  - Password auth (auth=password)
  - PEM key auth (auth=key, AWS EC2 etc.)
  - macOS / Linux / Windows (including PowerShell 5.x) cross-platform

Usage:
  python ssh_connect.py --host HOST --port PORT --user USER
                        --auth password --password PASS
                        --command "CMD"

  python ssh_connect.py --host HOST --port PORT --user USER
                        --auth key --key-path ~/.ssh/my-key.pem
                        --command "CMD"
"""

from __future__ import print_function  # Python 2 compatibility (just in case)

import sys
import os
import argparse

# Keep one character the cp949 console cannot encode from killing even the help output
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="replace")

# ──────────────────────────────────────────────
# paramiko is imported right before connecting (--help and argument errors work without paramiko)
# ──────────────────────────────────────────────
paramiko = None


def _require_paramiko():
    """Lazily import paramiko. If missing, print install instructions and exit."""
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
    """Turn a path containing ~ and env vars into an absolute path."""
    if path is None:
        return None
    return os.path.expandvars(os.path.expanduser(path))


def _new_client():
    """Same as StrictHostKeyChecking=accept-new: store unseen keys in known_hosts, changed keys raise BadHostKeyException."""
    known_hosts = os.path.join(os.path.expanduser("~"), ".ssh", "known_hosts")
    client = paramiko.SSHClient()
    try:
        os.makedirs(os.path.dirname(known_hosts), exist_ok=True)
        if not os.path.exists(known_hosts):
            open(known_hosts, "a").close()
        client.load_host_keys(known_hosts)
    except (OSError, IOError) as e:
        print("[WARN] Could not use known_hosts, the host key is not remembered: " + str(e), file=sys.stderr)
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    return client


def _connect_password(host, port, user, password, timeout=15):
    """Connect an SSH client with password auth and return it."""
    client = _new_client()
    client.connect(
        hostname=host,
        port=port,
        username=user,
        password=password,
        timeout=timeout,
        look_for_keys=False,   # disable automatic key file lookup
        allow_agent=False,     # disable the SSH agent (password only)
    )
    return client


def _connect_key(host, port, user, key_path, timeout=15):
    """Connect an SSH client with PEM key auth and return it."""
    key_path = _expand_path(key_path)
    if not os.path.isfile(key_path):
        print("[ERROR] PEM key file not found: " + key_path)
        sys.exit(1)

    client = _new_client()
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
    Run a command over an SSH channel and return stdout/stderr/exit_code.
    Waits until the command finishes with no timeout (get_pty=True stands in for interactive sudo).
    """
    # get_pty=True: supports commands that need a terminal, such as sudo
    stdin, stdout, stderr = client.exec_command(command, get_pty=False)
    exit_code = stdout.channel.recv_exit_status()

    # Decode the byte stream as UTF-8 (bad characters replaced)
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
    # The env var wins for the password — the path that keeps it out of argv
    if args.password is None:
        args.password = os.environ.get("SSH_PASSWORD") or None
    print("[NOTICE] ssh_connect.py is kept for compatibility. Use launch_cli.py ssh --cred <server>.", file=sys.stderr)

    # ── Validate arguments ──────────────────────────────────
    if args.auth == "password" and not args.password:
        print("[ERROR] --auth password requires --password.")
        sys.exit(1)
    if args.auth == "key" and not args.key_path:
        print("[ERROR] --auth key requires --key-path.")
        sys.exit(1)

    # ── Connect ───────────────────────────────────────
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
    except paramiko.BadHostKeyException as e:
        print("[ERROR] The host key of " + args.host + " changed since the last connection. "
              "If the server was really replaced, remove its line from ~/.ssh/known_hosts and try again. " + str(e))
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

    # ── Run the command ──────────────────────────────────
    try:
        out, err, exit_code = run_command(client, args.command)
    except Exception as e:
        print("[ERROR] Error while running the command: " + str(e))
        traceback.print_exc()
        sys.exit(1)
    finally:
        client.close()

    # ── Print the result ──────────────────────────────────
    # If the server echoes env vars and such, the password stays on screen — mask it
    if args.password and len(args.password) >= 4:
        out = out.replace(args.password, "***")
        err = err.replace(args.password, "***")
    if out:
        print(out)
    if err:
        # Prefix stderr to tell it apart
        for line in err.splitlines():
            print("[STDERR] " + line)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
