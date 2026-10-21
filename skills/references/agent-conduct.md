# What to do when you are blocked (detail)

This is the detail behind `common-rules.md` §"When something you need is missing" (including "before you say it
cannot be done"). Read it right before you decide a tool is missing or that "the user has to do this themselves".

## When something you need is missing — do not just give instructions and stop

A skill may need a tool (a package, a browser, a CLI) that is not installed. Follow this order.

1. **Say what is needed, why, and how big the download is** — "To drive the web, I need a browser (about 100MB)."
2. **Ask** — this changes the user's environment, so it needs approval.
3. **Once approved, the skill installs it itself** — do not stop after printing a command.

> If you only say "run `pip install X`", the user stops there. On macOS, Homebrew Python blocks `pip install`
> under PEP 668, so **following that advice fails anyway.** Handling that wall for the user, instead of
> handing it over, is part of the skill's job.

**Touch the system environment as little as possible.** If you can install into a dedicated virtual
environment or an isolated path, do that. Installation must be **idempotent**: if the tool is already there,
pass silently, and calling it again must not break anything.

## Before you say it cannot be done — check for an automated path first

Before you decide "the user must do this in a console or UI", **look up** whether a CLI or automation already
in the repo (fastlane match/cert/sigh, the GitHub API, SSH scripts, and so on) or a saved credential
(for example `kind: login` in `launch_cli.py cred list`) can do it. Do not end with "I can't do that" without checking.

- **Look things up right away; run changes only after approval.** Reading files, `cred list`, and `--readonly`
  checks need no question. Runs that are **hard to undo or change outside state** (reissuing a certificate,
  rotating a Secret, changing an external account or repository) need you to say what will change and get
  approval first. "Try first" does not mean "run without approval". Use a saved credential only within its
  `use_when` and `scope`.
- **Separate the point where you are truly blocked** (entering a 2FA code, approval from the account owner, and
  so on) **from the part you can do yourself**, and propose them separately. Do not lump it all into "I can't do any of it".
- Example: "I can try to reissue the certificate with fastlane match. I only need you to enter the Apple 2FA
  code. Shall I go ahead?"
- If the user pushes back with something like "but you can log in and do it", do not refuse again.
  **Say exactly what you tried and where it stopped.** Do not just repeat "it doesn't work".
