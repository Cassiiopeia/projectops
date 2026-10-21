# Board assembly · publishing

> When to read: Steps 5–6, when checking what `board` assembled, when writing the issue body, and when you find a mistake after publishing.

## 5. Board: assembly rules

- Topics not in the data are not created on the board. If you fill `states[].design`, a "design" column appears (the Figma gap table).
- **Split PNGs by topic.** One image with everything is unreadable on GitHub. Width is about 2,900px (max 3,400, `--scale` default 2).
- Each image is embedded **only once** in the HTML (even if the same capture is used in several slots). It is scaled down to a size sufficient for display.
- Write image paths relative to the data file.
- PNGs are captured with **the Chromium that pro-launch downloaded**. If it is missing you get `browser_missing`; do not stop, deliver
  HTML or raw captures plus an md table. If a browser is needed, ask the user first, then `launch_cli.py web setup`.
- **Open the PNGs with Read.** If text is cut off or overlaps anywhere, fix the data and assemble again.
- **Publish only when `preflight` in the result is empty.** It flags captures without a source, states without reachability,
  and facts backed only by renders. Right before publishing, assemble with `--strict`; if anything remains it stops with `ok:false` (`preflight_failed`).
- The source of truth for the board HTML layout is `../assets/board.html`.

## 6. Publish: only one format for the designer

Use the **approval gate** (`../../references/approval-and-questions.md` §4 A/B/C) right before publishing.
Show what goes where (issue title, assignee, number of attachments) and get approval. In auto mode, show only a summary and proceed.

| Output | What the designer receives | How |
|---|---|---|
| `issue` | Issue body + PNGs | The Step 6 block in `SKILL.md` |
| `html` | One file, `board/board.html` (images embedded, browse by tabs) | Give the path |
| `markdown` | `board/brief.md` + PNG folder | Built with `board --md`. Give the path |

**Never give both.** The designer would not know which one to look at.

### Image paths in the issue body: change them only with `rewrite-images`

Write the body md with local paths (`board/states.png`), and after uploading insert the URLs with the CLI. Do not substitute them with inline Python.

1. `upload-image ... > {run_dir}/uploads.json`: keep the output JSON as a file as is
2. `design_brief_cli.py rewrite-images --md {body} --uploads {run_dir}/uploads.json` → `<body>.issue.md` (the original md is untouched)
3. Pass the `.issue.md` to `create-issue`

- Matching: with upload-image output, by file name (stem); with a `{"board/a.png": "https://…"}` mapping, by path or name relative to the md. If two files share a name, give a mapping.
- If even one image cannot be matched, you get `unmatched_images` and **nothing is written**, so broken images never reach the designer's notification.
  Upload only the missing ones again and call it with one more `--uploads` (it can be given several times).

### Issue body skeleton: same names and order as the board

Match the sections of the repo's design request template. The title follows the repo's issue title rules.

| Section | Contents |
|---|---|
| 🖌️ Request (`🖌️ 요청 내용`) | What and why, a current-state table, **must-keep rules** (with sources), current implementation PNG |
| 🎯 Expected result (`🎯 기대 결과`) | What development does once a given design arrives |
| 📋 References (`📋 참고 자료`) | State PNGs · alternative PNGs (A · B · C) · copy table · UI elements. The dev side's recommendation in **one line** |
| 💡 Additional requests (`💡 추가 요청 사항`) | Options that cost extra development if chosen · questions (conflicts with principles, disagreements between design frames) |
| 🙋 Assignees (`🙋 담당자`) | Designer |

### If you find a mistake after publishing

Edit the body and **add a separate correction comment.** The designer may already have seen the old body through a notification; editing only the body
does not tell them what changed. In the correction comment, put a table of "initially written → actual → evidence" and attach a real-device capture.

### Private repos

**Images do not render in private repos** (`private_warning` from `upload-image`). Tell the user
and ask whether to switch to `html` output.

## Not done

- Calling AI generation APIs for captures (use fake data instead)
- Drawing in Figma (the MCP is read-only)
- Deciding for the designer (the recommendation is one line; the choice is the designer's)
- Proposing candidates for legal text
- Fixing, inside the brief, screen defects found apart from the request (list them as "separate" in the state table and tell the dev side)
