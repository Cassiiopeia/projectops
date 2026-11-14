"""Records of how to connect, plus secret checks (shared by pro-launch and pro-agent-test, #629).

**How to reach the DB and read logs is decided by the agent reading the code.** Servers differ in framework
and access path, so a regex cannot guess it. The agent writes down what it learned and
the next run uses it. state.py picks the storage spot (outside the project, so it survives across worktrees).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from common.state import launch_file

ACCESS_FILE = "access.json"

# What must never enter the record. The file stays plain text and is reread on every run,
# so once in, it stays exposed — blocking before the write is the only sure way.
# We block the 'value', not the word (password) alone — a selector `#password_text_field` or
# a description like "tap the password field" got blocked and login knowledge was lost (#882).
# Patterns with a value group mask only the value when reported: `password=***`.

# A value starting with a selector or env-var reference is not a secret (#id, .class, [attr], $VAR, <placeholder>, {template})
_NOT_VALUE_START = r"(?![#.\[$<{])"
_PASSWORD_WORD = r"(?:password|passwd|pwd|비밀번호|비번)"
_SECRET_WORD = (r"(?:secret|client[_-]?secret|api[_-]?key|private[_-]?key|token|"
                r"(?:access|refresh|auth|id|bearer)[_-]?token)")

SECRET_PATTERNS = [
    (r'[\w.+-]+@[\w-]+\.[\w.]{2,}', "email address"),
    (r'01[016-9][-\s]?\d{3,4}[-\s]?\d{4}', "phone number"),
    (r'eyJ[\w-]{10,}\.[\w-]{10,}', "JWT token"),
    # key=value · key: value · JSON {"password": "x"} (#589)
    (r'(?i)["\']?\b' + _PASSWORD_WORD + r'\b["\']?\s*[:=]\s*["\']?(?P<value>' + _NOT_VALUE_START
     + r'[^\s"\',;]{4,})', "password"),
    # Value right after the word with no separator (password hunter2) — only values mixing letters and digits (prose passes)
    (r'(?i)\b' + _PASSWORD_WORD + r'\s+(?P<value>(?=\S*\d)(?=\S*[a-z])[a-z0-9!@$%^&*_+-]{6,})(?!\S)',
     "password"),
    (r'(?i)["\']?\b' + _SECRET_WORD + r'\b["\']?\s*[:=]\s*["\']?(?P<value>' + _NOT_VALUE_START
     + r'[^\s"\',;]{8,})', "secret value"),
    # Keys with a service-defined shape (caught even without a keyword)
    (r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{20,}|'
     r'AKIA[0-9A-Z]{16}|xox[abprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35})', "API key"),
    (r'-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----', "private key"),
]


def _mask(match: re.Match) -> str:
    """Matched span with only the value masked > `password=***`. Without a value group, keep the first 3 chars."""
    if "value" in match.re.groupindex and match.group("value"):
        return match.group(0)[:match.start("value") - match.start()] + "***"
    sample = match.group(0)
    return sample[:3] + "***" if len(sample) > 3 else "***"


def find_secret_spans(text: str) -> list[dict]:
    """Spans that look like secrets: [{label, matched_span (masked)}]. Tells the agent which part to fix."""
    spans = []
    for pattern, label in SECRET_PATTERNS:
        match = re.search(pattern, text)
        if match:
            spans.append({"label": label, "matched_span": _mask(match)})
    return spans


def find_secrets(text: str) -> list[str]:
    """Anything that looks like a secret. Reports never reveal the full original either."""
    return [f"{span['label']}({span['matched_span']})" for span in find_secret_spans(text)]


def access_path(root: Path) -> Path:
    return launch_file(root, ACCESS_FILE)


def load_access(root: Path) -> dict:
    f = access_path(root)
    if not f.is_file():
        return {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_access(root: Path, data: dict) -> Path:
    f = access_path(root)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return f


# ── Track record of connection methods (#836) ─────────────────────────────
#
# Records whether a saved connection method still works (memory principles 2 and 4). Only results the tool checked itself.
# access.json keeps the human-written values as is; results pile up in a side file — some keys hold plain strings
# (logs command etc.) so fields cannot be added, and access show/detect print the key list as is.
# Keep only date and result code. Raw error text may contain secrets, so it is not stored.

STATUS_FILE = "access_status.json"


def status_path(root: Path) -> Path:
    return launch_file(root, STATUS_FILE)


def load_status(root: Path) -> dict:
    f = status_path(root)
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_status(root: Path, data: dict) -> None:
    f = status_path(root)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def needs_verify(entry: dict | None) -> bool:
    """Was the last result a failure? If so, ask for a check on next use."""
    return bool(entry) and entry.get("last") == "fail"


def record_result(root: Path, key: str, ok: bool, code: str | None = None,
                  today: str | None = None) -> dict:
    """Record the result of the connection method stored under key. Returns the state **before** recording (whether this call used a suspect record).

    Success > verified(date), failure > last_fail{date, code}. Same result on the same day counts once (no inflation).
    """
    import datetime as _dt
    day = today or _dt.date.today().isoformat()
    data = load_status(root)
    prev = dict(data.get(key) or {})
    e = dict(prev)
    if ok:
        if e.get("verified") != day:
            e["ok"] = int(e.get("ok", 0)) + 1
        e["verified"] = day
        e["last"] = "ok"
    else:
        last_fail = e.get("last_fail") or {}
        if last_fail.get("date") != day:
            e["fail"] = int(e.get("fail", 0)) + 1
        e["last_fail"] = {"date": day, "code": code}
        e["last"] = "fail"
    data[key] = e
    try:
        _save_status(root, data)
    except OSError:
        pass   # the track record is secondary — the main command result goes out even if this write fails
    return prev


def reset_status(root: Path, key: str) -> None:
    """A changed method makes the old track record meaningless (on access set/unset)."""
    data = load_status(root)
    if key in data:
        del data[key]
        try:
            _save_status(root, data)
        except OSError:
            pass
