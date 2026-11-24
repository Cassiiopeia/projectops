"""gbrain-local adapter: this machine's gbrain CLI (PGLite, local or remote Postgres, Supabase: gbrain's own engines)
Writes with `gbrain put <slug>` (content on stdin, expected revision from `gbrain get`), so a re-run updates in place.
The database URL is never printed: only its masked form, host and port.
"""
from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from urllib.parse import urlsplit

from .. import brain_usage, http_client, note_file
from .base import Adapter, check, write_result

DOCTOR_TIMEOUT_SECONDS = 180
TCP_TIMEOUT_SECONDS = 5
FIND_LIMIT = 500
# gbrain doctor --json check names > what they mean for writing notes
ENGINE_CHECKS = {"connection": "database connection", "pgvector": "pgvector extension", "schema_version": "schema migrations",
                 "embeddings": "embeddings", "stale_locks": "stale locks"}
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
DEFAULT_POSTGRES_PORT = 5432


def engine_status() -> dict:
    code, output, _ = brain_usage.run_gbrain_full("engine", "status", "--json")
    return brain_usage.parse_json(output) or {} if code == 0 or output else {}


def gbrain_version() -> str | None:
    code, output, _ = brain_usage.run_gbrain_full("--version")
    return output.strip().splitlines()[-1].replace("gbrain", "").strip() if code == 0 and output.strip() else None


def postgres_target(database_url: str | None) -> dict:
    """Connection URL > {host, port, is_local, is_supabase, url_shown} (userinfo masked whole, never partially)"""
    if not database_url:
        return {}
    try:
        parts = urlsplit(database_url)
        host, port = parts.hostname or "", parts.port or DEFAULT_POSTGRES_PORT
    except ValueError:
        return {"url_shown": "<unparseable>"}
    return {"host": host, "port": port, "is_local": host in LOCAL_HOSTS, "is_supabase": "supabase" in host,
            "url_shown": http_client.mask_url(database_url)}


def is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=TCP_TIMEOUT_SECONDS):
            return True
    except OSError:
        return False


def pglite_lock(database_path: str | None) -> dict:
    """PGLite owner lock next to the database: {held, pid, alive}"""
    if not database_path:
        return {"held": False}
    owner = Path(database_path + ".gbrain-owner.json")
    if not owner.is_file():
        return {"held": False}
    try:
        pid = int((json.loads(owner.read_text(encoding="utf-8")) or {}).get("pid") or 0)
    except (OSError, ValueError, TypeError):
        pid = 0
    alive = False
    if pid:
        try:
            os.kill(pid, 0)
            alive = True
        except PermissionError:
            alive = True
        except OSError:
            alive = False
    return {"held": True, "pid": pid or None, "alive": alive}


def doctor_rows(timeout_seconds: int = DOCTOR_TIMEOUT_SECONDS) -> dict:
    """gbrain doctor --json > {name: (status, message)} for the checks that matter to writing"""
    code, output, error = brain_usage.run_gbrain_full("doctor", "--json", timeout_seconds=timeout_seconds)
    parsed = brain_usage.parse_json(output) or {}
    rows = {item.get("name"): (item.get("status"), str(item.get("message") or "")[:200])
            for item in parsed.get("checks") or [] if isinstance(item, dict)}
    return {"rows": rows, "error": None if rows else (error or f"exit {code}")}


class GbrainLocalAdapter(Adapter):
    kind = "gbrain-local"

    def _status(self) -> dict:
        if "_engine" not in self.context:
            self.context["_engine"] = engine_status() if brain_usage.gbrain_binary() else {}
        return self.context["_engine"]

    def detect(self) -> dict:
        status = self._status()
        engine = status.get("effective_engine")
        return {"available": bool(engine) and status.get("thin_client") is not True, "engine": engine,
                "thin_client": status.get("thin_client") is True}

    def _engine_label(self, status: dict) -> str:
        if status.get("thin_client") is True:
            return "thin-client"
        engine = status.get("effective_engine") or "none"
        target = postgres_target(status.get("database_url"))
        return "supabase" if engine == "postgres" and target.get("is_supabase") else engine

    def doctor(self, quick: bool = False) -> dict:
        binary = brain_usage.gbrain_binary()
        if not binary:
            return {"checks": [check("gbrain_cli", "fail", "gbrain is not installed or not on PATH (also looked in ~/.bun/bin)",
                                     f"brain_cli.py install (guide: {brain_usage.GBRAIN_INSTALL_URL}); or set PRO_BRAIN_GBRAIN",
                                     code="gbrain_missing")]}
        checks = [check("gbrain_cli", "ok", f"gbrain {gbrain_version() or '?'} at {binary}")]
        status = self._status()
        label = self._engine_label(status)
        capabilities = {"engine": label, "version": gbrain_version(), "write": "gbrain put", "search": "gbrain search/query"}
        if label == "thin-client":
            checks.append(check("engine", "fail", "this gbrain is a thin client of a remote brain, not a local brain",
                                "choose a remote destination (setup --to remote:NAME) for that brain", code="local_is_thin_client"))
            return {"checks": checks, "capabilities": capabilities}
        if label == "none":
            checks.append(check("engine", "fail", "gbrain has no brain on this machine yet",
                                "gbrain init (PGLite) or brain_cli.py install", code="brain_not_initialized"))
            return {"checks": checks, "capabilities": capabilities}
        checks.append(check("engine", "ok", f"engine {label} (url from {status.get('db_url_source') or 'config'})"))
        if label == "pglite":
            checks += self._pglite_checks(status)
        else:
            checks += self._postgres_checks(status)
        if not quick and not any(row["status"] == "fail" for row in checks):
            checks += self._engine_doctor_checks(capabilities)
        source = self.destination.get("source_id")
        return {"checks": checks, "capabilities": capabilities,
                "command": f"gbrain put <slug> --expected-revision <rev> --content-origin inferred{' --source-id ' + source if source else ''} < note.md",
                "env": {"GBRAIN_HOME": os.environ.get("GBRAIN_HOME") or "(default)",
                        "PRO_BRAIN_GBRAIN": os.environ.get("PRO_BRAIN_GBRAIN") or "(unset)"}}

    def _pglite_checks(self, status: dict) -> list[dict]:
        path = status.get("database_path")
        rows = [check("pglite_database", "ok" if path and Path(path).exists() else "fail",
                      f"database {'found' if path and Path(path).exists() else 'missing'} at {path or '?'}",
                      None if path and Path(path).exists() else "gbrain init --pglite (or check GBRAIN_HOME)",
                      code=None if path and Path(path).exists() else "pglite_missing")]
        lock = pglite_lock(path)
        if lock["held"] and not lock["alive"]:
            rows.append(check("pglite_lock", "warn", f"owner lock names pid {lock['pid']}, which is not running",
                              "gbrain doctor --json (it reports stale locks); gbrain repair if it says so"))
        elif lock["held"]:
            rows.append(check("pglite_lock", "ok", f"held by running pid {lock['pid']} (gbrain routes CLI writes to it)"))
        return rows

    def _postgres_checks(self, status: dict) -> list[dict]:
        target = postgres_target(status.get("database_url"))
        if not target.get("host"):
            return [check("postgres_target", "warn", "database host unknown from engine status (URL from env or hidden)",
                          "gbrain engine status --json")]
        reachable = is_port_open(target["host"], target["port"])
        fix = ("start the SSH tunnel or local Postgres that serves " if target["is_local"] else "check network, VPN or firewall for ")
        return [check("postgres_reachable", "ok" if reachable else "fail",
                      f"{target['host']}:{target['port']} {'answers' if reachable else 'does not answer'} ({target['url_shown']})",
                      None if reachable else fix + f"{target['host']}:{target['port']}, then run doctor again",
                      code=None if reachable else ("tunnel_down" if target["is_local"] else "postgres_unreachable"))]

    def _engine_doctor_checks(self, capabilities: dict) -> list[dict]:
        report = doctor_rows()
        if report["error"]:
            return [check("gbrain_doctor", "warn", f"gbrain doctor did not answer ({report['error']})", "gbrain doctor --json")]
        rows = []
        fixes = {"connection": "gbrain db-repair --json (auth, database exists, permissions)",
                 "pgvector": "as a superuser in that database: CREATE EXTENSION IF NOT EXISTS vector;",
                 "schema_version": "gbrain init --migrate-only (or gbrain apply-migrations --yes)",
                 "embeddings": "gbrain doctor --json names the enable command (needs the user's consent and key)",
                 "stale_locks": "gbrain repair --apply"}
        for name, label in ENGINE_CHECKS.items():
            if name not in report["rows"]:
                continue
            state, message = report["rows"][name]
            status = "ok" if state == "ok" else ("warn" if state in ("warn", "warning") or name == "embeddings" else "fail")
            rows.append(check(name, status, f"{label}: {message}", None if status == "ok" else fixes[name],
                              code=None if status != "fail" else f"{name}_failed"))
            if name == "embeddings":
                capabilities["embeddings"] = "off" if "disabled" in message.lower() else ("on" if state == "ok" else "unknown")
        return rows

    def _via_source_sync(self) -> str | None:
        """Repo files are also chosen and a source of this brain already reads the folder: that sync is the write"""
        resolved = self.context.get("_resolved") or {}
        if "repo" not in resolved.get("write_targets", []):
            return None
        detected = brain_usage.detect_gbrain()
        sources = brain_usage.personal_sources_for_repo(detected, self.context["root"], f"{self.context['project']}-knowledge")
        return sources[0]["id"] if sources else None

    def write(self, note: dict) -> dict:
        source = self._via_source_sync()
        if source:
            return write_result(self.destination, "via_source_sync",
                                f"source {source} already imports the repo folder; commit the note and gbrain sync picks it up",
                                source=source)
        slug = note["slug"]
        code, output, error = brain_usage.run_gbrain_full("get", slug, "--json")
        revision = (brain_usage.parse_json(output) or {}).get("revision") if code == 0 else None
        if code != 0 and error not in ("page_not_found", "not_found"):
            return write_result(self.destination, "failed", f"gbrain get {slug} failed ({error})", code="read_failed",
                                fix="brain_cli.py doctor --to local")
        arguments = ["put", slug, "--content-origin", "inferred", "--reason", "pro-brain note", "--json"]
        if revision:
            arguments[2:2] = ["--expected-revision", str(revision)]
        if self.destination.get("source_id"):
            arguments[2:2] = ["--source-id", str(self.destination["source_id"])]
        code, output, error = brain_usage.run_gbrain_full(*arguments, input_text=note["content"])
        parsed = brain_usage.parse_json(output) or {}
        if code != 0:
            return write_result(self.destination, "failed", f"gbrain put {slug} failed ({error})", code=error or "put_failed",
                                fix="run write again (the revision is read fresh); if it repeats: brain_cli.py doctor --to local")
        outcome = "unchanged" if parsed.get("noop") is True else ("updated" if revision else "written")
        return write_result(self.destination, outcome, f"{outcome} page {slug}", slug=slug, revision=parsed.get("revision"))

    def search_hint(self) -> str:
        return f"gbrain search \"<words>\" (pages under {note_file.project_prefix(self.context['project'])})"

    def note_ids(self) -> tuple[set[str] | None, str]:
        prefix = note_file.project_prefix(self.context["project"])
        code, output, error = brain_usage.run_gbrain_full("find", prefix, "--limit", str(FIND_LIMIT), "--json")
        parsed = brain_usage.parse_json(output) if code == 0 else None
        if parsed is None:
            return None, f"gbrain find failed ({error or 'no answer'})"
        slugs = [page.get("slug", "") for page in parsed.get("pages") or [] if isinstance(page, dict)]
        return {slug.rsplit("/", 1)[-1] for slug in slugs if slug}, f"local brain pages {prefix}*"

    def backup_hint(self) -> str | None:
        source = self.destination.get("source_id")
        selector = f"--source {source}" if source else f"--slug-prefix {note_file.project_prefix(self.context['project'])}"
        folder = f"~/gbrain-backup/{note_file.slug_part(self.context['project'])}"
        return (f"gbrain export {selector} --dir {folder}/$(date +%Y%m%d)   "
                "# daily via cron, launchd or Task Scheduler; export refuses to overwrite, so use a fresh dated folder")
