"""cred set secret sources: validate every argument first > read one source (--prompt, --from-env, --from-file, --from-clipboard)
Values never reach argv, responses or logs; --delete-after removes the file only after the store write succeeded.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Sources that fill --secret-field; --prompt without --secret-field stays the sudo / ssh password path
SECRET_SOURCE_FLAGS = (("prompt", "--prompt"), ("from_env", "--from-env"), ("from_file", "--from-file"),
                       ("from_clipboard", "--from-clipboard"))
CLIPBOARD_TIMEOUT_SECONDS = 10
# Linux clipboard readers, tried in order (Wayland first)
LINUX_CLIPBOARD_COMMANDS = (["wl-paste", "--no-newline"], ["xclip", "-selection", "clipboard", "-o"],
                            ["xsel", "--clipboard", "--output"])


def no_tty_alternatives(name: str, field: str | None) -> str:
    """next hint for --prompt without a terminal: separate terminal, or a source that needs none"""
    field_part = f" --secret-field {field}" if field else ""
    return (f"Run in a separate terminal: launch_cli.py cred set --name {name}{field_part} --prompt ; "
            f"or without a terminal: --secret-field {field or 'sudo_password'} --from-file PATH [--delete-after] | "
            f"--from-clipboard | --from-env VAR")


def _chosen_sources(args) -> list[str]:
    return [flag for attribute, flag in SECRET_SOURCE_FLAGS if getattr(args, attribute, None)]


def validate_set_arguments(args, name: str) -> dict | None:
    """Error payload for conflicting or incomplete cred set arguments (nothing is read or deleted yet)"""
    chosen = _chosen_sources(args)
    if len(chosen) > 1:
        return {"ok": False, "code": "conflicting_sources", "error": f"Pick one secret source, got {' + '.join(chosen)}",
                "next": f"cred set --name {name} --secret-field token --from-file PATH"}
    if args.json_value and args.json_file:
        return {"ok": False, "code": "conflicting_sources", "error": "Pass --json or --json-file, not both",
                "next": f"cred set --name {name} --json-file PATH"}
    needs_field = [flag for flag in chosen if flag != "--prompt"]
    if needs_field and not args.secret_field:
        return {"ok": False, "code": "secret_field_required", "error": f"{needs_field[0]} needs --secret-field <field>",
                "next": f"cred set --name {name} --secret-field token {needs_field[0]}"
                        + (f" {args.from_env}" if args.from_env else " PATH" if args.from_file else "")}
    if args.secret_field and not chosen:
        return {"ok": False, "code": "secret_source_required", "error": "--secret-field needs a source",
                "next": no_tty_alternatives(name, args.secret_field)}
    if args.delete_after and not args.from_file:
        return {"ok": False, "code": "delete_after_needs_file", "error": "--delete-after works only with --from-file",
                "next": f"cred set --name {name} --secret-field {args.secret_field or 'token'} --from-file PATH --delete-after"}
    for flag, path in (("--from-file", args.from_file), ("--json-file", args.json_file)):
        if path and not Path(path).is_file():
            return {"ok": False, "code": "file_not_found", "error": f"{flag}: no file at {path}",
                    "next": f"check the path, then call again with {flag} PATH"}
    if args.prompt and not sys.stdin.isatty():
        # Fail before any input is consumed: a pasted `! ... --prompt` line in a chat has no terminal
        return {"ok": False, "code": "no_tty", "error": "--prompt needs a terminal (stdin is not a TTY)",
                "next": no_tty_alternatives(name, args.secret_field)}
    return None


def load_json_fields(args) -> tuple[dict | None, dict | None]:
    """--json text or --json-file (UTF-8, BOM allowed) > fields dict"""
    source, label = (args.json_value, "--json") if args.json_value else (None, "--json-file")
    if args.json_file:
        source = Path(args.json_file).read_text(encoding="utf-8-sig", errors="replace")
    if not source:
        return None, None
    try:
        fields = json.loads(source)
    except json.JSONDecodeError as error:
        return None, {"ok": False, "code": "bad_json", "error": f"Invalid {label}: {error}",
                      "next": "put the JSON in a UTF-8 file and pass --json-file PATH" if label == "--json" else None}
    if not isinstance(fields, dict):
        return None, {"ok": False, "code": "bad_json", "error": f"{label} must be a JSON object"}
    return fields, None


def _read_clipboard() -> tuple[str | None, dict | None]:
    """OS clipboard text (macOS pbpaste, Windows Get-Clipboard, Linux wl-paste/xclip/xsel)"""
    if sys.platform == "darwin":
        candidates = [["pbpaste"]]
    elif os.name == "nt":
        candidates = [["powershell", "-NoProfile", "-Command",
                       "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Clipboard -Raw"]]
    else:
        candidates = list(LINUX_CLIPBOARD_COMMANDS)
    available = [command for command in candidates if shutil.which(command[0])]
    if not available:
        return None, {"ok": False, "code": "clipboard_unavailable",
                      "error": f"No clipboard reader found ({', '.join(command[0] for command in candidates)})",
                      "next": "save the value to a file and use --from-file PATH --delete-after"}
    for command in available:
        try:
            completed = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace",
                                       timeout=CLIPBOARD_TIMEOUT_SECONDS)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if completed.returncode == 0:
            return completed.stdout, None
    return None, {"ok": False, "code": "clipboard_unavailable", "error": "The clipboard could not be read",
                  "next": "save the value to a file and use --from-file PATH --delete-after"}


def _strip_one_newline(value: str) -> str:
    if value.endswith("\r\n"):
        return value[:-2]
    return value[:-1] if value.endswith("\n") else value


def read_secret(args, name: str, field: str) -> tuple[str | None, dict | None]:
    """Secret for --secret-field from the one chosen source (validated before)"""
    if args.from_env:
        value = os.environ.get(args.from_env, "")
        if not value:
            return None, {"ok": False, "code": "env_empty", "error": f"Environment variable {args.from_env} is empty"}
        return value, None
    if args.from_file:
        value = _strip_one_newline(Path(args.from_file).read_text(encoding="utf-8-sig", errors="replace"))
    elif args.from_clipboard:
        raw, error = _read_clipboard()
        if error:
            return None, error
        value = _strip_one_newline(raw)
    else:
        import getpass
        value = getpass.getpass(f"{field} for {name} (hidden): ")
    if not value:
        return None, {"ok": False, "code": "empty_secret", "error": f"The {field} value is empty"}
    return value, None


def delete_source_file(args) -> str | None:
    """--delete-after: remove the --from-file source (store write already succeeded); outcome for the response"""
    if not (args.delete_after and args.from_file):
        return None
    try:
        Path(args.from_file).unlink()
        return "deleted"
    except OSError as error:
        return f"not deleted ({type(error).__name__}): delete {args.from_file} yourself"
