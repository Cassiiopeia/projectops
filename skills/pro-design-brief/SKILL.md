---
name: pro-design-brief
description: "Build a design request for a designer from a screen you already built: capture real states, render layout alternatives, collect copy and must-keep rules, deliver as issue, HTML or md. Use for 'request a design', 'send to designer'."
---

# Design request: for a screen built before its design

## When to use

- "Request a design", "post a design request", "make something to send to the designer" (Korean: '디자인 요청해줘', '시안 요청 올려줘', '디자이너한테 보낼 거 만들어줘')
- "There's no design for this yet but I built it first", "ask them to draw the empty and error screens too", "create a design issue" (Korean: '이거 디자인 안 나왔는데 먼저 만들었어', '빈 화면이랑 에러 화면도 그려 달라고 해줘', '디자인 이슈 만들어줘')
- Turning a design into code and comparing it is pro-figma; finding bugs is pro-agent-test.
- If there is a Figma link, separate the states drawn in the design from the missing ones and request the gaps. Give material to think with, not the answer.

The screen gets built first and the design comes later. **Designers usually draw only the default screen.** Empty, failed and
long-text cases go missing. This skill builds a request that fills those gaps first.

Talk to the user in the user's language (or the configured `language` preference). Write the brief in the configured `language`; if none is set, match the repo's design request template or the user's language.

> **Do not give the answer. Give material to think with.** Lay out alternatives, copy and elements broadly; state the dev side's preference in one line with its reason.
> **Always end with a deliverable the designer receives**: an issue with images / one HTML page / an md folder. Never end with a chat summary.

| Use it | Do not use it |
|---|---|
| Implemented without a design → request a design | A design exists and you are coding it → `pro-figma` |
| The design has only the default screen → request missing states | Finding bugs → `pro-agent-test` |
| The designer cannot find a direction → provide material | Building a new design system |

Apply the **absolute rules** in `../references/common-rules.md`. Settings: §2–4 of `../references/config-rules.md`; approval gate:
`../references/approval-and-questions.md`. **Do not re-investigate what is already in the conversation.** In particular, "why this placement was chosen"
exists only in the conversation, so always keep it. Arguments: $ARGUMENTS

## Goal → command → details

| Goal | Command | Details |
|---|---|---|
| Decide/save output mode · designer · confirm-before-posting | `design_brief_cli.py config show\|set` | Step 0 below |
| Read Figma · image input, gap table | `mcp__figma__get_figma_data` · `figma_cli.py coverage` | `references/states-and-capture.md` |
| State list (5 axes) | — (read the code) | `references/states-and-capture.md` · `../references/design-states.md` |
| Capture slot · device/browser/render capture | `launch_cli.py get-output-path --skill design-brief` · `app shot` · `web route` · `render run` | `references/states-and-capture.md` |
| States that cannot be rendered · options that do not exist yet | `design_brief_cli.py ascii --spec` | `references/states-and-capture.md` |
| Alternatives · copy · UI elements · must-keep rules | `design_brief_cli.py copy-lint` | `references/content.md` |
| Assemble the board (HTML → per-topic PNG · md) | `design_brief_cli.py get-output-path` → `board` | `references/publishing.md` |
| Publish (issue · HTML · md) | `github_cli.py upload-image` → `design_brief_cli.py rewrite-images` → `create-issue` | `references/publishing.md` |

## Find the scripts: once

**The Bash tool resets its state on every call.** Find them once and **write the real paths as literal values in later blocks.**

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
for SKILL in pro-design-brief pro-launch pro-github pro-figma; do
  ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
  [ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
    H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
    [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
  done
  [ -d "$ROOT/skills/$SKILL/scripts" ] || { echo "$SKILL scripts not found"; exit 1; }
  echo "$SKILL=$ROOT/skills/$SKILL/scripts"
done
```

Placeholders: `{SCRIPTS}` = pro-design-brief (config · get-output-path · board · copy-lint · ascii · rewrite-images), `{LAUNCH}` = pro-launch (capture · render · staging states),
`{GITHUB}` = pro-github (images · issues), `{FIGMA}` = pro-figma (counting the Figma dump, when there is a link).

## Common rules

- Flow: `0 settings → 1 input → 2 state list → 3 capture → 4 alternatives · copy · UI · must-keep → 5 board → 6 publish`.
- **Evidence for "this is how the app is now" comes from a real device and the production API.** Rendering is a way to stage states (claims written from renders alone differed from the real device in 7 places).
  Give each capture a `source`, and put factual statements in `facts[]` with a `basis`. Numbers come from production values, not fixtures.
- **You read the code** and list the states. Each state gets a `status` (done · temp · none) and `reachable` (yes · old_data · unknown);
  check in the code whether the input path still exists. Text the server sends (notices, terms, errors) is also a state.
- Navigate device screens **by element** (`app tap --text|--id|--desc`; if unsure, `app tree`). No guessing coordinates, no host mouse.
- Alternatives: **3 to 5 options on different axes**, always including a "current implementation" and a "minimal" option. Offer no candidates for legal text (`legal: true`).
- Do not call AI generation APIs to make captures. Clean up only the `residue` you created. Do not decide for the designer.
- **Do not show config key names or file paths to the user.**

## 0. Settings: decide once, automatic afterwards

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/design_brief_cli.py config show --root {PROJECT_ROOT}
```

`resolved` shows three items. Ask only about those in `missing`, **one at a time**, with the recommended option first.

| To decide | Automatic decision (`suggest`) | When asking |
|---|---|---|
| Output mode | `issue` for a GitHub repo, else `html` | "How do you want the design request? 1) Design issue (recommended) 2) One HTML page 3) md folder" |
| Designer | The `디자인:` line in the issue templates (`designer_candidates`). If empty, the assignee of recent design issues via `{GITHUB}` | "What is the designer's GitHub ID (or name)?" |
| Confirm before posting | Confirm by default | Approval gate branch C on the first post |

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/design_brief_cli.py config set --root {PROJECT_ROOT} --destination issue --designer {id}
#   --scope default      : default for all repos ("from now on, everywhere")    --auto-approve true : "post without asking next time"
```

"Use HTML from now on" is the same command. Repos that do not use GitHub are matched by path (the reason this is kept apart from the `github` settings).

## 1–4. Input · states · capture · material

Decide whether it is implemented (implemented / partial / not yet), and if there is a Figma file, build the gap table of drawn vs missing states.
From the 5 axes (data · input · environment · person · display), pick **only the states that apply to that screen**. Order: `references/states-and-capture.md`.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py get-output-path --skill design-brief --title "{screen name}"
source "{env_file value}"          # $SHOT_DIR · $RUN_DIR · $DEV
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py device acquire --platform ios --purpose "design request {screen}"   # borrow a device for an app · device release when done
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app shot --device "$DEV" --out 01_current --clean-status
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/design_brief_cli.py ascii --spec '{"title":"…","rows":["…","---"],"width":24}'
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/design_brief_cli.py copy-lint --file {board data.json} --banned "kid,device,server"
```

Capture order is **code render → real device / browser → ASCII**. Alternatives, copy (`current → 2–3 candidates → reason`), UI elements (what the repo already has first) and
must-keep rules (brand specs, design principles, agreed exceptions in code comments; raise conflicts as questions) are in `references/content.md`.

## 5. Board: one HTML page → per-topic PNG

Write everything you collected into one **data JSON** and assemble it (image paths relative to the data file).

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/design_brief_cli.py get-output-path --title "{screen name}"   # same title as the captures
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/design_brief_cli.py board --data {run_dir}/board_data.json --out {run_dir}/board --png
#   --md : also writes brief.md    --strict : stops with ok:false if preflight items remain (right before publishing)
```

```json
{
  "title": "{screen} — design request",
  "summary": {"what": "", "why": "", "status": "", "recommend": "Option A — one-line reason", "note": "",
              "must_keep": [{"rule": "", "source": "file · issue · doc"}]},
  "facts": [{"claim": "The weekly grant is 50", "basis": "device|server|code|design", "ref": "GET /api/credit · capture file"}],
  "current": [{"label": "Login (iOS)", "image": "screenshots/login_ios.png", "source": "device"},
              {"label": "Version at 4x", "image": "screenshots/zoom.png", "zoom": true, "source": "device"}],
  "states": [{"axis": "Data", "name": "0 items", "status": "done|temp|none", "reachable": "yes|old_data|unknown",
              "image": "", "source": "render|device|server", "ascii": "",
              "copy": "", "copy_needed": false, "design": true, "render_failed": false}],
  "alternatives": [{"id": "A", "name": "", "image": "", "source": "render", "zoom": "", "ascii": "",
                    "recommended": true, "pros": [], "cons": [], "dev_impact": ""}],
  "copy": [{"where": "", "current": "", "candidates": [], "reason": "", "legal": false, "needed": false}],
  "ui": [{"shape": "List", "candidates": [], "existing": [], "new": []}],
  "impact": [{"choice": "Option B", "work": "extra development needed"}]
}
```

**Open the PNGs with Read.** **Publish only when `preflight` is empty.** Assembly rules: `references/publishing.md`.

**When you only want a preview** (a person looks before publishing): `board` does not publish. Open the per-topic PNGs from `--png` and `brief.md` with `Read`,
show them to the user, and go to Step 6 only after approval. Do not build a separate contact sheet with PIL. When showing them, **state how many images were replaced with ASCII, if any**.

## 6. Publish: only one format for the designer

Approval gate right before publishing (`approval-and-questions.md` §4 A/B/C): show the title, assignee and number of attachments, and get approval.
For `html`, give the path of `board/board.html`; for `markdown`, `board/brief.md` plus the PNG folder. **Never give both.**
For `issue`, **images first** (if you post the body first, a post without images goes out):

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {GITHUB}/github_cli.py upload-image {owner} {repo} {run_dir}/board/*.png --prefix brief > {run_dir}/uploads.json
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/design_brief_cli.py rewrite-images --md "{body .md path}" --uploads {run_dir}/uploads.json   # → <body>.issue.md
PYTHONIOENCODING=utf-8 {PYTHON} {GITHUB}/github_cli.py create-issue {owner} {repo} "{title}" "{<body>.issue.md path}" "{labels}" --assignees "{designer}"
PYTHONIOENCODING=utf-8 {PYTHON} {GITHUB}/github_cli.py add-comment {owner} {repo} {implementation issue} "{link comment .md}"   # link it with the implementation issue both ways
```

Match the body to the repo's design request template (🖌️ Request · 🎯 Expected result · 📋 References · 💡 Additional requests · 🙋 Assignees, or the Korean template's equivalents), using the same
names and order as the board. If something is wrong after publishing, edit the body and add a **correction comment** (initial → actual → evidence). See `references/publishing.md`.

## Failure path → next action

| code · situation | Action |
|---|---|
| `browser_missing` · `png_failed` | Deliver HTML, or raw captures plus an md table, instead of PNGs. Give the reason in the summary. If a browser is needed, ask, then `launch_cli.py web setup` |
| `preflight_failed` | Fix or drop captures without a source, states without `reachable`, and facts based only on renders |
| `candidate_issues` (copy-lint) | Fix the flagged candidates yourself |
| `bad_data` · `bad_file` · `bad_spec` | Fix the JSON format (ascii takes only `title` · `rows` · `width` · `caption`) |
| `bad_destination` · `nothing_to_set` | Use `--destination issue\|html\|markdown`, and give at least one value to change |
| Render failed | Replace only that state with ASCII and set `render_failed: true` |
| Upload failed · `private_warning` | Report the local output path. For a private repo, ask whether to switch to `html` |
| `unmatched_images` (rewrite-images) | Upload the `unmatched` images with `upload-image`, add that output to `--uploads` too, and run again. Do not rewrite paths with inline Python |
| Figma read failed · designer unknown | Continue without it and note it in the summary (file without an assignee → ask next time) |
| Leftovers (`residue`) in the target repo | Report them as they are and do not delete them (delete only what you created) |
| Cannot verify on a real device (device, account, cost) | Drop that fact from `facts` or leave it without a basis and write "not verified". Do not assert it from a render instead |

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-design-brief`.
Keys for this skill: the common `language`, `tone`, `rules` only.
Preferences change presentation only; approval gates, secret protection and `--dry-run` stay in force.
