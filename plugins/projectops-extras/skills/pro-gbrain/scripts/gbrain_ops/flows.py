"""add / repair: ordered, idempotent steps per mode with a resumable state file (<home>/.projectops/gbrain/<project>.json).
team: server > repo > local > registry > verify | own: repo > connect | repo-only: repo
A failed step stops the run and is reported with its code and next step; finished steps are skipped on the next add.
"""
from __future__ import annotations

from pathlib import Path

from . import common, local_sync, mcp_check, pro_brain, provisioner as provisioner_module, registry_store, repo_switch

STEPS_BY_MODE = {"team": ("server", "repo", "local", "registry", "verify"),
                 "own": ("repo", "connect"),
                 "repo-only": ("repo",)}
DEFAULT_CAPTURE = "issue-end"


# ---------- state ----------
def state_path(project: str) -> Path:
    return common.state_directory() / f"{project}.json"


def load_state(project: str) -> dict:
    return common.read_json(state_path(project)) or {"project": project, "steps": {}}


def save_state(state: dict) -> None:
    common.write_private_json(state_path(state["project"]), state)


# ---------- context shared by steps ----------
class Run:
    def __init__(self, facts: dict, mode: str, options: dict, section: dict | None, provisioner):
        self.facts = facts
        self.mode = mode
        self.options = options
        self.section = section
        self.provisioner = provisioner
        self.project = facts["project"]
        self.repo_root = Path(facts["repo_root"])
        self.state = load_state(self.project)
        self.state["mode"] = mode
        # Team write mode: flag > recorded state > repo switch > sync (the behavior before direct existed)
        self.write_mode = (options.get("write") or self.state.get("write") or repo_switch.read(self.repo_root)["write_mode"]
                           or repo_switch.DEFAULT_WRITE_MODE) if mode == "team" else None
        if self.write_mode:
            self.state["write"] = self.write_mode
        block = (registry_store.find_provisioner(section)[1] or {}) if provisioner else {}
        self.sync_settings = block.get("sync") or {}
        self.sync_root = Path(str(self.sync_settings.get("root") or common.default_sync_root())).expanduser()
        self.home_directory = local_sync.sync_home(self.sync_root, self.project)

    @property
    def brain(self) -> dict:
        return self.state.setdefault("brain", {})


def mcp_name_and_url(run: Run) -> tuple[str | None, str | None]:
    return (run.options.get("mcp_name") or run.brain.get("mcp_server_name"),
            run.options.get("mcp_url") or run.brain.get("mcp_url"))


# ---------- steps ----------
def step_server(run: Run) -> dict:
    if run.provisioner is None:
        if run.options.get("mcp_url") and run.options.get("mcp_name"):
            run.brain.update({"mcp_url": run.options["mcp_url"], "mcp_server_name": run.options["mcp_name"]})
            return {"result": "manual brain recorded"}
        raise common.StepError("manual_server_steps", "no brain server (provisioner) is configured for this machine",
                               "a brain admin follows `server_steps`, then run add --mode team --mcp-url URL --mcp-name NAME",
                               {"server_steps": provisioner_module.manual_server_steps(run.project)})
    created = run.provisioner.create(run.project)
    brain = created.get("brain") or {}
    run.brain.update({key: brain.get(key) for key in ("mcp_url", "mcp_server_name", "database_name", "writer_role",
                                                       "service_name", "port") if brain.get(key) is not None})
    is_secret_saved = local_sync.save_writer_secret(run.home_directory, created.get("writer_secret"))
    return {"result": "ready", "server_steps": created.get("steps"), "writer_secret_saved": is_secret_saved,
            "is_healthy": brain.get("is_healthy")}


def step_repo(run: Run) -> dict:
    arguments = ["setup", "--apply", "--yes", "--enable", "--capture", run.options.get("capture") or DEFAULT_CAPTURE,
                 "--claude-md", run.options.get("claude_md") or "add"]
    if run.mode == "team":
        name, url = mcp_name_and_url(run)
        if not (name and url):
            raise common.StepError("team_brain_unknown", "the team brain name and URL are not known yet",
                                   "run the server step first (add or repair)")
        arguments += ["--team-brain-name", name, "--team-brain-url", url,
                      "--team-brain-contact", run.options.get("contact") or "the brain admin",
                      "--team-write", run.write_mode]
        if run.write_mode == "direct":
            # Direct: notes go to the team brain only, nothing is committed to knowledge/
            arguments += ["--to", "team"]
    result = pro_brain.run_brain_cli(arguments, run.repo_root)
    if not result.get("ok"):
        raise common.StepError(f"repo_{result.get('code') or 'setup_failed'}", str(result.get("summary")),
                               result.get("next") or "run pro-brain setup by hand to see the question it needs")
    return {"result": "switch written", "changed_files": result.get("changed_files") or result.get("written"),
            "next": "commit the changed files with pro-commit on an issue branch and open a PR (never push to a protected branch)"}


def step_connect(run: Run) -> dict:
    result = pro_brain.run_brain_cli(["connect", "--apply", "--yes", "--source-id", local_sync.source_id(run.project)],
                                     run.repo_root)
    if not result.get("ok") and result.get("code") not in ("already_connected", "no_notes_yet"):
        raise common.StepError(f"connect_{result.get('code')}", str(result.get("summary")), result.get("next"))
    return {"result": result.get("code"), "summary": result.get("summary")}


def step_local(run: Run) -> dict:
    if run.write_mode == "direct":
        return {"result": "skipped", "why": "direct write: members write to the team brain, no sync machine is needed"}
    if run.provisioner is None:
        return {"result": "skipped", "why": "no provisioner: the brain admin's machine syncs the knowledge folder"}
    brain = run.brain
    if not run.facts.get("remote_url"):
        raise common.StepError("no_remote", "the repository has no origin remote to clone from", "add an origin remote")
    port = local_sync.check_database_port(run.sync_settings)
    if not port["reachable"]:
        raise common.StepError("sync_database_unreachable", f"database {port['host']}:{port['port']} does not answer",
                               "start the database tunnel to the brain server, then run repair")
    connection_url = local_sync.read_writer_connection(run.home_directory, run.sync_settings,
                                                       brain.get("writer_role") or f"{run.project}_writer",
                                                       brain.get("database_name") or f"gbrain_{run.project}")
    common.ensure_private_directory(run.home_directory)
    branch = run.facts["default_branch"]
    embedding = {key: (run.sync_settings.get(key) or run.facts["own_brain"].get(key))
                 for key in ("embedding_model", "embedding_dimensions")}
    result = {"folder": str(run.home_directory),
              "clone": local_sync.ensure_clone(run.home_directory, run.facts["remote_url"], branch),
              "gbrain_config": local_sync.ensure_gbrain_config(run.home_directory, connection_url, embedding),
              "source": local_sync.ensure_source(run.home_directory, run.project),
              "sync_script": local_sync.ensure_sync_script(run.project, run.home_directory, branch)}
    if not run.options.get("no_first_sync"):
        result["first_sync"] = local_sync.run_first_sync(run.home_directory)
        if result["first_sync"]["exit_code"] != 0:
            raise common.StepError("sync_first_run_failed", "everything is in place but the first sync failed",
                                   f"read first_sync.tail, fix it, then run repair (or run {run.home_directory / local_sync.SYNC_SCRIPT_NAME})",
                                   {"local": result})
    result["schedule"] = (f"covered by the job that runs {run.sync_root}/*/sync.sh" if run.sync_settings.get("scheduler") == "glob"
                          else f"add an hourly job that runs {run.home_directory / local_sync.SYNC_SCRIPT_NAME}")
    return result


def step_registry(run: Run) -> dict:
    if run.section is None:
        return {"result": "skipped", "why": "no private registry on this machine (nothing to record)"}
    name, url = mcp_name_and_url(run)
    brain_entry = {key: value for key, value in {
        "engine": "gbrain", "kind": "team", "database": run.brain.get("database_name"),
        "mcp_url": url, "mcp_server_name": name, "service": run.brain.get("service_name"), "port": run.brain.get("port"),
        "server": (registry_store.find_provisioner(run.section)[1] or {}).get("server") if run.provisioner else None,
        "provisioned_by": run.provisioner.name if run.provisioner else None,
        "sync_script": str(run.home_directory / local_sync.SYNC_SCRIPT_NAME) if run.provisioner and run.write_mode == "sync" else None,
        "write": run.write_mode,
    }.items() if value is not None}
    if run.write_mode == "direct":
        knowledge_entry = {"enabled": True, "brain": registry_store.team_brain_name(run.project), "sync": "direct-write"}
    else:
        knowledge_entry = {"enabled": True, "brain": registry_store.team_brain_name(run.project), "path": "knowledge/",
                           "source_id": local_sync.source_id(run.project), "sync": "repo-commit"}
    return registry_store.apply_entries(run.project, brain_entry, knowledge_entry)


def step_verify(run: Run) -> dict:
    if run.provisioner is None:
        return {"result": "skipped", "why": "no provisioner token API: verify with a teammate token via pro-brain connect --team"}
    _, url = mcp_name_and_url(run)
    verification = mcp_check.run_verification(run.provisioner, run.project, url, run.write_mode)
    if not verification["passed"]:
        raise common.StepError("verify_failed", "end-to-end check failed", "read `checks`, fix the failing part, then run repair",
                               {"verification": verification})
    return verification


STEP_FUNCTIONS = {"server": step_server, "repo": step_repo, "connect": step_connect, "local": step_local,
                  "registry": step_registry, "verify": step_verify}


def execute(run: Run, redo_all: bool, only_steps: list[str] | None = None) -> dict:
    """Run the mode's steps in order; stop at the first failure (state keeps what finished)"""
    report, skipped = {}, []
    for step_name in STEPS_BY_MODE[run.mode]:
        if only_steps and step_name not in only_steps:
            continue
        recorded = run.state["steps"].get(step_name) or {}
        if recorded.get("status") == "done" and not redo_all:
            skipped.append(step_name)
            continue
        try:
            outcome = STEP_FUNCTIONS[step_name](run)
        except common.StepError as error:
            run.state["steps"][step_name] = {"status": "failed", "at": common.timestamp(), "code": error.code}
            save_state(run.state)
            return {"ok": False, "code": error.code, "summary": f"step {step_name} failed: {error.message}",
                    "next": error.next_step, "failed_step": step_name, "finished": report, "skipped_done": skipped,
                    **error.details}
        run.state["steps"][step_name] = {"status": "done", "at": common.timestamp()}
        save_state(run.state)
        report[step_name] = outcome
    return {"ok": True, "code": "done", "finished": report, "skipped_done": skipped}
