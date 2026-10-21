# Getting through the login gate · points where a person must act

> When to read: when you hit a login screen, and when you reach a screen a person must handle, such as 2-step verification, payment or a captcha (Phase 4).

## Points where a person must act — stop at once and tell the user

Do not bypass or guess.

| Situation | How to recognize it on screen |
| --- | --- |
| 2-step verification | "Verify", "2-Step", "tap the confirm button", a countdown |
| Biometrics | Fingerprint or Face ID prompt (the simulator can substitute via menu — `../../pro-launch/references/app.md`) |
| Payment | Card entry, store payment sheet |
| Switch to an external app | `mCurrentFocus` is not our package |
| Captcha | Image selection, text entry |

> **The login screen itself is not in this table.** If you hand it over on sight, nothing after it is ever verified —
> follow the steps below and **get through it yourself**; stop only when you reach 2-step verification.

What the message **must include** (write it in the user's language, or the configured `language` preference):

```
You need to do this now — {what}

One line on {which app / where} and {what to tap}.
{Time left, if there is a time limit}. If it runs out, retrying is fine.
```

Because of the risk of locking the account, **never auto-retry a password more than once.**

---

> Login is **the start of the walk, not the end.** If you stop here, the screens after it
> are never verified. Most apps and webs require login from the first screen,
> so what this document covers is not an "extra feature" but **whether you can walk at all.**

> **Check saved login info first.** If `pro-launch`'s `cred list` has an account for this app or provider with `kind: login`,
> use it (`web type --cred` · `app type --cred`). If not, ask, and save **only what you are allowed to** — see
> "When saving login info" in `pro-launch/references/web.md`. Keep the account in `cred` and the method that worked in `learn`.

## First: check whether there is a way in without logging in

Follow the order. The further down, the more expensive and fragile.

| Order | Method | When |
| --- | --- | --- |
| 1 | **Test account · seed data** | Always this if the project provides it |
| 2 | **Dev bypass flag** (`SKIP_AUTH`, etc.) | Common in local and staging |
| 3 | **Inject a token directly** — issue it from the server and put it into storage | When the API is open |
| 4 | **Own-account login** (email + password) | Much more stable than social login |
| 5 | Social login | When none of the above exist |

**Do not go to 5 without checking 1–3.** They are usually written in the project's `CLAUDE.md`, `README`, `docker-compose`
or seed scripts. If not, **ask the user first** — one line, "is there a test account?",
saves 30 minutes.

## Why social login rejects automation

Providers (Google, Apple, Kakao, etc.) detect automated browsers **before you even reach the login screen**
and downgrade them to a low-end flow or reject them. So **the rejection happens at the email step,
not the password step.**

The important point is that **you can tell before you try.** The address and screen already say
"this is a downgraded flow". Read that, then decide whether to try.

### Google — measured

| Signal | Meaning |
| --- | --- |
| `flowName=WebLiteSignIn` in the address | Detected as automation → **trying leads to `/signin/rejected`** |
| `flowName=GlifWebSignIn` in the address | Normal flow → you can proceed |

The rejection text is `Couldn't sign you in / This browser or app may not be secure.` and
**it never asks for the password.**

### How to get through — open it visibly

```bash
{PYTHON} {LAUNCH}/launch_cli.py web open --headed --root {PROJECT_ROOT}
{PYTHON} {LAUNCH}/launch_cli.py web goto --url "https://accounts.google.com/ServiceLogin" --root {PROJECT_ROOT}
```

> **Measured (projectops, 2026-09-18)** — same Chromium, same address, only `--headed` differs:
>
> | Mode | flowName reached |
> | --- | --- |
> | Default (headless) | `WebLiteSignIn` |
> | `--headed` | **`GlifWebSignIn`** |
>
> **Headed or not was the only difference** — no anti-bot extension or separate browser.
> This means this skill's `web` commands are enough.
>
> pro-launch turns on hiding of automation markers (stealth, moved from gstack) by default, so headless gets blocked less,
> but **if login is needed, `--headed` still comes first.** Read `flowName` in the address before pressing the login button.

You cannot use this path in an environment without a display (CI, remote SSH). Then go back to 1–4 above.

## What did not work — do not retry

| Attempt | Result |
| --- | --- |
| Direct login in headless | `/signin/rejected` at the email step. It does not even ask for the password |
| Import cookies from installed Chrome (macOS) | A "Chrome Safe Storage" Keychain approval dialog appears and **the command returns immediately**. Rerunning still gives 0 cookies — impossible from a remote session that cannot see the screen |
| Bypass via public pages without login | Even the closed-testing opt-in page (`play.google.com/apps/testing/{package}`) requires login |

## Native Android Google login — the account picker

The Play Services account picker that the app's "Sign in with Google" opens is **a screen outside the app** (unlike web login).

- If the device **already has** a test account, pick it with `app tap --text "{account email}" --shot` — it is found as a screen element.
  The email is an identifier visible on screen, so passing it with `--text` is fine (never a password or token — those go through `app type --cred`). Mask it in reports and issues.
- If there is **no** account (an add-account screen appears) or 2-step verification appears, **stop and hand over to the user.** Do not add accounts to the device on your own.

## 2-step verification — stop here

Reaching an identity check screen is the end of automation. **Read the screen and pass on exactly what it says.**

What it says differs per account. Even in our measurements it split like this.

| Screen | What the user does |
| --- | --- |
| Device notification + number | "Yes" on the notification → tap the number shown on screen |
| Device notification only | Tap "Yes" on the notification (no number) |
| Alternative method prompt | Open a specific app on another device to confirm |

**Do not reuse a memorized format.** If you ask for a number that is not there, or leave out the alternative method shown,
the user is lost even with the phone in hand. Pass on exactly what is on screen — which device, what to tap, and the number if there is one.

- If a **recovery-info setup screen** pops up after passing, press **"Cancel"** — do not change account settings on your own
- Once passed, the session stays in the browser, so **later rechecks work without logging in**
- Closing the browser with `web close` also ends the session. Keep it open during continuous work

## Handling secrets ⚠️

**A password written in command arguments stays in plain text in the session history file.**
If you pass it through an environment variable, only the variable name stays in the history.

```bash
APP_PW="..." {PYTHON} {LAUNCH}/launch_cli.py web type \
  --selector 'input[type=password]' --text-env APP_PW --root {PROJECT_ROOT}
```

- Values passed with `--text-env` are masked as `***` even in failure responses
- **Do not copy them into report text, screenshots or notes.** A screenshot right after login can carry
  a token in the address bar, so capture only the area you need
- If you received credentials in the conversation, **recommend changing them after the work is done**
- Account lock risk — **auto-retry at most once.** Hand the second failure to the user

## Not yet verified

| Provider | Status |
| --- | --- |
| Google | **Measured** (table above) |
| Apple | **Unverified.** The same approach (headed) likely works, but do not assume so until confirmed |
| Kakao · Naver · GitHub, etc. | **Unverified.** Detection signals differ per provider |

**When you meet an unverified provider, do not guess; follow the order.**

1. Open headed and go as far as the login screen
2. **Record the address and screen text first** — this becomes the detection signal for the next person
3. If rejected, keep that signal with `note` and hand over to the user

```bash
{PYTHON} {SCRIPTS}/e2e_cli.py note pitfall \
  --text "Kakao login: rejected even headed, with {observed signal}" \
  --scope platform --root {PROJECT_ROOT}
```

Setting `scope` to `platform` signals that **this belongs in the skill, not in this project.**
Keeping the next person from getting lost at the same wall is how this document grows.
