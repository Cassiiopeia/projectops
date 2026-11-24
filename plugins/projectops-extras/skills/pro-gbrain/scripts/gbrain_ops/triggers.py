"""Capture events vs actual delivery: event policy, idempotent records, per-record receipts"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from . import common, context, pro_brain, runtime

EVENTS = ("report", "issue-done", "session-end", "merge", "deploy", "manual")
# Legacy single mode (pro-brain `capture`) > events it implies
LEGACY_CAPTURE_EVENTS = {"issue-end": ["report", "issue-done"], "session-end": ["session-end"], "merge": ["merge"],
                         "manual": ["manual"]}


def legacy_capture_mode(events: list[str]) -> str:
    """Event list > closest single pro-brain capture mode, so readers of the old key keep one meaning"""
    if "report" in events or "issue-done" in events:
        return "issue-end"
    for mode in ("merge", "session-end"):
        if mode in events:
            return mode
    return "manual"


def modules():
    sys.path.insert(0, str(pro_brain.pro_brain_scripts_directory()))
    from brain import repo_facts, switch_edit
    return repo_facts, switch_edit


def inspect(root: Path) -> dict:
    root = context.find_repo_root(root)
    facts, _ = modules()
    text = facts.read_version_yml_text(root)
    raw = facts.read_nested_block(text, facts.KNOWLEDGE_BLOCK_PATH) or {}
    events = (facts.parse_flow_list(raw["capture_events"]) if "capture_events" in raw
              else LEGACY_CAPTURE_EVENTS.get(raw.get("capture", "issue-end"), ["manual"]))
    workflows = []
    folder = root / ".github" / "workflows"
    for path in sorted(folder.glob("*.y*ml")):
        content = path.read_text(encoding="utf-8", errors="replace")
        if any(term in content for term in ("gbrain", "pro-brain", "brain_cli")):
            workflows.append(str(path.relative_to(root)))
    return {"repo": str(root), "enabled": raw.get("enabled") is True, "events": events,
            "runner": raw.get("capture_runner", "agent"), "workflow_candidates": workflows,
            "workflow_verified": False, "server_schedule": "unknown",
            "note_path": raw.get("path", "knowledge/"), "source": raw.get("capture_source") or None}


def configure(args):
    root = context.find_repo_root(Path(args.repo or ".").resolve())
    current = inspect(root)
    if not args.events:
        return {"ok": True, "code": "triggers", **current,
                "question": "When should project knowledge be captured? Choose report, issue-done, session-end, merge, deploy or manual.",
                "next": "triggers --events report,deploy --runner agent"}
    events = list(dict.fromkeys(item.strip() for item in args.events.split(",")))
    if not events or any(item not in EVENTS for item in events):
        raise common.StepError("invalid_event", "unsupported capture event", ", ".join(EVENTS))
    facts, editor = modules()
    text = facts.read_version_yml_text(root)
    # capture_events is the source of truth; capture mirrors it for pro-brain and older plugin versions
    updates = {"capture_events": events, "capture": legacy_capture_mode(events), "capture_runner": args.runner,
               "enabled": True}
    if args.source:
        updates["capture_source"] = args.source
    try:
        new = editor.set_knowledge_keys(text, updates, create_if_missing=True)
    except editor.SwitchEditError as error:
        raise common.StepError("switch_invalid", str(error), "repair version.yml, then retry") from error
    plan = {"ok": True, "code": "plan", "before": current, "events": events, "runner": args.runner,
            "source": args.source or current["source"], "changed": new != text,
            "summary": "configure event policy; this does not install a CI workflow or server scheduler",
            "next": "repeat with --apply --yes"}
    if not args.apply:
        return plan
    if not args.yes:
        raise common.StepError("needs_consent", "trigger changes require --yes", plan["next"])
    path = root / "version.yml"
    # Refuse if another session edited version.yml since planning; replace atomically
    if path.read_text(encoding="utf-8") != text:
        raise common.StepError("config_changed", "version.yml changed while planning", "retry triggers")
    descriptor, temporary = tempfile.mkstemp(prefix=".version-", dir=root)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(new)
        os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {**plan, "code": "configured", "next": "commit version.yml; inspect existing automation before installing a runner"}


def _identity(root: Path, key: str) -> tuple[str, Path]:
    _, remote = context.read_remote(root)
    project = hashlib.sha256((remote or str(root)).encode()).hexdigest()[:20]
    record = hashlib.sha256(key.encode()).hexdigest()
    return project, common.state_directory() / "events" / project / f"{record}.json"


def handle_event(args):
    root = context.find_repo_root(Path(args.repo or ".").resolve())
    policy = inspect(root)
    if not policy["enabled"] or args.event not in policy["events"]:
        return {"ok": True, "code": "skipped", "reason": "event disabled", "event": args.event, "next": None}
    if args.event == "deploy" and args.outcome != "success":
        return {"ok": True, "code": "skipped", "reason": "deployment success not confirmed", "next": None}
    key = f"issue-{args.issue}" if args.issue else args.record_id
    if not key:
        raise common.StepError("record_id_required", "use an issue or stable change-set identity", "pass --issue N or --record-id ID")
    if not args.note:
        collect = ["collect", "--capture-mode", "manual"]
        if args.issue:
            collect += ["--issue", str(args.issue)]
        return {"ok": True, "code": "needs_note", "record_id": key, "facts": pro_brain.run_brain_cli(collect, root),
                "next": "author or update this record with verified facts, then repeat event with --note FILE"}
    note = Path(args.note).resolve()
    if not note.is_file():
        raise common.StepError("note_missing", "note file does not exist", "pass --note FILE")
    digest = hashlib.sha256(note.read_bytes()).hexdigest()
    project, receipt_path = _identity(root, key)
    previous = common.read_json(receipt_path) or {}
    if previous.get("digest") == digest and previous.get("status") == "done":
        return {"ok": True, "code": "noop", "record_id": key, "receipt": str(receipt_path), "next": None}
    if not args.apply:
        return {"ok": True, "code": "plan", "record_id": key, "digest": digest, "previous": previous.get("status"),
                "next": "repeat with --apply --yes"}
    if not args.yes:
        raise common.StepError("needs_consent", "event delivery requires --yes", "repeat with --apply --yes")
    # Exclusive per-record lock; an unexplained lock is never broken
    common.ensure_private_directory(receipt_path.parent)
    lock = receipt_path.with_suffix(".lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise common.StepError("event_busy", "this record is already being handled", "inspect the active runner before retrying") from None
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(str(os.getpid()))
        existing = _find_record_note(root, policy, key)
        with tempfile.TemporaryDirectory(prefix="pro-gbrain-event-") as staging:
            delivered = _stage_under_record_name(note, existing, Path(staging))
            result = pro_brain.run_brain_cli(["write", "--note", str(delivered), "--id", key], root)
            if result.get("code") == "bad_args":
                result = _repo_fallback(root, policy, delivered, existing, previous.get("digest"))
        state = {"schema": 1, "project": project, "record_id": key, "event": args.event,
                 "digest": digest, "status": "done" if result.get("ok") else "failed", "updated_at": common.timestamp()}
        common.write_private_json(receipt_path, state)
        return {**result, "record_id": key, "receipt": str(receipt_path),
                "next": result.get("next") or ("inspect the configured sync runner" if result.get("ok") else "retry this event")}
    finally:
        lock.unlink()


def _find_record_note(root: Path, policy: dict, key: str) -> Path | None:
    """Knowledge folder > the note whose frontmatter id is this record (first match), else None"""
    folder = (root / str(policy["note_path"])).resolve()
    if not folder.is_dir():
        return None
    id_line = re.compile(r'^id:\s*["\']?' + re.escape(key) + r'["\']?\s*$', re.MULTILINE)
    for path in sorted(folder.rglob("*.md")):
        head = path.read_text(encoding="utf-8", errors="replace")[:2000]
        if head.startswith("---") and id_line.search(head.split("\n---", 1)[0]):
            return path
    return None


def _stage_under_record_name(note: Path, existing: Path | None, staging: Path) -> Path:
    """Note > copy named like the record's existing file, so one record keeps one file across events"""
    if existing is None or existing.name == note.name:
        return note
    staged = staging / existing.name
    shutil.copyfile(note, staged)
    return staged


def _repo_fallback(root, policy, note, existing, last_written_digest):
    # pro-brain without `write`: repo file only, never reported as delivered to a brain
    facts, _ = modules()
    raw = facts.read_nested_block(facts.read_version_yml_text(root), facts.KNOWLEDGE_BLOCK_PATH) or {}
    if raw.get("repo_notes") is False:
        return {"ok": False, "code": "write_upgrade_required", "next": "install pro-brain with destination write support"}
    target = (existing or (root / str(policy["note_path"]) / note.name)).resolve()
    if not target.is_relative_to(root) or target == root:
        raise common.StepError("invalid_note_path", "notes must stay inside this repository", "fix knowledge.path")
    target.parent.mkdir(parents=True, exist_ok=True)
    # Overwrite only what this flow wrote last; a hand-edited note is a conflict
    if target.exists() and target.read_bytes() != note.read_bytes():
        current = hashlib.sha256(target.read_bytes()).hexdigest()
        if current != last_written_digest:
            return {"ok": False, "code": "note_conflict", "path": str(target),
                    "next": "merge the edits into the note deliberately, then pass that file"}
    if target != note:
        target.write_bytes(note.read_bytes())
    return {"ok": True, "code": "repo_written", "path": str(target), "ingestion": "pending_commit_and_sync",
            "next": "commit with pro-commit, then run the selected sync runner"}
