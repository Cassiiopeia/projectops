---
name: pro-ssh
description: "Run commands on remote servers over SSH (AWS EC2, Synology NAS, any Linux host), by saved name or direct host/user/key. Use for 'check the server', 'look at logs', 'is the deploy live'."
version: 2.1.0
---

# SSH: remote server access

## When to use

- "Check the server", "show the logs", "connect to EC2", "connect to the Synology" (Korean: '서버 확인해줘', '로그 봐줘', 'EC2 접속해', '시놀로지 접속해')
- "Inspect prod", "check server status", "check whether the deploy is live", "do ~ on the server" (Korean: 'prod 검수해줘', '서버 상태 확인', '배포 됐는지 확인해줘', '서버에서 ~해줘')
- It connects by a saved server name, or without saving by passing host, port, account and password/key directly.

The connection runner is **`launch_cli.py ssh` from `pro-launch`** (#841). It works with a saved server (`--cred`) or **with connection details passed directly, without saving**.

Talk to the user in the user's language (or the configured `language` preference).

- Use it for: checking server status, logs and files, post-deploy server checks, "go into the server and do ~".
- **Do not use it for**: Synology DSM reverse proxy and domain setup → `pro-synology-expose` (in the optional projectops-extras plugin).

`{SCRIPTS}` is pro-launch's `scripts/` (how to find it: `../pro-launch/SKILL.md`). Calls are `{PYTHON} {SCRIPTS}/launch_cli.py …`.

## Workflow

### Phase 0: Which server

**Look in the project before asking the user.** Even when the user only gives a name, such as "the Iroom server DB", the answer is usually in the repo.

1. `access show`: if this repo has recorded how to connect (`ssh.<env>` · `db` · `logs`), use that first.
2. Find the target server in the project files (host · account · port · DB host/name):

   | Where | What |
   |---|---|
   | `application-*.yml` · `application-*.properties` (`prod` · `dev` …) | DB host and name in `spring.datasource.url`, external API addresses |
   | `.env*` · `docker-compose*.yml` | `DB_HOST` · `DB_NAME` · service names · ports |
   | `.github/workflows/*DEPLOY*` · `*CICD*` | `ssh` target host · account · port · deploy path · container name (if the value is `secrets.*`, you only know the name) |

   - **Never copy secret values (passwords, tokens, keys) into output or reports.** Even if you read them, give **only the location**, such as "`spring.datasource.password` in `application-prod.yml`".
   - Match the host you found against `host` in `cred list`. If a saved server matches, use it.
3. Look at saved servers (`kind: ssh`) with `cred list`. Use only those whose `use_when` fits the current task. If there is only one, select it automatically; if several, let the user pick by number.
   - **If `scope` is `ask-first`, confirm with the user before connecting** ("I'll connect to the ○○ server and check △△. Proceed?"). Never use it without approval.
4. If nothing was found above, or the user already gave connection details (for example "host 1.2.3.4 port 2222 user ubuntu key ~/k.pem"), **connect directly without saving**. Ask for missing details **one per message**:
   1) host (IP/domain) 2) port (suggest 22 if unknown) 3) account 4) auth method (password / PEM key) 5) password or key file path.
5. **When a connection succeeds through an unrecorded path, record it** so you do not search again next time.
   - How to connect (no secrets) goes in this repo: `access set --key ssh.<env> --json '{"host":…,"port":…,"user":…,"cred":"<saved name>","source":"<file where found>"}'`,
     and for a DB `access set --key db --json '{"how":"ssh",…}'` (`../pro-launch/references/server.md`). Putting a secret value in is rejected with `secret_in_value`.
   - For credentials such as passwords and keys, ask whether they may be saved, then `cred set` (below). If the user says it is one-off, do not save.

### Phase 1: Run commands

If the user did not choose a command, the agent picks one that fits the goal and runs it.

| Situation | Command |
|---|---|
| Saved server | `ssh --cred <server> --command '…'` (for password sudo, `--sudo` + `SUDO <command>`) |
| No saving · password | `ssh --host H --port P --user U --password-env VAR --command '…'` (**never put the password on the command line**: the permission classifier blocks it and it stays in logs) |
| No saving · PEM key | `ssh --host H --port P --user U --key-path ~/k.pem --command '…'` |
| Try a saved server with a different port or account | `ssh --cred <server> --port 2022 --command '…'` (values given directly win) |
| Save a new server | Ask whether it may be saved, and let the user type the password themselves: `! {PYTHON} {SCRIPTS}/launch_cli.py cred set --name <server> --prompt --json '{"kind":"ssh","host":…,"port":…,"user":…,"use_when":…,"scope":…}'` (do not put the password in `--json`). For key auth, put `key_path` in `--json` without `--prompt` |
| Import servers from the old `ssh` section | Check the list with `cred import-ssh --dry-run` → run without it (copies the values too) → after confirming connections, `--prune` |
| Logs · DB | `logs --cred …` · `db --cred …` (`../pro-launch/references/server.md`) |

- **Reading result codes**: `remote_exit_nonzero` means the connection worked and the remote command ended non-zero (no grep match, etc.; do not suspect the connection details). `auth_failed`, `connect_failed` and `host_key_*` are connection failures. On Windows (cmd) servers, commands joined with `&` keep only the last exit code, so call each step separately or wrap them in PowerShell.
- Passwords that appear in the output are masked as `***`. Password connections use `sshpass` when installed, otherwise OpenSSH `SSH_ASKPASS` (OpenSSH 8.4+, one password attempt so a wrong password cannot lock the account).
- When connecting to a saved server, `memory` in the response carries facts learned about that server (OS, docker path, containers, log locations). Record new findings with
  `learn --area server --scope machine --key server.<server>.<topic> --how '…' --result ok` (no accounts or secrets). Connections without saving are not remembered.
- Full credential rules: `../pro-launch/references/credentials.md`.

### Phase 2: Report results

Summarize the results for the user. If there are errors, give the cause and the fix together (`references/troubleshooting.md`).

## What remains in this skill

- `references/troubleshooting.md`: Synology docker absolute path, `wget`, Windows PowerShell, common pitfalls (per-server-type knowledge).
- `scripts/ssh_connect.py`: paramiko-based compatibility path. Use it only where `launch_cli` cannot be used (ssh older than OpenSSH 8.4 with no sshpass). It also takes the password from the `SSH_PASSWORD` environment variable.

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-ssh`.
Keys for this skill: the common `language`, `tone`, `rules` only.
Preferences change presentation only; approval gates, secret protection and `--dry-run` stay in force.
