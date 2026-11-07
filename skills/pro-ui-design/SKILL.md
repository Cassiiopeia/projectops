---
name: pro-ui-design
description: "Show UI mockups on a local URL so a person can compare, press and pick: layouts, animations, linked multi-screen prototypes in the repo's real design. Then build it, post it to an issue, or request a designer. Use for 'show me mockups', 'request a design'."
---

# UI design: see it, pick it, or ask a designer

## When to use

- "Show me a few mockups", "compare these layouts", "try some animations", "let me press through this flow" (Korean: '시안 몇 개 보여줘', '애니메이션 시안 보여줘', '이 흐름 눌러 보게 해줘')
- "Post the mockup to the issue" (Korean: '시안 캡처해서 이슈에 올려줘')
- "Request a design", "send this to the designer", "ask them to draw the empty and error screens too" (Korean: '디자인 요청해줘', '디자이너한테 보낼 거 만들어줘')
- A brainstorm reaches a question that is easier to see than to read.

| Situation | Skill |
|---|---|
| No Figma design yet: decide what it looks like, or ask for one | **this one** |
| A Figma design exists: move it into code and compare | `pro-figma` |
| Find bugs by running the real thing | `pro-agent-test` |

Talk to the user in the user's language (or the configured `language` preference). Apply the **absolute rules** in `../references/common-rules.md`.

**You make the mockups and every judgment.** The scripts only run the server, gather facts and capture. Their output is never the design.

## Goal → command → details

Every command is `PYTHONIOENCODING=utf-8 python3 ~/.projectops/bin/projectops_cli.py ui-design <command>` (add `--root <project>` if the shell left the project). All output is JSON with `next`; follow it.

| Goal | Command | Details |
|---|---|---|
| Start or resume a session; get the URL, folders and project notes | `start --title "<screen>" [--issue N] [--open]` | Step 1 |
| Find where after a lost context | `status` | |
| Find this project's design files · save them | `tokens` · `tokens --save` | `references/fidelity.md` · `references/project-profile.md` |
| Check a mockup before showing it | `check [--screen F]` | `references/fidelity.md` |
| Motion, press and drag, screens that affect each other | `UIDesign` in the mockup | `references/motion.md` |
| Read browser clicks | `choices` | Step 3 |
| PNG (page or per option) · GIF of steps | `capture ...` | `references/sharing.md` |
| Record the decision · read it later | `decide --choice b --reason "..."` · `decision` | Step 4 |
| Settings | `config show\|set\|options` | `../references/config-rules.md` §7 |
| Stop the server (mockups stay) | `stop` | |
| Design request for a designer | board and friends | `references/design-request.md` (read only then) |

If that entry point is missing or returns `scripts_not_found`, find the scripts as in `../references/common-rules.md` §"Script lookup" with `SKILL=pro-ui-design`, and call `ui_design_cli.py` directly.

## The flow

### 1. Start

`start` returns `url`, `screens_dir` and `project_profile`. Read the notes if they exist. If they do not, or `changed_files` is not empty, follow `next`. Ask only what changes the mockup; a request with enough detail needs no questions.

### 2. Make the mockup

- Write a new HTML file into `screens_dir` with your file tool. A fragment gets the shared frame; `<!DOCTYPE html>` stays as written. Never overwrite an earlier file: `layout.html`, then `layout-v2.html`.
- **Make it look like this product.** Real tokens, real fonts, the repo's components. Pick the fidelity per question (`references/fidelity.md`).
- Ask the question on the page. Show 2 to 4 options that truly differ. Use real content, not lorem ipsum.
- Things that move or respond must really move and respond. Comparing motion or testing a flow: `references/motion.md`. Build as much of the interaction as the decision needs.
- Run `check`. Fix what it finds or say why it stays.

### 3. Show it and wait

Give the full `url` (it has the key), say in one line what is on the page, and **end your turn**. New files appear in the open tab by themselves; earlier ones stay in its list.

**If the user cannot open localhost** (they say so, or they are on a remote session such as Remote Control): do not hand over only a URL. `capture` it, open the image with Read so it shows in the conversation, and offer to post it to the issue.

Next turn: the terminal reply decides. `choices` adds what was clicked; a click alone never starts work. Reply changed something: write a new file and show it again.

### 4. Decide, then branch

When it is settled, run `decide`. Later skills read it, so nobody asks again. Add one line under `## Decisions` in the project notes if they exist.

| Next | Do |
|---|---|
| Build it | Implement from the mockup and `tokens.css`. Stop here if the user only wanted to see options |
| Post to an issue | `references/sharing.md`. **Get approval first** (`../references/approval-and-questions.md`) |
| Cannot decide, or "ask the designer" | `references/design-request.md`. Mockups you showed become its alternatives |

Then `stop` when nothing is left to show. The server also stops itself when idle.

## What to tell the user

- Say what each image is: HTML mockup, real code render, or real capture.
- HTML is a reproduction, not a pixel match. Native motion in a browser is an approximation; the final feel needs a real device.
- A linked prototype is fake behavior. It settles flow and screens, and proves nothing about the real server, push or login.
- No design files found: say the mockup uses a neutral theme.

## Failure → next action

| code | Action |
|---|---|
| `server_start_failed` | Read `log_tail`, fix it, run `start` again |
| `port_changed: true` | Give the new URL; an open tab will not follow |
| `no_session` · `server_stopped` | `start` with the same title: same mockups, and the same URL when the port is free |
| `screen_not_found` · `option_not_found` | Use a name from `screens`, or a `data-choice` value from the mockup |
| `browser_missing` · `pillow_missing` | Ask, then `launch_cli.py web setup`. Otherwise describe the mockup and give the URL |
| `step_failed` · `bad_steps` | Fix that step in the steps file (`references/sharing.md`) |
| `bad_option_value` · `unknown_option` | `config options` lists names and values |

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start with `SKILL_ID=pro-ui-design`.
Keys for this skill: the common `language`, `tone`, `rules` only. Behavior is under `config`; project knowledge is in `references/project-profile.md`.
Preferences change presentation only; approval gates and secret protection stay in force.
