# Walk a server (target: server)

> When to read: when Phase 0 sets the target to `server`, and when you record how to connect in `access`.

This document is for when `pro-agent-test` **walks an API without a screen**. You do not need it when walking an app
(`target-app.md`) or web (`target-web.md`).

Repos with only a backend are verified with this target too. This is different from **cross-checking** the server
while walking an app or web — that is done with `expect_server` on any target.

## Walking

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py api --name {scenario} --root {ROOT}
#   --base-url http://localhost:8080   # when neither the scenario nor access has it
#   --timeout 30
```

Unlike app and web, **one call walks the whole scenario.** There is no screen to judge, so there is no reason
to split it, and token chaining stays simple when it finishes inside one process.

If it stops, it returns results up to that step. Later steps do not run — if you keep walking after an earlier
step failed, the real cause is buried under later failures.

## Scenario — the key is passing values along

Without login, every following request is a 401. **Extract a value from an earlier response and insert it into the next request.**

```json
{
  "target": "server",
  "base_url": "http://localhost:8080",
  "steps": [
    {
      "screen": "-",
      "do": "POST /api/auth/login {\"id\": \"test\", \"pw\": \"...\"}",
      "expect_status": 200,
      "save": { "token": "$.accessToken" }
    },
    {
      "screen": "-",
      "do": "POST /api/routines {\"title\": \"Morning routine\"}",
      "auth": "{token}",
      "expect_status": 201,
      "expect_json": "$.id is not empty",
      "expect_server": "select count(*) from routine where title = 'Morning routine'"
    }
  ]
}
```

| Field | What |
|---|---|
| `do` | `{method} {path} {body JSON}` — the body is optional |
| `auth` | Value for `Authorization: Bearer`. Use a value saved earlier, like `{token}` |
| `save` | Values taken from the response and passed to the next step. Reads paths like `$.a.b[0]` |
| `expect_status` | Expected status code. **Judged automatically** |
| `expect_json` | A human-readable description. The real response is saved alongside, so the agent compares it by eye |
| `expect_server` | DB cross-check query. The actual query runs through the `db` subcommand |

If there is no value for a `{name}` slot, it **stops there and tells you.** Silently filling it with an empty string
would only get a 401 and hide the cause.

## What not to miss on a backend — in order

With no screen, **state change** is the basis for judgment. But **a 201 response does not mean the row is in the DB.**
So always look at three places together.

```
response (status · body)  +  storage (DB · cache · files)  +  traces (logs · external calls)
```

| Rank | What | Why this order |
|---|---|---|
| 1 | **Permission boundaries** | Hiding a button in the frontend does not close the API. And **almost nobody walks it** |
| 2 | **State cross-check** | The response and what was actually stored disagree. Common with transaction rollbacks and async work |
| 3 | **Observability** | Can you trace it when it fails |
| 4 | **Failure distinction** | Does it distinguish 400/401/403/404/409. If everything is 500, the client cannot react |
| 5 | **Idempotency · duplicates** | The same request twice. Network retries make this happen often |
| 6 | **Concurrency** | The same resource at the same time. Breaks with stock, points and seats |
| 7 | **Cleanup** | Data left by the test. If not removed, the second run breaks |

### 1. How to break permissions

**The most important spot and the least walked one.**

First check in the code **whether resources have owners** — `userId` comparison · `@PreAuthorize` ·
`where owner_id = ?` in queries · middleware. If they do, **walk with two accounts.**

| What to walk | Expected | If you get 200 |
|---|---|---|
| Create with A, **read with B** | 403 or 404 | **Critical** — someone else's data is visible |
| Create with A, **update/delete with B** | 403 | **Critical** — someone else's data changes |
| Request without a token | 401 | The endpoint has no authentication |
| Request with a withdrawn account's token | 401 | **Often missed** — the token survives withdrawal |
| Admin API with a regular account | 403 | **Critical** |

Hiding with `404` is also a valid design (it hides the very existence of the resource). **403 or 404 does not matter;
a 200 is the defect.**

### 2. How to cross-check state

Do not trust the response alone.

```bash
... api --name {scenario} --root {ROOT}      # walk
{PYTHON} {LAUNCH}/launch_cli.py db --profile db --sql "select ..."   # check it really went in
```

| Where it diverges | How it shows |
|---|---|
| 201 but not in the DB | The transaction rolled back after the response was built |
| In the DB but not returned by reads | Stale cache, or mismatched index or condition |
| Deleted but still there | Soft delete, but reads do not filter it |
| Created one, got two | Duplicate creation from a retry |

### 3. Observability — can you trace it later

**Judge this separately from pass/fail.** "Works but cannot be traced" is the most common state,
and it is why the cause cannot be found in the next outage.

| What to check | Defect |
|---|---|
| Request tracing | Logs exist but cannot be tied to a request (no request ID) |
| Failure records | Only a stack trace, **no input values** |
| What the user sees | Only "An error occurred" — even with a report you cannot find it |
| Sensitive data | Passwords or tokens stay in logs **in plain text** ← report as a defect |

### 5. Idempotency — the same request twice

**This really happens often** through network retries. A user tapping a button twice is the same.

```bash
... api --name {scenario} --root {ROOT}   # once
... api --name {scenario} --root {ROOT}   # once more
{PYTHON} {LAUNCH}/launch_cli.py db --profile db --sql "select count(*) from ... where ..."
```

Whether the second one is 409 (duplicate) or 200 (same result) **depends on the design.** The defect is **ending up with two.**

### 6. Concurrency

Touch the same resource at the same time. It breaks with stock, points, seats and balances.

Sending twice in sequence does not catch it — you must send them **overlapping**. Run the scenario in two shells at once,
or use a tool that sends the same request concurrently. Then check in the DB **that the totals add up**
(10 concurrent orders against stock of 10 → exactly 10 go out).

### 7. Cleanup — so the second run does not break

Backend tests **create real data.** That is the decisive difference from the frontend.

- Write how to delete it in the scenario's `reset`
- Values under unique constraints (email, nickname) **must differ every time** — append a timestamp or random number
- If you could not delete it, **record it in the report.** If you leave it silently, the next person hits failures with no known cause

## Do not look at only one endpoint

**The most common server defect is "this one works but that one does not".** If you walk only the one API you were asked about,
everything looks like a pass.

| If one place has it | Also check | If missing |
|---|---|---|
| Owner check on create | **All of read, update, delete** | Others' data can be seen or deleted — **Critical** |
| One API logs a request ID | All other APIs | Only that stretch can be traced during an outage |
| Page limit on one list | All other lists | It breaks once the data grows |
| Length/format validation on one input | Other inputs that take the same value | A bypass path appears |
| Duplicate prevention on create | **Can update produce the same value** | Uniqueness is broken |
| One place masks passwords | All other logs | Leaking in one line is still a leak |

How to find them: state the rule you just checked in one sentence, **find every endpoint of the same kind**,
and walk each one. The fastest way is to see **where things like `@PreAuthorize`, middleware or `where owner_id`
are present and where they are not.**

> This is not only about services with screens. **API-only servers miss it even more often** —
> with no screen, nobody ever looks at it.

## Look at the life cycle — sign-up as an example

It is not a single API call. **Sign-up → use → withdrawal → sign-up again** is one unit.

```
sign up → try duplicate sign-up → log in → use → withdraw → token after withdrawal → sign up again
```

| What to walk | What to check |
|---|---|
| Sign up | Stored in the DB · logs · the password is not stored in plain text |
| **Sign up again with the same info** | Is it blocked? A pass is a defect |
| Withdraw | Does it really delete, or only flip a flag |
| **Call the API with the token left after withdrawal** | Must be 401 — **often missed** |
| **Sign up again** | Is it a new account, or does old data come along |

**What sign-up-again reveals**: a unique constraint holds on to the withdrawn account and blocks re-registration,
or the opposite, old data comes along with the new account (this can be a privacy problem). **Which one is correct
is up to this service** — judge from the code and policy, and ask the user if you cannot decide.

## Create failures on purpose

Developers have already walked the normal path dozens of times. On a server, bugs are usually found here.

| Situation | How to create it | What to check |
|---|---|---|
| No token | Send without `auth` | 401 or 500 (500 means handling is missing) |
| Expired or forged token | Any string in `auth` | Does the message tell the cause apart |
| Access to someone else's resource | Read with another account's token | **If you get 200 instead of 403, there is no permission check** |
| Missing required field | Remove one field from the body | 400, or a 500 from a DB constraint violation |
| The same request twice | Repeat the same step | Is a duplicate created, or is it idempotent |
| Nonexistent resource | An id that cannot exist | 404, or an empty 200 |

If you put a failure code in `expect_status`, **that becomes the pass criterion.** A step that expects 401 passes only
when it gets 401.

## You decide how to connect to the DB and logs

**Where settings live and how to reach them differ per project.** The skill does not guess — read the code,
decide, and record it in pro-launch `access`. How to record it, the connection routes (`direct` · `ssh` · `command`) and how to read logs are in
`../../pro-launch/references/server.md`.

```bash
{PYTHON} {LAUNCH}/launch_cli.py access set --root {ROOT} --key db --json '{"how":"direct","engine":"postgres","host":"...","port":5432,"db":"...","user":"...","password_env":"DB_PASSWORD"}'
DB_PASSWORD=... {PYTHON} {LAUNCH}/launch_cli.py db --profile db --root {ROOT} --sql "select count(*) from ..."
{PYTHON} {LAUNCH}/launch_cli.py logs --root {ROOT} --tail 100 --grep ERROR
```

> **Do not write the password value.** Use `password_env` to record only **where to read it from**. Writing the value is rejected.

`api` walks the scenario to the end. To check a single request, use pro-launch `http`
(`--expect-status` judges it too). Request header values are not kept in the result.

## Good to know

- **Write how to delete test data in `reset`.** If the second run fails with "already exists",
  the scenario becomes single-use.
- **Do not walk against a production server.** Check where `base_url` points every time. If a scenario that creates and
  deletes accounts runs in production, real user data can disappear.
- **Do not write passwords or tokens in scenario files.** Outputs stay in the home directory but can be shared.
  Take them from the user, use them for that run only, and keep them out of files.
- If the response is not JSON (an HTML error page, etc.), only the beginning goes into `text`. If the cause is not
  visible from that, read the server logs.
