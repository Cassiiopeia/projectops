"""Destination adapter interface: detect, doctor, write, search hint, covered issues (gaps), backup hint
A new brain engine = one module with an Adapter subclass + one line in adapters/__init__.py ADAPTERS; nothing else changes.
"""
from __future__ import annotations

# Check status values: ok | warn (works, but look) | fail (this destination cannot be used) | skip (not applicable)
CHECK_STATUSES = ("ok", "warn", "fail", "skip")


def check(name: str, status: str, detail: str, fix: str | None = None, **facts) -> dict:
    """One doctor check row; fix is the concrete next command or action for warn and fail"""
    row = {"name": name, "status": status, "detail": detail}
    if fix:
        row["fix"] = fix
    row.update({key: value for key, value in facts.items() if value is not None})
    return row


def summarize_checks(checks: list[dict]) -> tuple[str, str | None]:
    """(health, code of the first failing check): healthy | degraded | unhealthy"""
    failing = next((row for row in checks if row["status"] == "fail"), None)
    if failing:
        return "unhealthy", failing.get("code") or failing["name"]
    return ("degraded" if any(row["status"] == "warn" for row in checks) else "healthy"), None


def write_result(destination: dict, outcome: str, summary: str, **facts) -> dict:
    """outcome: written | updated | unchanged | via_source_sync | skipped | failed"""
    return {"destination": destination["id"], "kind": destination["kind"], "ok": outcome != "failed",
            "outcome": outcome, "summary": summary, **{key: value for key, value in facts.items() if value is not None}}


class Adapter:
    """Base adapter; subclasses override what their engine supports (defaults say 'not supported' clearly)"""

    kind = "base"

    def __init__(self, destination: dict, context: dict):
        self.destination, self.context = destination, context

    def detect(self) -> dict:
        return {"available": False}

    def doctor(self, quick: bool = False) -> dict:
        """{checks, command (secrets masked), env (names only), capabilities}; quick skips slow engine checks"""
        return {"checks": [check("adapter", "fail", f"no doctor for {self.kind}", code="unsupported_destination")]}

    def write(self, note: dict) -> dict:
        return write_result(self.destination, "failed", f"{self.kind} cannot write notes", code="unsupported_destination")

    def write_many(self, notes: list[dict]) -> list[dict]:
        """Default: page by page (adapters with a batch tool override this)"""
        return [self.write(note) for note in notes]

    def search_hint(self) -> str:
        return ""

    def note_ids(self) -> tuple[set[str] | None, str]:
        """(note ids stored for this project, e.g. issue-12, change-20261124-abc1234; how it was read); None = unknown"""
        return None, f"{self.kind} cannot list notes"

    def backup_hint(self) -> str | None:
        return None


class UnsupportedAdapter(Adapter):
    kind = "unsupported"
