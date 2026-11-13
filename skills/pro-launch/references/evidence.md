# Evidence — cheaper captures · cover secrets before posting

> When to read: before attaching captures or logs to an issue, PR or report, or when captures eat a lot of tokens.
> What to attach and the review-before-posting rules are shared by every skill: [`../../references/evidence-attach.md`](../../references/evidence-attach.md).

## Save tokens

- Reading screen images is the most expensive thing. **If text can confirm it (`assert` · logs · `app tree` · E2E assertVisible), do not read the screenshot.**
- Once you build an E2E flow, save its path with `learn` so you do not write it again.
- Use the default downscaled capture (1200px long side, WebP); use the original only when truly needed, such as for pixel comparison.
- Shrink with `shrink` — WebP reduces file size and resolution reduces session tokens. You need both.

## Commands (#1082)

```bash
{PYTHON} {SCRIPTS}/launch_cli.py mask "$SHOT_DIR/01_login.webp" --rect x,y,width,height [--rect ...] [--out path]   # solid cover in image pixels > <name>.masked<ext>
{PYTHON} {SCRIPTS}/launch_cli.py redact app.log [--out path]                                                       # known secret and personal formats > <name>.redacted<ext>
{PYTHON} {SCRIPTS}/launch_cli.py shrink "$SHOT_DIR"/*.png           # long side 1200 + WebP (--max-side · --quality · --keep-format)
```

- Order: `mask` · `redact` first, then `shrink` the masked copies. Originals are never changed; upload only the new files.
- Open the masked image with Read before posting to confirm the cover sits on the secret and the point of the image survives.
