"""Management actions delegated to the official GBrain CLI: plan by default, explicit target and effects"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from . import common, context, credentials, pro_brain, runtime


def required(args, field):
    value = getattr(args, field, None)
    if not value:
        raise common.StepError("missing_option", f"--{field.replace('_', '-')} is required", "manage --help")
    return value


def cmd_manage(args):
    return HANDLERS[args.action](args)


def doctor(args):
    env, _ = runtime.environment(args)
    binary = runtime.executable(env)
    result = {"ok": True, "code": "inventory", "executable": binary, "engine": runtime.engine(args) if binary else None,
              "credentials": credentials.list_credential_names(), "harnesses": {}, "automation": None,
              "summary": "installation, engine, harness and automation are separate checks"}
    if binary:
        result["version"] = runtime.run(["--version"], args)
        for harness in ("claude-code", "codex"):
            result["harnesses"][harness] = runtime.run(["setup", harness, "--dry-run", "--json"], args)
        result["automation"] = runtime.run(["autopilot", "--status", "--json"], args)
        if args.probe:
            result["health"] = runtime.run(["doctor", "--fast", "--json"], args, timeout=120)
    from . import triggers
    try:
        result["project"] = triggers.inspect(Path(args.repo or ".").resolve())
    except common.StepError as error:
        if error.code != "not_a_repo":
            raise
        result["project"] = {"code": "not_a_repo", "next": "pass --repo to inspect project policy"}
    if result["harnesses"]:
        result["harness_targets"] = summarize_harness_targets(result["harnesses"])
    result["next_steps"] = recommend_next_steps(result)
    return result


def _harness_needs_setup(preview: dict | None) -> bool:
    """setup --dry-run result > True when a step would write (mcp, hooks, receipt); unknown shapes > False"""
    data = (preview or {}).get("result")
    if not isinstance(data, dict):
        return False
    return any(isinstance(step, dict) and step.get("action") == "write" for step in data.get("steps") or [])


def summarize_harness_targets(harnesses: dict) -> dict:
    """setup previews > brain each harness points at, plus whether they agree (unknown when a preview failed)"""
    targets = {}
    for name, preview in harnesses.items():
        data = (preview or {}).get("result")
        brain = (data.get("target") or {}).get("brain") if isinstance(data, dict) else None
        targets[name] = brain or "unknown"
    known = [json.dumps(value, sort_keys=True) for value in targets.values() if value != "unknown"]
    same = "unknown" if len(known) < len(targets) else len(set(known)) == 1
    return {"targets": targets, "same_brain": same}


def recommend_next_steps(inventory: dict) -> list[dict]:
    """doctor inventory > ordered setup steps: install > init > harness wiring > capture triggers"""
    steps = []
    if not inventory.get("executable"):
        return [{"step": "install", "command": "manage install", "why": "GBrain CLI is not installed"}]
    engine = inventory.get("engine") or {}
    if not engine.get("effective_engine") and not engine.get("thin_client"):
        steps.append({"step": "init", "command": "manage init --engine pglite",
                      "why": "no brain is initialized; PGlite needs no server or provider key"})
    for name, preview in (inventory.get("harnesses") or {}).items():
        if _harness_needs_setup(preview):
            steps.append({"step": "harness", "command": f"manage harness --harness {name}",
                          "why": f"{name} would get new GBrain wiring; review the preview first"})
    project = inventory.get("project") or {}
    if project.get("repo") and not project.get("enabled"):
        steps.append({"step": "triggers", "command": f"triggers --repo {project['repo']}",
                      "why": "project knowledge capture is not configured"})
    return steps


def install(args):
    env, _ = runtime.environment(args)
    if runtime.executable(env):
        return {"ok": True, "code": "already_installed", "executable": runtime.executable(env), "next": "manage doctor"}
    bun = shutil.which("bun", path=env.get("PATH"))
    # Official GitHub distribution only; the same-named npm package is unrelated
    argv = [bun or "bun", "install", "-g", "github:garrytan/gbrain#stable"]
    if not args.apply:
        return {"ok": True, "code": "plan", "argv": argv, "runtime_available": bool(bun),
                "effects": ["install the official GBrain CLI globally for this user"],
                "next": "install Bun from its official installer if missing; then manage install --apply --yes"}
    if not args.yes:
        raise common.StepError("needs_consent", "installation requires --yes", "manage install --apply --yes")
    if not bun:
        raise common.StepError("bun_missing", "Bun is required by the official GBrain distribution",
                               "install Bun from https://bun.sh, then retry manage install")
    code, output = common.run(argv, env=env, timeout=600)
    return {"ok": code == 0 and runtime.executable(env) is not None, "code": "installed" if code == 0 else "install_failed",
            "exit_code": code, "output": runtime.redact(output[-2000:]), "next": "manage doctor"}


def initialize(args):
    current = runtime.engine(args)
    if current.get("effective_engine"):
        return {"ok": True, "code": "already_initialized", "engine": current, "next": "manage harness --harness <name>"}
    argv = ["init", "--pglite", "--no-embedding", "--non-interactive", "--json"]
    if args.engine == "postgres":
        if not args.credential or args.credential_env != "GBRAIN_DATABASE_URL":
            raise common.StepError("database_credential_required", "Postgres needs a stored database URL credential",
                                   "use --credential NAME --credential-field FIELD --credential-env GBRAIN_DATABASE_URL")
        argv = ["init", "--prefer-postgres", "--no-embedding", "--non-interactive", "--json"]
    return runtime.plan_or_run(argv, args, effects=[f"initialize a new {args.engine} brain; preserve existing brains"])


def harness(args):
    target = required(args, "harness")
    argv = ["setup", target, "--json", "--shape", "none", "--no-providers"]
    argv += ["--capture" if args.capture else "--no-capture"]
    if args.no_hooks:
        argv.append("--no-hooks")
    if args.source:
        argv += ["--source", args.source]
    preview = runtime.run([*argv, "--dry-run"], args)
    if not preview["ok"] or not args.apply:
        return {**preview, "code": "plan" if preview["ok"] else preview["code"], "next": "review target; repeat with --apply --yes"}
    result = runtime.plan_or_run(argv, args, effects=[f"wire {target} MCP, selected hooks and instructions"])
    if result["ok"]:
        result["verification"] = runtime.run(["doctor", "--only", "harness_wiring", "--json"], args)
    return result


def _registered_source_ids(args) -> set[str] | None:
    """sources list --json > registered ids; None when the list cannot be read"""
    listing = runtime.run(["sources", "list", "--json"], args)
    data = listing.get("result")
    items = data.get("sources") if isinstance(data, dict) else data
    if not listing["ok"] or not isinstance(items, list):
        return None
    return {item.get("id") for item in items if isinstance(item, dict)}


def source(args):
    """Source status, or register one new git-backed source (never --force, never an existing id)"""
    if not args.path:
        return runtime.run(["sources", "status", *([args.source] if args.source else []), "--json"], args)
    source_id = required(args, "source")
    folder = Path(args.path).expanduser().resolve()
    if not (folder / ".git").exists():
        raise common.StepError("not_a_git_repo", "a source path must be a git repository with committed files",
                               "commit the documents first, then pass that repository as --path")
    registered = _registered_source_ids(args)
    if registered is None:
        raise common.StepError("sources_unreadable", "could not list existing sources", "manage doctor --probe")
    if source_id in registered:
        return {"ok": True, "code": "already_registered", "source": source_id,
                "next": f"manage ingest --source {source_id}"}
    result = runtime.plan_or_run(["sources", "add", source_id, "--path", str(folder), "--no-federated", "--json"], args,
                                 effects=[f"register source {source_id} reading committed files of {folder}"])
    result["next"] = f"manage ingest --source {source_id}" if args.apply else result["next"]
    return result


def ingest(args):
    source = required(args, "source")
    argv = ["sync", "--source", source, "--no-pull", "--json"]
    if not args.embedding:
        argv.append("--no-embed")
    preview = runtime.run([*argv, "--dry-run"], args)
    if not args.apply or not preview["ok"]:
        return {**preview, "code": "plan" if preview["ok"] else preview["code"]}
    return runtime.plan_or_run(argv, args, effects=[f"index committed documents from {source}"])


def search(args):
    argv = ["query" if args.semantic else "search", required(args, "query"), "--json"]
    if args.source:
        argv += ["--source-id", args.source]
    return runtime.run(argv, args)


def embeddings(args):
    model = required(args, "model")
    argv = ["embeddings", "enable", "--embedding-model", model, "--json"]
    if args.dimensions:
        argv += ["--embedding-dimensions", str(args.dimensions)]
    result = runtime.plan_or_run(argv, args, effects=["enable embedding provider; future calls may cost money",
                                                    "host-wide model: every brain mounted on this host shares it",
                                                    "model and vector compatibility are enforced by GBrain"])
    result["backfill"] = "manage embed --apply --yes"
    return result


def embed(args):
    """Backfill vectors for chunks queued after enablement (enablement alone embeds nothing)"""
    return runtime.plan_or_run(["embed", "--stale", "--json"], args,
                               effects=["embed stale chunks with the configured provider; paid providers bill per token"])


def publish(args):
    page = Path(required(args, "file")).expanduser().resolve()
    out = Path(required(args, "out")).expanduser().resolve()
    if not page.is_file():
        raise common.StepError("file_missing", "publication input is missing", "pass --file FILE")
    if out.exists():
        raise common.StepError("output_exists", "publication will not overwrite an existing file", "choose a new --out path")
    digest = hashlib.sha256(page.read_bytes()).hexdigest()
    if args.apply and args.content_sha != digest:
        raise common.StepError("content_changed", "review the exact content before publication", "run without --apply and pass its --content-sha")
    result = runtime.plan_or_run(["publish", str(page), "--out", str(out)], args,
                                effects=["create local shareable HTML; no upload or public URL", "review sensitive content; automatic stripping is not a guarantee"])
    result["content_sha"] = digest
    if args.apply and result["ok"]:
        result["ok"] = out.is_file() and out.stat().st_size > 0
        result["artifact"] = str(out)
        result["public_url"] = None
        result["revocation"] = "local artifact only; copies shared elsewhere cannot be remotely revoked"
    return result


def schedule(args):
    """Autopilot maintenance runner: status, install, uninstall, pause, resume (brain-wide, never --force)"""
    action = args.schedule_action
    if action == "status":
        return runtime.run(["autopilot", "--status", "--json"], args)
    if action == "uninstall":
        return runtime.plan_or_run(["autopilot", "--uninstall"], args, effects=["remove the installed maintenance daemon"])
    if action in ("pause", "resume"):
        return runtime.plan_or_run(["autopilot", action], args, effects=[f"{action} brain-wide maintenance cycles"])
    if not args.repo:
        raise common.StepError("missing_option", "select the brain repository for its maintenance daemon", "pass --repo PATH")
    # PGlite holds a single-writer lock; a daemon would block every other writer, and --force is never passed
    if (runtime.engine(args).get("effective_engine")) == "pglite":
        raise common.StepError("pglite_single_writer", "a resident daemon on a PGlite brain locks out other writers",
                               "use Postgres for a scheduled runner, or run manage ingest on demand")
    argv = ["autopilot", "--install", "--repo", str(Path(args.repo).resolve()), "--no-inject"]
    if args.target:
        argv += ["--target", args.target]
    return runtime.plan_or_run(argv, args, effects=["install a persistent maintenance daemon under the host supervisor",
                                                    "undo with manage schedule --schedule-action uninstall"])


def note(args):
    repo = context.find_repo_root(Path(args.repo or ".").resolve())
    if args.file:
        if not args.apply or not args.yes:
            return {"ok": True, "code": "plan", "next": "repeat with --apply --yes to write to configured destinations"}
        return pro_brain.run_brain_cli(["write", "--note", str(Path(args.file).resolve())], repo)
    argv = ["collect", "--capture-mode", "manual"]
    if args.issue:
        argv += ["--issue", str(args.issue)]
    result = pro_brain.run_brain_cli(argv, repo)
    result["authoring"] = "synthesize verified facts and citations as a pro-brain note; then manage note --file FILE"
    return result


HANDLERS = {"doctor": doctor, "install": install, "init": initialize, "harness": harness, "source": source,
            "ingest": ingest,
            "search": search, "embeddings": embeddings, "embed": embed, "publish": publish, "schedule": schedule, "note": note}
