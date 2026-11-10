# Providers: which tool draws, and in what order

> When to read: `providers` returned `ask_priority`, a run failed with a provider code, or the user names a tool.

## Built in

| Name | Tool | Account | Transparency | References | Notes |
|---|---|---|---|---|---|
| `codex` | OpenAI Codex CLI (`codex exec`) | ChatGPT subscription (Plus or higher). API-key login is refused unless `image.require_subscription` is `false` | Real alpha | Attached (`-i`) | Best quality and prompt-following in tests. Saves to `./out/` itself |
| `antigravity` | Google Antigravity CLI (`agy -p`) | Free or Pro Google account | None: it paints a fake checkerboard. The CLI asks for a flat key color and removes it | Not attached; it is told to open `./ref/` | Returns JPEG in its own folder; the CLI collects the newest one after the run settles |
| `claude-vector` | You (the agent) write SVG | none | Real alpha | none | Last resort: simple icons, geometric shapes, diagrams. Weak for scenes and characters |

Default order: `codex` > `antigravity` > `claude-vector`. `run` without `--provider` uses the first ready one.

Both built-in tools run with approvals off (Codex `--dangerously-bypass-approvals-and-sandbox`, Antigravity
`--dangerously-skip-permissions`): headless runs cannot answer a permission prompt and would stop without an image.
They work in a scratch run folder outside the repo. To restrict them, override `image.providers.<name>.args`.

## First use: ask once

When `providers` says `ask_priority`, ask the user once with your agent's choice prompt (AskUserQuestion in Claude Code; a numbered list elsewhere) which tools to use and in what order,
showing only the ready ones (`ready_in_order`). Save the answer in `~/.projectops/config/config.json`:

```json
{ "image": { "priority": ["codex", "antigravity", "claude-vector"] } }
```

## When a run fails

| `code` | Do |
|---|---|
| `provider_missing` · `not_subscription` | Move to the next provider in the priority list with `--provider <next>`. Tell the user in one line which tool made the image |
| `quota_exhausted` | The tool's own log shows a 429 or quota error. `quota.reset_in` says when it resets: under an hour, retry once after 1-2 minutes; longer (the Antigravity free image quota is weekly, measured 166h), move to the next provider now and tell the user when it comes back |
| `image_unavailable` | The tool said it cannot generate images, with no quota trace. Move to the next provider |
| `timeout` · `no_image` | Run once more with the same provider (background), then move on |
| `agent_draws` (claude-vector) | Write the SVG yourself, render it to PNG (`pro-launch render`, or a browser screenshot), then `check` |

## Adding a tool (no code change)

Any command-line tool that can turn a prompt into an image file can be added under `image.providers`:

```json
{
  "image": {
    "providers": {
      "my-tool": {
        "kind": "command",
        "command": "my-image-cli",
        "args": ["--prompt-file", "{prompt_file}", "--out", "{out_file}", "--size", "{size}", "{refs}"],
        "supports_alpha": false,
        "attaches_references": true,
        "timeout_seconds": 600
      }
    },
    "priority": ["codex", "my-tool", "antigravity", "claude-vector"]
  }
}
```

Placeholders: `{prompt_file}` `{prompt_text}` `{run_dir}` `{out_dir}` `{out_file}` `{size}` `{timeout_seconds}`;
a lone `"{refs}"` expands to every reference path. If the tool writes somewhere else, list that folder in
`harvest_globs` (e.g. `"~/my-tool/output/*.png"`); the CLI collects the newest file created during the run.
The same keys under `providers.codex` or `providers.antigravity` override the built-in values (e.g. a different model).
