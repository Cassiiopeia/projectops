# Harness: the project's art memory

> When to read: the first time in a repo (`harness` says `no_style`), or when adding a character or a kind.

One folder per repo, committed with the code so every session and teammate gets the same art rules.
Default `docs/image-harness/` (change with `image.harness_dir` in `~/.projectops/config/config.json`).
Different projects never share it, so a watercolor game and a flat-icon web app do not mix.

```
docs/image-harness/
  STYLE.md            the look: medium, line, palette, light, layout rules, never-list (required)
  characters/<id>.md  fixed look per character + its reference sheet
  kinds/<kind>.md     optional: this repo's own rules for a kind; replaces the built-in guide of the same name
  refs/               reference images STYLE.md and characters point to (small, approved ones only)
  history.jsonl       every run: prompt, references, result, approved or rejected and why (written by the CLI)
```

## First time in a repo

1. `harness --init [--character <id> ...]` creates the skeleton. It never overwrites.
2. Fill `STYLE.md` from what the app already has: open 2-4 existing images (Read) and describe them.
   If the app has no art yet, ask the user for one sentence about the look and one example they like.
3. Copy the best existing image of each kind into `refs/` (small PNG or WebP), and name it in `STYLE.md`.
4. For a character the app will show many times, make a character sheet first (`kind character-sheet`).

## Growing it

- A new kind of asset the built-in guides do not cover (a card frame, a map tile): add `kinds/<name>.md` with the
  same sections as `references/kinds/*.md`. No code change; `kind <name>` finds it.
- A user correction that applies to the future goes into `STYLE.md` or the character file in the same session.
- Keep `refs/` small. Remove a reference when a newer approved image replaces it.

Candidates (not yet approved) never go in the repo: the CLI keeps them in
`~/.projectops/image/<owner__repo>/runs/`.
