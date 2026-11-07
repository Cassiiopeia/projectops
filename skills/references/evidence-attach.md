# Evidence: attach it by default, check it first

> When to read: before writing an issue, a completion comment, a report or a QA report.

The reader should see what you saw without asking. **Attach without being told.** Checking for sensitive content is what you never skip.

## What goes where

| Writing | Attach by default |
|---|---|
| New issue | Every image in the conversation that relates to it: the bug screenshot, the reference, the mockup |
| Completion comment or report | Captures of the result (`pro-launch`, `pro-ui-design`), E2E results, key log lines, and what you could not verify |
| QA or defect report | The capture or recording of each finding, plus the log lines around it |

- **Where to find them:** a pasted image's path appears in its message (`[Image: source: <path>]`). Captures are in the paths your tool results returned. That file may be temporary and disappear later, so upload it early in the work. If it has no path anywhere, or the file is gone, write the rest first, then ask for it once.
- **Choose:** one image per claim, final state only, no near-duplicates. Before and after beats ten screens. For motion or a flow, use a GIF. A change with nothing to show gets no filler image.
- **E2E results:** one table row per scenario with the actual result, including failures and what was not run. Never only "tests passed".

## Check every item before posting

Do this yourself. The commands only help.

1. **Open every image with Read and look at all of it,** including corners: status bars, notifications, browser tabs and profile icons, side panels, file paths.
2. **Read every log excerpt.** `redact` catches known formats only. It cannot know that a name or an internal host is sensitive.
3. **Hide what you find,** then open the masked copy with Read to confirm it is covered and the point of the image survives.

| Look for | |
|---|---|
| Credentials | Tokens, passwords, API keys, cookies, session IDs, signed URLs, QR codes |
| Personal data | Real names, emails, phone numbers, addresses, IDs, payment details, faces, other people's messages |
| Internal details | Server IPs, internal hosts, account IDs, customer data, unrelated private projects |

**Public repos get extra care.** A screenshot of a different private product does not go on a public issue; use a sample or describe it. Test data that only looks real still gets masked.

## Commands

```bash
launch_cli.py mask <image> --rect x,y,width,height [--rect ...]   # solid cover in image pixels, written to a new file
launch_cli.py redact <text file>                                  # known secret and personal formats, written to a new file
launch_cli.py shrink <images...>                                  # smaller files, after masking
github_cli.py upload-image {owner} {repo} <files...> --prefix ... # then paste the returned markdown into the body
```

Originals are never changed. Upload only the masked copies. Blur is not used, because blurred text can sometimes be recovered. `mask` does not handle animated GIFs: fix the mockup or test data and record again.

## Logs

Run `redact`, read the result, and quote only the lines that matter, inside a collapsed block:

```markdown
<details><summary>Failing run: 3 lines around the error</summary>

(lines)

</details>
```

Say which command or run it came from. Link the CI run instead of pasting a long log. A GitHub comment holds about 65,000 characters.

## When to ask

Do not ask "should I include the images?" Ask only when:

- You cannot mask it with confidence, or the sensitive part is the point of the image. Leave out that one item and ask about it. Post the rest.
- The image has no path you can find.

Approval gates that a skill already has still apply to the post itself. In the final message, say how many items you attached and what you masked, by kind and not by value. In a private repo uploaded images do not render for readers, so say so if `private_warning` comes back.
