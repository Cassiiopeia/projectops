"""`db` — SQL 을 실행한다."""
from __future__ import annotations

import os
import shutil
import subprocess

from common.access import load_access

import credentials

from pro_launch.registry import Command
from pro_launch.runtime.context import project_root, state_home
from pro_launch.runtime.creds import cred_name_for, load_cred
from pro_launch.runtime.output import out, set_area, use_access


#
# **접속 방법은 agent가 정한다.** 설정이 사는 곳도 붙는 길도 제각각이다.
# 여기서는 적어 둔 것을 받은 대로 실행만 한다.
_DB_CLIENTS = {"postgres": "psql", "postgresql": "psql", "mysql": "mysql", "mariadb": "mysql"}


def _db_argv(engine: str, db: dict, sql: str) -> tuple[list[str], dict]:
    """엔진에 맞는 명령과 환경변수. 비밀번호는 argv가 아니라 env로 — argv는 다른 프로세스에서 보인다."""
    exe = _DB_CLIENTS[engine]
    env = {}
    if exe == "psql":
        argv = [exe, "-tAF", "\t", "-c", sql]
        env = {"PGHOST": db.get("host") or "", "PGPORT": str(db.get("port") or ""),
               "PGDATABASE": db.get("name") or "", "PGUSER": db.get("user") or "",
               "PGPASSWORD": db.get("password") or ""}
    else:
        argv = [exe, "-N", "-B"]
        if db.get("host"):
            argv += ["-h", db["host"]]
        if db.get("port"):
            argv += ["-P", str(db["port"])]
        if db.get("user"):
            argv += ["-u", db["user"]]
        if db.get("name"):
            argv += [db["name"]]
        argv += ["-e", sql]
        if db.get("password"):
            env = {"MYSQL_PWD": db["password"]}
    return argv, env


def _shq(s: str) -> str:
    """원격 셸에 넘길 값을 감싼다."""
    return "'" + str(s).replace("'", """'"'"'""") + "'"


def _db_rows(text: str) -> list[list[str]]:
    """탭으로 나뉜 출력을 행 목록으로. 판정은 agent가 한다."""
    return [line.split("\t") for line in (text or "").splitlines() if line.strip()][:200]


def _proc_result(r, via: str, engine: str | None = None) -> int:
    return out({
        "ok": r.returncode == 0, "via": via, "engine": engine,
        "code": "ok" if r.returncode == 0 else "db_query_failed",
        "rows": _db_rows(r.stdout), "raw": r.stdout[:4000],
        "error": (r.stderr or "").strip()[:500] or None,
        "summary": "Query succeeded" if r.returncode == 0 else "Query failed",
        "hint": ("A key that connects without a password is required (BatchMode)"
                 if (via == "ssh" and r.returncode != 0) else None),
    })


def cmd_db(args) -> int:
    """SQL 한 줄을 실행한다. **어떻게 붙을지는 호출하는 쪽이 정한다.**

      --command  임의 명령 (docker exec 등). 가장 자유롭다
      --via ssh  원격에 들어가 그 안에서 클라이언트를 실행한다
      (기본)     여기서 직접 붙는다
    """
    set_area("server", project_root(args))
    sql = args.sql
    if not sql:
        return out({"ok": False, "code": "sql_required", "error": "--sql is required"})

    cred_env: dict = {}
    cred_entry = None
    # 적어 둔 접근 방법을 쓴다. 인자로 직접 준 값이 언제나 이긴다 — 기록이 낡았을 때의 탈출구.
    if args.profile:
        root = project_root(args)
        state_home(root)
        saved = load_access(root).get(args.profile)
        if not saved:
            return out({"ok": False, "code": "profile_not_found",
                        "error": f"No record named '{args.profile}'",
                        "next": f"access show --root {args.root}"})
        use_access(root, args.profile)
        if isinstance(saved, dict):
            for k in ("engine", "host", "port", "db", "user", "password",
                      "command", "ssh_host", "ssh_user", "ssh_port"):
                if getattr(args, k, None) in (None, "") and saved.get(k) is not None:
                    setattr(args, k, saved[k])
            if saved.get("how") in ("ssh", "direct") and args.via == "direct":
                args.via = saved["how"]
            if saved.get("append_sql"):
                args.append_sql = True
            cred_name = cred_name_for(args, saved)
            if cred_name and not getattr(args, "cred", None):
                args.cred = cred_name
            env_key = saved.get("password_env")
            if env_key and not args.password:
                args.password = os.environ.get(env_key)
                if not args.password:
                    return out({"ok": False, "code": "password_env_empty",
                                "error": f"Environment variable {env_key} is empty",
                                "hint": f"Set {env_key}=... and call again"})

    if getattr(args, "cred", None):
        cred_entry, err = load_cred(args.cred)
        if err:
            return out(err)
        # 저장된 값은 비어 있는 인자만 채운다 — 직접 준 인자가 이긴다
        for src, dst in (("host", "host"), ("port", "port"), ("db", "db"), ("user", "user"),
                         ("password", "password"), ("engine", "engine")):
            if getattr(args, dst, None) in (None, "") and cred_entry.get(src) not in (None, ""):
                setattr(args, dst, cred_entry[src])
        cred_env = credentials.env_for(cred_entry)

    try:
        if args.command:
            argv = (["bash", "-lc", f"{args.command} {_shq(sql)}"] if args.append_sql
                    else ["bash", "-lc", args.command])
            stdin = None if args.append_sql else sql
            r = subprocess.run(argv, input=stdin, capture_output=True, text=True,
                               timeout=args.timeout, env=dict(os.environ, **cred_env))
            return _proc_result(r, "command")

        engine = (args.engine or "").lower()
        if engine not in _DB_CLIENTS:
            return out({"ok": False, "code": "unsupported_engine",
                        "error": f"engine '{args.engine}' is not supported",
                        "supported": sorted(set(_DB_CLIENTS)),
                        "hint": "Any DB works if you give the command to run with --command"})
        db = {"host": args.host, "port": args.port, "name": args.db, "user": args.user,
              "password": args.password or os.environ.get("DB_PASSWORD")}
        argv, env = _db_argv(engine, db, sql)

        if args.via == "ssh":
            if not args.ssh_host:
                return out({"ok": False, "code": "ssh_host_required",
                            "error": "--ssh-host is required"})
            remote = " ".join(f"{k}={_shq(v)}" for k, v in env.items() if v)
            remote += " " + " ".join(_shq(a) for a in argv)
            dest = f"{args.ssh_user}@{args.ssh_host}" if args.ssh_user else args.ssh_host
            ssh = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
            if args.ssh_port:
                ssh += ["-p", str(args.ssh_port)]
            r = subprocess.run(ssh + [dest, remote], capture_output=True, text=True,
                               timeout=args.timeout)
            return _proc_result(r, "ssh", engine)

        exe = shutil.which(argv[0])
        if not exe:
            return out({"ok": False, "code": "client_missing",
                        "error": f"{argv[0]} is not installed",
                        "install": ("brew install libpq" if argv[0] == "psql"
                                    else "brew install mysql-client"),
                        "hint": "Run it on the server with --via ssh, or give the command directly with --command"})
        r = subprocess.run([exe] + argv[1:], env=dict(os.environ, **env),
                           capture_output=True, text=True, timeout=args.timeout)
        return _proc_result(r, "direct", engine)
    except subprocess.TimeoutExpired:
        return out({"ok": False, "code": "db_timeout", "error": f"No response ({args.timeout}s)"})


def configure_db(p) -> None:
    p.add_argument("--sql", required=True)
    p.add_argument("--engine", default=None, help="postgres · mysql (not needed with --command)")
    p.add_argument("--host", default=None)
    p.add_argument("--port", default=None)
    p.add_argument("--db", default=None, help="Database name")
    p.add_argument("--user", default=None)
    p.add_argument("--password", default=None, help="Defaults to the DB_PASSWORD environment variable (recommended)")
    p.add_argument("--via", choices=["direct", "ssh"], default="direct")
    p.add_argument("--ssh-host", dest="ssh_host", default=None)
    p.add_argument("--ssh-user", dest="ssh_user", default=None)
    p.add_argument("--ssh-port", dest="ssh_port", default=None)
    p.add_argument("--command", default=None,
                   help="Give the whole connection command. e.g. \"docker exec -i pg psql -U root -d appdb -c\"")
    p.add_argument("--append-sql", dest="append_sql", action="store_true",
                   help="Append the SQL as an argument after --command (default: standard input)")
    p.add_argument("--profile", default=None, help="Use a record saved with access (e.g. db)")
    p.add_argument("--cred", default=None, help="Fill host, user and password from a saved credential (cred list)")
    p.add_argument("--root", default=".")
    p.add_argument("--timeout", type=int, default=40)


COMMANDS = [
    Command(name="db", help="Run SQL (the caller decides how to connect)", run=cmd_db,
            configure=configure_db),
]
