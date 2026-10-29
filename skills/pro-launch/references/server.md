# Connecting to the server — requests · DB · logs

> When to read: the first time you use `http` · `db` · `logs`, or when you record in `access` how to connect. Storing secret values: `credentials.md`.

**Where settings live and how to connect differ per project.** It may be Spring's `application.yml`,
or `.env` · `settings.py` · `ormconfig`. The DB may be local, reachable only over SSH,
or you may have to run commands inside a container. **The script does not guess. Read the code and decide yourself.**

Once you find out, **record it.** Later runs use that record.

## At a glance

```bash
{PYTHON} {SCRIPTS}/launch_cli.py http --url /api/health --expect-status 200
{PYTHON} {SCRIPTS}/launch_cli.py http --method POST --url /api/items --data '{"name":"x"}' \
  --header "Authorization: Bearer $TOKEN" --save create.json
{PYTHON} {SCRIPTS}/launch_cli.py access set --key base_url --json '{"url":"http://localhost:8080"}'
{PYTHON} {SCRIPTS}/launch_cli.py access show
{PYTHON} {SCRIPTS}/launch_cli.py access unset --key base_url
{PYTHON} {SCRIPTS}/launch_cli.py db --profile db --sql "select count(*) from item"
{PYTHON} {SCRIPTS}/launch_cli.py logs --tail 100 --grep ERROR
```

| code | Next action |
|---|---|
| `base_url_required` | You gave only a path and there is no `base_url`. Read the code and run `access set --key base_url` |
| `unexpected_status` | The status differs from `--expect-status`. Look at the response body and the server logs |
| `profile_not_found` · `no_log_command` | Check the recorded keys with `access show`; if missing, find out how to connect and run `access set` |
| `secret_in_value` | You wrote a secret into `access`. Move it with `cred set` and write only `{"cred":"<name>"}` |
| `db_timeout` · `logs_timeout` | Check that the connection path (direct · ssh · command) is right. Raising `--timeout` comes after that |

**Track record of recorded methods.** When `logs` · `db --profile` · `http` (given only a path, so it used `base_url`) run from an access record,
the tool writes the result to `access_status.json` itself: `verified` (date) on success, and
`last_fail` (date · code) on failure. It does not store the raw error text. Failures caused by the environment, such as a missing tool or environment variable, are not counted.
When you reuse a method that failed last time, the response carries `verify: true` and `verify_note`. Check the result, and
if it is wrong, read the code again and fix it with `access set` (fixing it clears that key's record). You can also see this in
`status` · `verify` from `access show`.

## Address

```bash
... access set --key base_url --json '{"url":"http://localhost:8080"}'
... http --url /api/health                       # a bare path is appended to base_url
... http --url https://api.example.com/v1/me --header "Authorization: Bearer $TOKEN"
```

| Argument | What |
|---|---|
| `--method` | Default GET |
| `--data` | Body. If it is JSON, `Content-Type` is added automatically. `@file` reads from a file |
| `--header` | `'Name: value'` — can repeat |
| `--save` | Save the response body. A bare name saves under `$RUN_DIR/http/` |
| `--expect-status` | `ok:false` if it differs |

- 4xx · 5xx are **results too.** It does not end with an exception; it returns the status, headers and body.
- **Request header values are not echoed back in the result.** Only the names are kept (otherwise Authorization would end up in the records).
- Walking a scenario step by step and judging it is `api` in `pro-agent-test`. This is for single calls.
- **Never send mutating requests to a production server.** Check where `base_url` points every time.

## DB

```bash
... access set --key db --json '{"how":"direct","engine":"postgres",
      "host":"...","port":5432,"db":"...","user":"...","password_env":"DB_PASSWORD"}'
DB_PASSWORD=... ... db --profile db --sql "select count(*) from ..."
```

> **Do not write secret values into `access`** (they are rejected). Save values with `cred set` and write only
> `"cred":"<name>"` in `access`. To read from an environment variable, write only where to read it from, with `password_env`.

| how | When | What to record |
|---|---|---|
| `direct` | Local DB · open port | `engine` · `host` · `port` · `db` · `user` |
| `ssh` | A DB reachable only from inside the server | The above + `ssh_host` · `ssh_user` |
| `command` | **Anything**, such as running inside a container | `command` (e.g. `docker exec -i pg psql -U u -d d -c`) |

`command` works with any DB. Use it even for engines that are not built in (postgres · mysql).
Values given directly as arguments win over the record. That is your way out when the record is stale.

## Logs

```bash
... access set --key logs --json '{"command":"ssh u@h \"docker logs --tail 200 app\""}'
... logs --tail 100 --grep ERROR
```

Logs can be anywhere: a container, a file, an admin screen or a log collector. Find out, record it, then run it.

## Good to know

- If the response is not JSON (an HTML error page, etc.), `text` holds only the beginning. If that does not reveal
  the cause, look at the server logs.
- Never write passwords or tokens into `access.json`, reports or commits. When the user gives you one, **save it with `cred set`** so you do not ask again
  (`launch.credentials` in `~/.projectops/config/config.json`, file mode 600).
- Reach a server with `ssh --cred <name> [--sudo] --command '…'` (a saved server), or without saving with `ssh --host H --port P --user U --password-env <var>|--key-path <key> --command '…'`. Passwords go only through stdin or environment variables, never the command line,
  and even if the server echoes them, they are masked as `***` in the output. Password logins use `sshpass` when installed, otherwise OpenSSH `SSH_ASKPASS` (one password attempt).
- Before calling a server, read `use_when` · `scope` · `notes` from `cred list` and stay inside them.
