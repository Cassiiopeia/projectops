# What worked on this computer · tokens · storage locations

> When to read: the first time you use `recall`·`learn`·`forget`, when you need to know where state files live, or when captures eat a lot of tokens.

## Remember what worked (it gets more accurate with use)

> Shared principles: [`../../references/memory-principles.md`](../../references/memory-principles.md)

What works differs per person and per computer (iOS only where Maestro is installed, Google login only with `--headed` on some machines, and so on).
To avoid repeating the same failure and to save tokens, **write down what worked in the home folder.**

**Reading is automatic (#833).** Responses from `app` · `web` · `http` · `db` · `logs` carry memories for that area in `memory`
(once a day per repo and area, at most 3, and entries where failures clearly outnumber successes are left out). You do not need to call `recall` separately —
an agent that "does not know what it does not know" never thought to look, so memories were never read back (measured).

| What comes in the response | What to do |
|---|---|
| `memory` | **Read it first** and try that method first. After using it, record the result with `learn --key <that key> --result ok\|fail` |
| `learn_hint` | You just got past a failure (N times) with a different method. If you will use that method again, save it with `learn` |
| `related` in a `learn` result | A similar memory already exists. If it is the same knowledge, `forget` the new entry and `learn --scope machine` again under that key |
| `promoted_from` | The same knowledge existed in another repo, so it was merged into the machine scope |

- **Verified successes are recorded by the CLI itself.** When `app tap/swipe/tree` succeeds, "this computer is driven this way" is
  added to the machine scope once a day. **Failures and missing tools are not recorded automatically** — they change with the environment and become junk.
- `verify:true` means failures outnumber successes or it is older than 90 days, so **check it once** before relying on it. `forget` anything learned wrongly.
- Clean up scattered memories (the same thing in several repos, the wrong bucket) with `tidy` — it merges only the clear-cut cases automatically.
- **Do not delete stale memories; mark them as superseded**: `learn --supersede <key> --by kb:<id>|feature:<command>` (or `forget --by`). `recall` returns superseded entries last, with `verify: true`. New entries store the `plugin_version` at the time they were written.
- **Disk usage · fake buckets**: `tidy --buckets` **only reports** per-bucket size, last use, whether a bucket is fake (scratch), orphaned browser profiles, and `~/.maestro/tests`. It deletes only with `--apply [--days N]`,
  and keeps the browser profile of a real repo (`owner__repo`) as `keep:real_repo_profile` even if unused for a long time (deleting it would lose the login). It never touches a profile whose browser is still running.
- If `--root` is a folder with neither git nor project files (a scratch path), it uses a `_scratch/<folder>-<hash>` bucket and does not record it as a recent root (`root_scratch: true`).
- `recall --platform` is an alias of `--area`.

**What not to save** (following Hermes Agent's do-not-store list): environment-dependent failures such as "not installed" or "not authenticated",
negative claims like "X does not work", unresolved trial and error, one-off stories, secret values, and host-mouse methods.

**Scope**: Methods unrelated to any repo (login method, tool usage) go in `--scope machine`. Only things tied to that repo's app or profile
stay in the default (repo) scope. If the same knowledge exists in another repo, `learn` promotes it to the machine scope on its own.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py recall --area ios                 # --area ios|android|web|server · --scope both|repo|machine · --limit
{PYTHON} {SCRIPTS}/launch_cli.py learn --area ios --key ios.tap \
    --how "tap widget text with client/tool/e2e_shot.sh (Maestro)" --result ok
# If it applies to the whole computer, use --scope machine (the default is this repo)
{PYTHON} {SCRIPTS}/launch_cli.py forget --key ios.tap --area ios
{PYTHON} {SCRIPTS}/launch_cli.py tidy                              # clean up scattered memories
{PYTHON} {SCRIPTS}/launch_cli.py tidy --buckets [--apply --days 7]   # report state-folder disk usage (deletes only with --apply)
{PYTHON} {SCRIPTS}/launch_cli.py recall --match swipe               # only entries whose key, method, or note contains the word
# If the story is long, keep how to a one-line conclusion and put the long text in --detail (or --detail-file) → notes/<key>.md; recall returns it as detail_path
{PYTHON} {SCRIPTS}/launch_cli.py learn --area android --key android.swipe --result ok \
    --how "swipe with app swipe. Pick the row y with app shot first" --detail "An ad banner moved y from 87% to 80%, so the wrong card was swiped ..."
{PYTHON} {SCRIPTS}/launch_cli.py session-check                      # when you finish: areas that got unstuck but were not learned · Maestro runs outside pro-launch
```

- **Safety rules outrank memory.** Methods that tap coordinates with the host mouse (`cliclick`, etc.) are blocked from both saving and recall.
- Secret **values** such as passwords, tokens, and emails are refused (`secret_detected` + a masked `matched_span`). Words alone do not block —
  a selector like `#password_text_field` is saved (#882).
- `how` has a 200-character limit. Longer input is **not truncated**; it is refused with `too_long` (length · limit) — split it out with `--detail` (#863).
- **App screens, coordinates, and pitfalls do not belong here** — `pro-agent-test`'s `note` handles them. This is for **tools and methods** only.
- Keep only the conclusion in `how`; put why it got stuck and how it was solved in the `--detail` note. Cases the team needs to see go in repo docs (`CLAUDE.md`, etc.).
- If you call `adb`·Maestro·`simctl` directly, responses carry no `memory` — at the start of the task, check `doctor` (memory count per area) or `recall --area <area>`.
- `outside_launch.maestro_runs` in `session-check`: the number of `~/.maestro/tests/<timestamp>/` folders from the last 24 hours whose time does not match a window pro-launch started (`launch/maestro_runs.json`). It looks only at folder names and times, never the contents (they log secret input). `adb`·`simctl` leave no trace, so they are not counted.
- Accounts go in `cred` (`credentials.md`); methods go in `learn`.

## Official knowledge vs my memory (#889)

| | Official troubleshooting | My memory (`learn`) |
|---|---|---|
| Content | Verified symptom · cause · fix | Methods that worked on this computer · this repo |
| Location | Inside the skill, `troubleshooting/<area>/<id>.json` (list: `troubleshooting.md`) | `~/.projectops/launch/` |
| Written by | Maintainers, via PR | The agent, automatically |
| Included in responses | `known_fix` in failure responses (at most 2, every time) | `memory` in area command responses (once a day) |

- On failure, try `known_fix` first; see the full entry with `kb show <id>`. If nothing came in the response, use `kb search "<error message>" --code <code>` · `kb list --area web`.
- `kb propose` turns my memories that worked many times (ok 3 or more, fail < ok) into drafts of official entries (secret values are filtered out, nothing is written to files).
  Fill in the todo fields and, **after the user confirms**, submit it as an issue or PR. It never merges into the official set automatically.

```bash
# the search text is the literal error message the CLI emits (browser_start_failed)
{PYTHON} {SCRIPTS}/launch_cli.py kb search "브라우저가 뜨지 않았습니다" --code browser_start_failed
{PYTHON} {SCRIPTS}/launch_cli.py kb show browser-start-stale-process-or-lock
{PYTHON} {SCRIPTS}/launch_cli.py kb list --area ios
{PYTHON} {SCRIPTS}/launch_cli.py kb propose --key web.google-login     # → {"drafts":[{"path":..., "draft":{...}, "todo":[...]}]}
```

## Write down what you did (work journal)

`learn` is for a one-line conclusion: "this method worked". Write the **context of one task** (what you did and why, in what order,
what you based decisions on, how it turned out, what will be confusing next time) freely in `journal`. There is no format.

**When to write**
- When you finish a task and close the window, the response carries a `journal_hint`. If the task is likely to repeat, **first ask the user,
  in the user's language, "Should I record this task?"** and write it only if they agree.
- If the user says "record this" first, write it right away without asking.

**When it is read**: When you open the same area (web·app·server) again, the response carries `journal` (latest 2 entries, once a day).
**Use it for reference only** — follow its order and decision criteria, but actions that change things (exclude · delete · submit, etc.) need user confirmation.
If what is written is outdated or the screen has changed, do not follow it blindly; append what changed with `--add`.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py journal --add-file "$NOTE" --title "sparrow false-positive exclusion request" --area web --site 10.206.10.195
{PYTHON} {SCRIPTS}/launch_cli.py journal --site sparrow       # search (newest first)
{PYTHON} {SCRIPTS}/launch_cli.py journal --forget "sparrow false-positive exclusion request"
```

- Pass long text or line breaks with `--add-file` (a UTF-8 file). Up to 1,500 characters per entry and 40 entries per repo.
- **Passwords and tokens are refused.** Keep accounts in `cred`.
- Location: `~/.projectops/launch/<owner__repo>/journal.jsonl`.

## Save tokens

- Reading screen images is the most expensive thing. **If text can confirm it (`assert` · logs · `app tree` · E2E assertVisible), do not read the screenshot.**
- Once you build an E2E flow, save its path with `learn` so you do not write it again.
- Use the default downscaled capture (1200px long side, WebP); use the original only when truly needed, such as for pixel comparison.
- Shrink with `shrink` — WebP reduces file size and resolution reduces session tokens. You need both.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py shrink "$SHOT_DIR"/*.png           # long side 1200 + WebP (--max-side · --quality · --keep-format)
```

## Storage locations

| Location | Contents |
|---|---|
| `~/.projectops/launch/<owner__repo>/` | devices.json · browser.json · access.json (**no secrets**) · access_status.json (access-method scores) · knowledge.json · `.browser-profile/` · `shots/` |
| `~/.projectops/config/config.json` → `launch.credentials` | **Credentials** (with values, file mode 600). The same file as `pro-ssh`·`pro-github` |
| `~/.projectops/launch/_machine/` | knowledge.json — methods that apply to the whole computer. State is also kept here when the repo cannot be determined (below) |
| `~/.projectops/launch/.venv` | Playwright · Pillow (uses the old `agent-test/.venv` if it exists) |

If the `PROJECTOPS_HOME` environment variable is set, it is used instead of `~/.projectops` (for test isolation). The venv is an installation, so
if it is not there, the one in the real home is used.

**Root lookup order (#885)** — `--root` > `$PROJECT_ROOT` > working folder (if it is git) > most recently used root (`_machine/recent_roots.json`) > working folder.
If the recent root was used, the response carries `root_source: "last_used"` and `root_note`. If it fails because it is outside a repo (`browser_not_open`, etc.),
it returns `root_candidates` (those with a live browser first) and a `retry` command you can copy as is.

**When the repo cannot be determined** — if it was called from a skill or plugin cache folder (`/skills/pro-` · `/plugins/cache/` in the path) and there is no git remote,
it does not treat the folder name (`scripts`, etc.) as the repo. It uses `$PROJECT_ROOT` if set; otherwise it writes state to
`_machine/` and adds `root_unknown: true` to the response, with a `next` that says to call again with `--root <project>`.
Repo-scope memory is not used in this case.

State used to be mixed into `~/.projectops/agent-test/`. On the first call, the launch part is moved and
reported as `migrated` in the result. From the second call on, nothing happens. If a browser is running, browser-related
files are moved after it closes.
