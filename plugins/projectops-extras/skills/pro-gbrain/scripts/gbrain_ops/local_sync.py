"""The machine that writes the team brain: <root>/<project>/ with a sparse clone of the default branch, a gbrain config
for the writer role (600), one source <project>-knowledge and a generated sync.sh (700). Every step is idempotent:
existing pieces are checked and kept, never replaced or deleted.
"""
from __future__ import annotations

import json
import re
import shutil
import socket
from pathlib import Path

from . import common

TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "sync.sh.tmpl"
WRITER_SECRET_FILE = ".writer-role.json"
SYNC_SCRIPT_NAME = "sync.sh"
SYNC_SCRIPT_MODE = 0o700
PORT_CHECK_TIMEOUT_SECONDS = 5
DEFAULT_SPARSE_FOLDER = "knowledge"


def sync_home(sync_root: Path, project: str) -> Path:
    return sync_root / project


def source_id(project: str) -> str:
    return f"{project}-knowledge"


def strip_url_credentials(url: str) -> str:
    # https://user:token@host/... > https://host/... (a clone must not keep someone's token in .git/config)
    return re.sub(r"^(https?://)[^@/]+@", r"\1", url.strip())


def save_writer_secret(home_directory: Path, writer_secret: dict | None) -> bool:
    """Store the one-time writer secret from the server (600). False when there was none to store"""
    if not writer_secret or not writer_secret.get("password"):
        return False
    common.write_private_json(home_directory / WRITER_SECRET_FILE, writer_secret)
    return True


def read_writer_connection(home_directory: Path, sync_settings: dict, writer_role: str, database: str) -> str:
    secret = common.read_json(home_directory / WRITER_SECRET_FILE) or {}
    url = secret.get("sync_connection_url") or secret.get("connection_url")
    if url:
        return url
    if secret.get("password"):
        from urllib.parse import quote
        host = sync_settings.get("database_host", "127.0.0.1")
        port = sync_settings.get("database_port", 5432)
        sslmode = sync_settings.get("sslmode", "require")
        return f"postgresql://{writer_role}:{quote(secret['password'], safe='')}@{host}:{port}/{database}?sslmode={sslmode}"
    raise common.StepError(
        "writer_secret_missing", f"no writer password for {writer_role} on this machine ({home_directory / WRITER_SECRET_FILE})",
        "the server shows a writer password only when it creates the role: ask the brain admin for it and save it "
        f"as JSON {{\"password\": ...}} in {home_directory / WRITER_SECRET_FILE} (mode 600), then run repair")


def check_database_port(sync_settings: dict) -> dict:
    host = sync_settings.get("database_host", "127.0.0.1")
    port = int(sync_settings.get("database_port", 5432))
    try:
        with socket.create_connection((host, port), timeout=PORT_CHECK_TIMEOUT_SECONDS):
            return {"reachable": True, "host": host, "port": port}
    except OSError:
        return {"reachable": False, "host": host, "port": port}


def ensure_clone(home_directory: Path, remote_url: str, branch: str) -> str:
    """Sparse partial clone (knowledge/ + root files) of the default branch; an existing clone is checked, not replaced"""
    repo_directory = home_directory / "repo"
    clean_url = strip_url_credentials(remote_url)
    if (repo_directory / ".git").exists():
        _, current_url = common.run(["git", "-C", str(repo_directory), "config", "--get", "remote.origin.url"])
        if strip_url_credentials(current_url) != clean_url:
            raise common.StepError("sync_clone_mismatch", f"{repo_directory} already clones another repository",
                                   "move that folder away by hand (nothing was changed), then run repair")
        return "kept"
    if repo_directory.exists() and any(repo_directory.iterdir()):
        raise common.StepError("sync_folder_not_empty", f"{repo_directory} exists and is not a git clone",
                               "move that folder away by hand (nothing was changed), then run repair")
    steps = [["git", "clone", "--filter=blob:none", "--no-checkout", "--branch", branch, clean_url, str(repo_directory)],
             ["git", "-C", str(repo_directory), "sparse-checkout", "set", "--cone", DEFAULT_SPARSE_FOLDER],
             ["git", "-C", str(repo_directory), "checkout", branch]]
    for command in steps:
        exit_code, output = common.run(command)
        if exit_code != 0:
            raise common.StepError("sync_clone_failed", f"{' '.join(command[:3])} failed: {output[-300:]}",
                                   "check that this machine can read the repository (git credentials), then run repair")
    return "created"


def ensure_gbrain_config(home_directory: Path, connection_url: str, embedding: dict) -> str:
    config_file = home_directory / ".gbrain" / "config.json"
    if config_file.exists():
        config_file.chmod(common.PRIVATE_FILE_MODE)
        return "kept"
    command = ["gbrain", "init", "--url", connection_url, "--non-interactive", "--no-git", "--skip-embed-check"]
    if embedding.get("embedding_model"):
        command += ["--embedding-model", str(embedding["embedding_model"])]
    if embedding.get("embedding_dimensions"):
        command += ["--embedding-dimensions", str(embedding["embedding_dimensions"])]
    exit_code, output = common.run(command, env=common.gbrain_environment(home_directory), secrets=[connection_url])
    if exit_code != 0:
        raise common.StepError("sync_gbrain_init_failed", f"gbrain init failed: {output[-400:]}",
                               "check the database tunnel and the writer role grants (repair re-applies grants on the server)")
    if config_file.exists():
        config_file.chmod(common.PRIVATE_FILE_MODE)
    return "initialized"


def ensure_source(home_directory: Path, project: str) -> str:
    environment = common.gbrain_environment(home_directory)
    repo_directory = home_directory / "repo"
    exit_code, output = common.run(["gbrain", "sources", "list", "--json"], env=environment)
    if exit_code != 0:
        raise common.StepError("sync_gbrain_unavailable", f"gbrain sources list failed: {output[-300:]}",
                               "check the database tunnel, then run repair")
    sources = _parse_sources(output)
    wanted_id = source_id(project)
    existing = next((source for source in sources if source.get("id") == wanted_id), None)
    if existing:
        existing_path = str(existing.get("local_path") or existing.get("path") or "")
        if existing_path and Path(existing_path).resolve() != repo_directory.resolve():
            raise common.StepError("source_id_taken", f"source {wanted_id} already reads {existing_path}",
                                   "nothing was changed: check that source by hand")
        return "kept"
    exit_code, output = common.run(["gbrain", "sources", "add", wanted_id, "--path", str(repo_directory)], env=environment)
    if exit_code != 0:
        raise common.StepError("sync_source_add_failed", f"gbrain sources add failed: {output[-300:]}",
                               "check the clone has committed files, then run repair")
    return "added"


def _parse_sources(output: str) -> list:
    start = output.find("[") if output.lstrip().startswith("[") else output.find("{")
    try:
        parsed = json.loads(output[start:]) if start >= 0 else []
    except ValueError:
        return []
    if isinstance(parsed, dict):
        parsed = parsed.get("sources") or []
    return [source for source in parsed if isinstance(source, dict)]


def render_sync_script(project: str, home_directory: Path, branch: str) -> str:
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    gbrain_path = shutil.which("gbrain", path=common.gbrain_environment()["PATH"])
    gbrain_directory = str(Path(gbrain_path).parent) if gbrain_path else str(common.home() / ".bun" / "bin")
    for placeholder, value in (("__GBRAIN_DIR__", gbrain_directory), ("__PROJECT__", project), ("__GBRAIN_HOME__", str(home_directory)),
                               ("__BRANCH__", branch), ("__SOURCE_ID__", source_id(project))):
        text = text.replace(placeholder, value)
    return text


def ensure_sync_script(project: str, home_directory: Path, branch: str) -> str:
    """Write sync.sh (700); a different existing script is kept as sync.sh.bak-<time> first"""
    script_path = home_directory / SYNC_SCRIPT_NAME
    wanted = render_sync_script(project, home_directory, branch)
    if script_path.exists():
        if script_path.read_text(encoding="utf-8", errors="replace") == wanted:
            script_path.chmod(SYNC_SCRIPT_MODE)
            return "kept"
        script_path.rename(script_path.with_name(f"{SYNC_SCRIPT_NAME}.bak-{common.compact_timestamp()}"))
        result = "replaced (old copy kept)"
    else:
        result = "created"
    script_path.write_text(wanted, encoding="utf-8")
    script_path.chmod(SYNC_SCRIPT_MODE)
    return result


def run_first_sync(home_directory: Path) -> dict:
    exit_code, output = common.run(["/bin/bash", str(home_directory / SYNC_SCRIPT_NAME)], env=common.gbrain_environment())
    return {"exit_code": exit_code, "tail": output[-400:]}


def describe(home_directory: Path) -> dict:
    """status: what exists on this machine for the project (no secret values)"""
    last_sync_file = home_directory / "last-sync"
    gaps_log = home_directory / "gaps.log"
    last_gaps = None
    if gaps_log.exists():
        lines = [line for line in gaps_log.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
        last_gaps = lines[-3:] if lines else None
    return {"path": str(home_directory), "exists": home_directory.exists(),
            "has_clone": (home_directory / "repo" / ".git").exists(),
            "has_gbrain_config": (home_directory / ".gbrain" / "config.json").exists(),
            "has_writer_secret": (home_directory / WRITER_SECRET_FILE).exists(),
            "has_sync_script": (home_directory / SYNC_SCRIPT_NAME).exists(),
            "last_sync": _read_last_sync(last_sync_file, gaps_log),
            "last_gaps": last_gaps}


def _read_last_sync(last_sync_file: Path, gaps_log: Path) -> str | None:
    """Time of the last sync run: the generated script's stamp, else the gaps log time (hand-written scripts)"""
    if last_sync_file.exists():
        return last_sync_file.read_text(encoding="utf-8").strip()
    if gaps_log.exists():
        import time
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(gaps_log.stat().st_mtime)) + " (gaps.log)"
    return None
