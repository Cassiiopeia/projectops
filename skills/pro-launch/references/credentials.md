# Credentials · sudo on this Mac · remote ssh

> When to read: before touching a server, DB, registry or login screen; when the user gives new connection details; when you need `sudo` on this Mac.

Once saved, the next run does not ask again.
This works the same way `pro-ssh` and `pro-github` keep servers and PATs in `~/.projectops/config/config.json`.
Values are saved **under a name** in `launch.credentials` (the file is mode 600). In list and show output, values are masked as `<저장됨>` ("saved").

```bash
{PYTHON} {SCRIPTS}/launch_cli.py cred list                     # once at the start of a task — what can you use
{PYTHON} {SCRIPTS}/launch_cli.py cred show --name synology     # values are masked (use --reveal only when truly needed)
{PYTHON} {SCRIPTS}/launch_cli.py cred show synology            # the name can also be a positional argument (show · set · unset)
{PYTHON} {SCRIPTS}/launch_cli.py cred set --name synology --json '{"kind":"ssh","host":"h","port":22,"user":"u",
  "use_when":"server deploy QA","scope":"test-only","notes":"production containers run here, so use only the pops-qa- prefix"}'
{PYTHON} {SCRIPTS}/launch_cli.py cred unset --name synology
{PYTHON} {SCRIPTS}/launch_cli.py cred policy get --name google-dev                 # interstitial login screen policy (account > global > ask)
{PYTHON} {SCRIPTS}/launch_cli.py cred policy set --name google-dev --key trust_device --value always
{PYTHON} {SCRIPTS}/launch_cli.py cred policy set --key skip_nags --value always    # without --name, the default for all sites
{PYTHON} {SCRIPTS}/launch_cli.py ssh --cred synology --sudo --command 'SUDO docker ps'   # password sudo works too
{PYTHON} {SCRIPTS}/launch_cli.py logs --cred synology --command 'sshpass -e ssh -p $CRED_PORT $CRED_USER@$CRED_HOST "docker logs --tail 100 app"'
{PYTHON} {SCRIPTS}/launch_cli.py db --cred pg --sql "select 1"   # fills in host · user · password
{PYTHON} {SCRIPTS}/launch_cli.py http --cred api --url /me        # a token becomes Authorization: Bearer
```

`cred set` merges into the existing entry. To replace it entirely, use `--replace`. Even `--replace` keeps the saved `login_policy`. Putting `login_policy` in `--json` is rejected with `use_cred_policy`; change the policy only with `cred policy set|unset`.

| Field | Meaning |
|---|---|
| `kind` | `ssh` · `dockerhub` · `db` · `http` · `github-org` · `login` · `local` · `other` |
| `ssh_server` | (deprecated, for compatibility) A server name from the old `ssh` section. Do not use it for new entries; move the values into cred with `cred import-ssh`. Keep server details and passwords **in cred only** |
| `use_when` | **When this credential may be used** (the justification). Write the scope the user allowed, word for word |
| Login account | `kind: login` + `provider` (google · apple · naver · kakao · custom) · `surface` · `app` · `account` · `password` · `two_factor` — social and app logins and developer console logins. Enter them on screen with `web type --cred` · `app type --cred`. Field details: "Saving login details" in `web.md` |
| `login_policy` | The interstitial screen policy for a login account (`trust_device` · `keep_signed_in` · `skip_nags` = `ask` · `always` · `never`). Change it **only with `cred policy set|unset`**. Handling rules: "Interstitial login screens" in `web.md` |
| sudo on this Mac | `kind: local` + `sudo_password` — when you need admin rights **on this Mac** (`sudo installer -pkg …`, etc.). Use it with `local sudo --cred <name> -- <command>` (below) |
| `scope` | Allowed scope: `test-only` · `test-ok` · `readonly` … |
| `notes` | What to keep in mind: naming rules, port ranges, production services on the server, etc. |

## Agent decision rules

- Before touching a server, DB or registry, check `cred list` and use **only entries whose `use_when` fits what you are about to do**.
  If none fits, do not guess and use another one; ask the user.
- **Before saying "this needs a login, so the user has to do it", check `cred list` first.** Developer console (Apple
  Developer, etc.) and social login accounts may be saved as `kind: login`. If `use_when` fits, do not say "I can't"; offer
  "I'll try with the saved account". For actions that **change external state**, such as certificates, profiles or Secrets, **say what will change
  and get approval first**. Ask separately only for the steps only a person can do, such as 2FA.
- Read `scope` and `notes` and stay inside them (for example: a test name prefix; delete only what you created).
- When the user gives new connection details, **ask once whether you may save them**. If allowed, save them with `cred set` and fill `use_when` · `scope` · `notes`
  with the user's own words. The goal is not to ask again next time. If refused, use them for this run only and do not save them.
  (Within a scope the user approved in advance, such as "just save it", save without asking.)
- If saved details **look wrong or changed** (login failure · connection refused), ask the user before retrying or overwriting. Never auto-retry logins.
- Record the **approach that worked** for connecting or logging in (which browser mode, which order) with `learn`, without the values. The next `recall` brings it back (`memory.md`).
- Never copy values into results, reports, issues or commits. Use `cred show --reveal` only when truly needed.
- Do not write secrets in command strings; use the `$CRED_HOST` · `$CRED_USER` · `$CRED_PASSWORD` · `$CRED_TOKEN` · `$SSHPASS` environment variables.
  If a value appears in the output, it is masked as `***`.
- Do not write secrets in `access.json` (a value there is rejected with `secret_in_value`). In `access`, write only `{"cred":"<name>"}` (`server.md`).

## Remote ssh

- Reach a server with `ssh --cred <name> [--sudo] --command '…'` (a saved server), or **without saving** with `ssh --host H --port P --user U --password-env <var>|--key-path <key> --command '…'`. Values given directly take precedence over saved values and are not saved. With `--sudo`, you can use `SUDO <command>` inside the remote command.
- Passwords go only through stdin or environment variables, never the command line. Even if the server echoes them, they are masked as `***` in the output.
- Password logins need `sshpass` (`sshpass_missing` if absent). Output is truncated at `--max-output` characters.
- **Server memory (#841)**: the `memory` in an `ssh` response carries only that server's memory (`server.<credential name>.*`). After the first successful connection,
  the CLI checks the OS (`uname -s`) and the absolute Synology docker path and saves them at this-computer scope (skipped on Windows).
  Record what you find out yourself, such as container names or log locations, with `learn --area server --scope machine --key server.<server>.<topic>` (no accounts or secrets).
- **Keep server details in cred only.** If an old `ssh` section exists, list it with `cred import-ssh --dry-run` (secrets are masked).
  Running it without `--dry-run` imports the host · user · password values too. After you confirm the connection works, call it again with `--prune`
  to delete the imported servers from the old section (backed up to `config.json.bak-ssh-prune` first, mode 600). Servers whose names do not fit the cred format (letters, digits, `._-`)
  cannot be imported; save them yourself with `cred set` under an English name. `--ref` only creates a reference (the password stays in two places).

## sudo password on this Mac (#784)

When a task on the local Mac needs admin rights (for example `sudo installer -pkg … -target /`), **do not stop with "I can't enter the password"**. Look for a saved credential first.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py cred list                      # is there one with kind local
{PYTHON} {SCRIPTS}/launch_cli.py local sudo --cred mac -- installer -pkg /path/x.pkg -target /
```

- **The user does the first registration directly in the terminal.** The input is not shown on screen, and the password never enters the chat or session records.
  `! {PYTHON} {SCRIPTS}/launch_cli.py cred set --name mac --prompt` (the `!` prefix in Claude Code). If `!` cannot get a TTY,
  type the same command in a separate terminal window. Pipes and chat are not accepted (rejected with `no_tty`).
- The password goes only to `sudo -S` on stdin. It does not stay in the command line, responses or logs, and the same string in the output is masked as `***`.
- Use only `kind: local`. Do not try sudo on this Mac with a server ssh password (`cred_not_local`).
- **These commands change the system.** Before running one, say in one line what the command is. Saving once does not mean running any command; stay within `use_when`.
- It is stored as plain text in a local file (`config.json`, mode 600). This follows the user's local-only policy, and the user knows that a Mac login password is more sensitive than a server key.
- ⚠️ **Claude Code's permission classifier may refuse a "sudo with a saved password" call.** This skill cannot bypass that and does not change permission settings.
  If refused, report that and give the user the one-line command to type themselves.

## Failure code → next action

| code | Next action |
|---|---|
| `cred_required` · `name_required` | Pick a name with `cred list`. If none fits, ask the user |
| `cred_field_missing` | That credential lacks the field. Check the existing fields with `cred show` |
| `cred_not_local` | Only `kind: local` credentials work with `local sudo` |
| `no_tty` | The user types `cred set --prompt` themselves, with the `!` prefix or in a separate terminal |
| `sudo_failed` · `auth_failed` | Do not retry; ask the user whether the value changed |
| `sshpass_missing` | Offer to install it, for example with `brew install sshpass` |
| `remote_exit_nonzero` | Connection and authentication succeeded, and the remote command ended non-zero. That can be normal, such as grep finding nothing. Judge by the output and do not suspect the connection details |
| `connect_failed` · `host_key_unknown` · `host_key_changed` | The connection itself failed. `host_key_changed` may mean the server changed, so do not delete known_hosts on your own; tell the user |
