# Web sign-in — Google · Apple · Naver · Kakao · GitHub

> When to read: before signing in to Google, Apple (developer.apple.com, App Store Connect, Apple Account), Naver, Kakao or GitHub in a `pro-launch web` browser,
> and when such a sign-in stops at a two-factor, captcha or "browser not secure" screen. Apple's code that arrives on this Mac is in [Apple](#apple).

This is a guide you follow while making your own decisions, not a script. **Sites change:** the selectors below are hints from a structure check
(2026-11-13, Korean UI, signed out). Always confirm them with `web inspect` before typing. The rules in `web.md` (safety contract, credentials,
interstitial screens, profiles) apply; this file only adds the order and the provider differences.

## Contents

- [Common flow](#common-flow) · [Two-factor kinds](#two-factor-kinds) · [Rules](#rules)
- Providers: [Google](#google) · [Apple](#apple) · [Naver](#naver) · [Kakao](#kakao) · [GitHub](#github)
- [macOS permissions for the desktop part](#macos-permissions-for-the-desktop-part) · [Out of scope](#out-of-scope)

## Common flow

| Step | Command | Decide |
|---|---|---|
| 1. Reuse a signed-in profile | `web open --need login:<provider> --url <url>` | `no_matching_profile` → go on. Signed in already → done |
| 2. Find the account | `cred list` (`kind: login`, `provider`, `use_when`) | Nothing fits → ask the user (`web.md` "Credentials") |
| 3. Open | `web open --headed --url <login url>` | Google and Apple block headless more often. Stealth is on by default (`web.md` "Google · Apple login — stealth") |
| 4. Find the inputs | `web inspect --role input` | `nothing_found` with `frames` → the form is in an iframe: `web inspect --frame <name\|part of url\|iframe>` |
| 5. Type | `web type [--frame F] --ref N --cred <name> --cred-field account`, then the password with `--cred <name>` | Never `--text` for a password |
| 6. Submit | `web click [--frame F] --ref <button>` | `content_changed` / `frame_content_changed` true = the step moved. Read it with `web text [--frame F]` |
| 7. Second factor | See [Two-factor kinds](#two-factor-kinds) | Only a person can answer → hand over and `web wait` |
| 8. Interstitials | trust this browser · stay signed in · passkey nags | Follow `login_policy` (`web.md` "Interstitial login screens") |
| 9. Record | `web profile mark --kind login --name <provider> --note "<account hint>"` | Next time step 1 finds it and no sign-in is needed |
| 10. Learn | `learn --area web --key <provider>.signin --how "<one line>"` | Only a method that is new, never values |

The flow is the same with `web login` (`--user-selector` · `--password-selector` · `--submit-selector` · `--until-url`) when the form is on the top page.
`web login` has no `--frame`; for iframe forms use the steps above.

## Two-factor kinds

| Kind | What the screen says | What you do |
|---|---|---|
| Approve on a phone | "check your phone", a number to tap | Relay the number and a `web shot`. Do not navigate. `web wait --gone "<prompt text>" --timeout 120` |
| Code by SMS · email · authenticator app | One input, or one box per digit | Ask the user for the code. One input: `web type --ref N --text-env CODE`. Per-digit boxes: click the first box, then `web type --keys <code>` |
| Code on this Mac (Apple) | "enter the code sent to your Apple device" | [Apple](#apple) desktop part, after the user agrees |
| Passkey · security key | A system passkey sheet | Only a person can answer. Ask, or choose "other options" / password if the page offers it |
| Captcha · keyboard security · device check | Picture puzzle, "unusual activity", new device notice | Only a person. Ask, keep the window open (`--headed`), `web wait` |

## Rules

- **Do not retry a failed password or code.** Stop and ask. Accounts get locked.
- A code is single-use and short-lived. Do not repeat it in the conversation, issues, reports, `learn`, `journal` or captures (`mask` before attaching).
- Approve a sign-in only for the sign-in this session just started, and only after the user agreed in this conversation.
- `web goto` or a reload on a waiting two-factor screen cancels it. Use `web wait`.

## Google

| Item | Hint (confirm with `web inspect`) |
|---|---|
| Login URL | `https://accounts.google.com/signin` (lands on `/v3/signin/identifier`) |
| Step 1 | `input#identifierId` (`name=identifier`), then the "Next" button. Password is a second page |
| Account chooser | If the profile knows accounts, a list appears instead. Click the right account, or "Use another account" |
| "This browser or app may not be secure" | Bot detection. `web open --headed`; if it stays, the user signs in once in that window, then `web profile mark` |
| Second factor | Usually phone approval (tap a number), sometimes a code or passkey. See [Two-factor kinds](#two-factor-kinds) |
| After | "Stay signed in", recovery phone, passkey nags → `login_policy` |

## Apple

Covers developer.apple.com/account, App Store Connect and Apple Account pages. Measured end to end on macOS 27.2 (#1132).

### Web part

| Item | Hint (confirm with `web inspect`) |
|---|---|
| Login URL | `https://developer.apple.com/account` (redirects to `idmsa.apple.com/IDMSWebAuth/signin`) · `https://appstoreconnect.apple.com/login` |
| Frame | The form is in an iframe named `Widget` (url `idmsa.apple.com/appleauth/auth/signin?widgetKey=...`). Use `--frame Widget` on every command |
| Inputs | `#account_name_text_field`, `#password_text_field` (the password box may stay hidden until "Continue") |
| Buttons | `#sign-in` (label "Continue", then "Sign In"), `#swp` (sign in with a passkey — do not press) |
| Code page | Six `tel` inputs labeled "code digit 1..6" in the UI language. Click box 1, then `web type --frame Widget --keys <code> --delay-ms 120` |
| After | "Trust this browser?" → `login_policy` `trust_device`. With `ask`, ask the user |

```bash
{PYTHON} {SCRIPTS}/launch_cli.py web open --headed --url https://developer.apple.com/account
{PYTHON} {SCRIPTS}/launch_cli.py web inspect --frame Widget --role input
{PYTHON} {SCRIPTS}/launch_cli.py web type --frame Widget --ref 1 --cred <apple-cred> --cred-field account
{PYTHON} {SCRIPTS}/launch_cli.py web type --frame Widget --ref 2 --cred <apple-cred>
{PYTHON} {SCRIPTS}/launch_cli.py web inspect --frame Widget --role button       # ref of "Continue" / "Sign In"
{PYTHON} {SCRIPTS}/launch_cli.py web click --frame Widget --ref <button>          # frame_content_changed: true when the step moved
{PYTHON} {SCRIPTS}/launch_cli.py web text --frame Widget                          # two-factor page? go to the desktop part
```

### Desktop part — the code arrives on this Mac

Do this only when the Mac running the agent is a trusted device of that Apple Account and the user agreed. Otherwise ask the user for the code.

| Step | Command | Note |
|---|---|---|
| 1 | `desktop doctor` | `permission_missing` → [macOS permissions](#macos-permissions-for-the-desktop-part) |
| 2 | `desktop session start --purpose "Apple sign-in code"` | Relay `tell_user` |
| 3 | `desktop wait --window overlay --text "Apple" --timeout 60` | Start right after the web "Sign In" click. The match carries `ref` and `named_actions` |
| 4 | `desktop click --window overlay --ref <ref> --action "<Allow>" --confirm-mutating` | Allow is the action that is not "Don't Allow", "Close" or "Details" |
| 5 | `desktop tree --window overlay` | The code window shows digits with spaces (`N N N   N N N`). Drop the spaces |
| 6 | `desktop click --window overlay --ref <Done> --confirm-mutating` | The code window holds keyboard focus until it closes |
| 7 | Web code page: click box 1, `web type --frame Widget --keys <code> --delay-ms 120` | Do not echo the code anywhere else |
| 8 | `desktop session stop` | Always, also after a failure |

**Which alert is this?** The text differs by macOS version and language, so judge by structure and timing, not by exact words:

| macOS | Title (English UI) | Actions |
|---|---|---|
| Older | "Apple Account sign-in requested" with a map and a place | Allow · Don't Allow |
| 27.x (seen on 27.2) | "Signed-in Apple Account" — "Your Apple Account is signed in on a device" | Details · Don't Allow · Allow · Close |

The Korean UI labels seen on macOS 27.2 are in `kb show desktop-apple-2fa-code-window`. The newer text does not say "sign-in requested", so it is the session's own
sign-in only when it appears **within about a minute after this session pressed "Sign In"** and the web page shows the code page. An alert at another time,
or with a place the user does not recognize, is not ours: press "Don't Allow" only if the user says so, otherwise leave it and ask.

**When it goes wrong**

| Symptom | Check | Fix |
|---|---|---|
| No alert within 60 s | `desktop windows` (overlay rows), the web page text | Use the page's "didn't get a code?" → resend once. Or ask the user for the code from another device |
| Alert gone before the click | Banners leave after about 5 s | `desktop wait` again right before the click; the code window may already be open (`desktop tree --window overlay`) |
| "Don't Allow" pressed or alert closed | The web page still waits | Resend once from the page, then repeat the desktop part |
| Code rejected or expired | Page error text | Resend once. Never type the same or a guessed code again |
| `permission_missing` at `desktop click` | `desktop doctor` → `host_app`, `grant` | A person grants it, see below |
| Web click says nothing changed | `web text --frame Widget` | Fixed in #1132 for iframes; if it still happens, read the frame text before clicking again |

## Naver

| Item | Hint (confirm with `web inspect`) |
|---|---|
| Login URL | `https://nid.naver.com/nidlogin.login` |
| Inputs | `#id` (`name=id`), `#pw` (`name=pw`), no iframe |
| Buttons | `#loginBtn_row` (sign in), `#passkeyBtn_row` (passkey — do not press) |
| Blocks | Automated typing often leads to a captcha or a keyboard-security prompt. Do not try to solve it: ask the user |
| Second factor | "New device sign-in" notice or approval in the Naver app; a code by SMS for some accounts |
| Prefer | Sign in once with the user present (`--headed`), `web profile mark --kind login --name naver`, then reuse with `--need login:naver` |

## Kakao

| Item | Hint (confirm with `web inspect`) |
|---|---|
| Login URL | `https://accounts.kakao.com/login/?continue=<encoded return url>`. Without `continue` the page answers `/v2/error/400` |
| Inputs | `input[name=loginId]`, `input[name=password]` (ids carry a suffix like `loginId--1`; do not rely on the id) |
| Other ways | QR code sign-in and "sign in with KakaoTalk" — both need the user's phone |
| Second factor | Approval in the KakaoTalk app ("2-step verification"). Relay it and `web wait`; do not navigate |
| Developer console | `developers.kakao.com` uses the same account; the debugger pages may misbehave with stealth (`web.md` "Google · Apple login — stealth" step 3) |

## GitHub

| Item | Hint (confirm with `web inspect`) |
|---|---|
| Login URL | `https://github.com/login` |
| Inputs | `#login_field` (`name=login`), `#password` (`name=password`), submit `input[name=commit]` |
| Other buttons | "Continue with Google", "Continue with Apple", "Sign in with a passkey" — do not press unless the user chose that route |
| Second factor | Authenticator code (`/sessions/two-factor/app`), SMS code, passkey or security key (`/sessions/two-factor/webauthn`), GitHub Mobile approval. A **device verification** code by email (`/sessions/verified-device`) appears for a new browser even without 2FA |
| Code entry | One input, may submit by itself after the last digit: `web type --ref N --text-env CODE`, then `web wait --url-contains github.com` |
| Prefer | For API work use a token (`cred` `kind: github-org` or the `pro-github` PAT), not the web sign-in |

## macOS permissions for the desktop part

The permissions belong to the **host app** that runs the agent (Terminal, iTerm, Paseo, Cursor, VS Code, Claude desktop…), not to Python.

- Both are needed: **Accessibility** and **Screen & System Audio Recording**. `desktop click` · `type` · `press` · `focus` need Screen Recording too
  (they compare the screen before and after). With Accessibility only, `desktop session start` works and `desktop click` fails with `permission_missing`.
- `desktop doctor` names the host app (`host_app`), the panes to open (`grant`, `open_settings`) and what to ask (`ask_user`).
- **Only a person can grant them**, once per host app: the agent cannot press System Settings for its own host (those clicks need the same permissions, and
  macOS asks for the user's password). Relay `ask_user`, wait for "done", then the host app must be quit and reopened, and `desktop doctor` run again.

## Out of scope

- Sign-in inside native apps on simulators and emulators: `app.md` (`device mark --kind login --name <provider>`, `device acquire --need login:<provider>`).
- Changing account security, turning off two-factor, storing authenticator secrets (`web.md` "Out of scope").
