# Harness: a guide folder for a site or workflow you repeat

> When to read: a response carried `harness`, you are about to repeat work on a site you have worked on before, or a workflow has repeated and deserves a guide.

A harness is **one folder per site or workflow**: a README the agent reads and follows while making its own decisions, plus optional helper scripts.
It is not a rigid script. When the screen changed or a result looks wrong, check with `web text` · `web find` and update the README.
Adding a new site means adding a folder. No code changes.

| | `learn` | `journal` | `harness` |
|---|---|---|---|
| Holds | One-line conclusion: "this method worked" | Context of one task: what, why, order, result | The guide for a repeating workflow + helper scripts |
| Shape | key · how (200 chars) | free text (1,500 chars, 40 entries per repo) | a folder: `README.md` · `harness.json` · scripts |
| Comes back | `memory` in area responses (once a day) | `journal` in area responses (once a day) | `harness` in responses aimed at a matching URL, host, app or window (once a day per harness) |

## Where it lives

| Scope | Folder | Use |
|---|---|---|
| machine (default) | `~/.projectops/launch/_machine/harness/<name>/` | Sites and workflows used from any repo on this computer |
| repo | `~/.projectops/launch/<owner__repo>/harness/<name>/` | Only for this repo. Wins over a machine harness with the same name |

`PROJECTOPS_HOME` replaces `~/.projectops` (test isolation). Repo scope is not available when the repo cannot be determined or the root is a scratch folder.
**Keep helper scripts in the harness folder**, not in a random project or scratch folder, so the next session finds them.

## Folder contents

```
<name>/
  README.md      the guide (required to be useful; listed even without harness.json)
  harness.json   optional: description and auto-surface rules
  *.py · *.sh …  optional helpers the README refers to
```

```json
{"description": "Monthly Sparrow vulnerability loop",
 "match": {"hosts": ["10.206.10.195"], "urls": ["https://10.206.10.195:10880/*"]},
 "areas": ["web"]}
```

```json
{"description": "Sign-in setup for the example app",
 "match": {"apps": ["com.example.app", "com.example.ios"], "windows": ["Example Setup*"]}}
```

- Without `harness.json`, the folder still shows in `harness list` · `show` (description = the README's first heading), but it never auto-surfaces.
- README sections (`harness new` writes this skeleton): summary · goal · loop · decision points (human check) · access · step notes · API notes · when stuck · files.
  A `## Summary` section (or its Korean equivalent from the `--lang ko` skeleton) is what responses show as `excerpt`; without one, the paragraph under the title is used (8 lines, 600 characters at most).
- **Never write passwords or tokens in a harness.** Accounts go in `cred`. `harness new` refuses secret-looking values in the description, hosts and URLs.

## Matching

| Rule | Matches |
|---|---|
| `match.urls` | URL patterns with `*`. Scheme and host are compared case-insensitively. A pattern with no path covers the whole site (`https://h:8443` = `https://h:8443/*`) |
| `match.hosts` | Host names or IPs, `*` allowed (`*.corp.example`). `host:port` also requires that port when the URL has one |
| host-only commands (`ssh`) | `match.hosts`, and also the host part of `match.urls`, so a web harness shows up when you ssh into the same server |
| `match.apps` | Android package names or iOS bundle IDs, `*` allowed (`com.example.*`), case-insensitive |
| `match.windows` | Desktop window titles or program names, `*` allowed (`Setup*`), case-insensitive. A program name also matches without `.exe` (`setup` = `setup.exe`) |
| `areas` | If set, only commands of those areas (`web` · `server` · `app` · `desktop` · …). Empty = all. `app` covers `ios` and `android`, and `ios` or `android` also match `app` commands |

Which commands carry it: `web open` · `web goto` (the `--url`), every other `web` action (the current page URL), `http` (the full URL), `ssh` (the host, saved or `--host`),
`app` actions (`--pkg` or `$PKG`; `launch` · `terminate` · `relaunch` · `permission` · `push` also use the device bind package), `desktop` actions that pick a window (its title and program name).
`app` actions with no `--pkg`, `$PKG` or package-using step do not guess the app, so nothing is matched.

## In responses

- `harness`: a list (at most 2) of `name` · `scope` · `description` · `readme` · `path` · `matched_by` · `excerpt` · `files`, plus `harness_note`.
- **Once a day per harness** (seen file `harness_seen.json` next to the journal's). **A failed response (`ok: false`) shows it but does not count as seen**, so the next successful response shows it again.
- `harness` · `journal` · `memory` survive `--brief` and `--fields` (projectops#1023: `--brief` once dropped the journal while still counting it as seen).

## Commands

```bash
{PYTHON} {SCRIPTS}/launch_cli.py harness list                                   # all harnesses (repo first) + the folders searched
{PYTHON} {SCRIPTS}/launch_cli.py harness show sparrow                           # README text + files
{PYTHON} {SCRIPTS}/launch_cli.py harness match --url https://10.206.10.195:10880/projects   # or --host 10.206.10.195 [--area web]
{PYTHON} {SCRIPTS}/launch_cli.py harness new sparrow --description "Monthly Sparrow vulnerability loop" \
    --url "https://10.206.10.195:10880/*" --host 10.206.10.195 --area web    # --scope repo · --lang ko|en (repeat --url · --host · --area)
{PYTHON} {SCRIPTS}/launch_cli.py harness new example-app --description "Sign-in setup for the example app" \
    --app com.example.app --app com.example.ios --area app                     # desktop: --window "Example Setup*" --area desktop
{PYTHON} {SCRIPTS}/launch_cli.py harness match --app com.example.app            # or --window "Example Setup"
```

- `harness new` fails with `exists` if the name is taken (in either scope); edit that folder instead.
- Without `--host` · `--url` · `--app` · `--window`, the harness is listed only and never auto-surfaces.
- After a task that repeats, ask the user whether to write it down; keep the context in `journal` and the reusable steps in the harness README.
