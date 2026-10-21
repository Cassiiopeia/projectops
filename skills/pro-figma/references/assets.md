# Downloading assets: grouping · names · baked effects · fill values

> When to read: Phase 2, before passing the `assets` result to `download_figma_images` and right after downloading.

**`get_figma_data` does not give you images.** Icons exist in the dump only as `IMAGE-SVG` nodes,
with **no shape data at all.** However well you translate the values, the screen has no icons
unless you download the files separately.

Pass the `nodes` returned by `assets` **as is** as the `nodes` argument of `mcp__figma__download_figma_images`,
and give `localPath` **the absolute path you chose from Phase 0's `asset_dir_candidates`**.

> - Paths outside the project are rejected: `Invalid path specified. Directory traversal is not allowed.`
> - **Do not download into the evidence folder (`run_dir`).** It is excluded from tracking and will not be committed.

## What breaks when you sweep naively

| Pitfall | Measured | What the tool does |
|---|---|---|
| Download once per node | 609 downloads for what were really 135 assets | Groups them by evidence |
| Use layer names as file names | **46% are rejected** (Korean, spaces, `/`) | Builds names that pass |
| Same name means same image | 71 `Vector` nodes = **48 different images** | **Does not group** on name alone |
| Save by name | 592 of 609 piled into 45 names and **overwrote each other** | Adds a number on collision |
| `imageRef` missing for photos | The wrong image arrives | Puts it in the arguments for you |

## Assets with effects **come in larger** ⚠️

Items tagged `baked_effect` arrive with the spread **baked into the image as an SVG filter**.

> Measured: a glow shape with a `layout` of 36×34 arrived as **96×94**, 30px larger on every side.

| Mistake | Result |
|---|---|
| Squeeze it into the layout size (36×34) | The glow shrinks too and **the shape gets smaller** |
| Add the effect in code as well | **Applied twice**, so it spreads twice as far |

→ For those items, **remove the effect from the code**, keep the downloaded image size as is, and position it by **the shape's center**.
In `coverage`, classify that effect item as "implemented (included in the asset)".

## Always check after downloading

- `rename_me: true`: the original name was Korean, so **its meaning was lost.** Look at `name` and rename it
  to something meaningful. Left as `asset-976-4627.svg`, the next person cannot tell what it is.
- `certain: false`: there was no `componentId`, so it was **grouped only because the content matched.**
  Check it by eye after downloading.
- **Count the files and check for 0-byte files.** Downloads have been reported as done without actually happening.
- **If the size differs from the dump, an effect was baked in.** Handle it as in the section above.

## After placing them, sweep every fill value

**"I put in the file from the design, so it must be right" is often wrong.** Sometimes the shape is the same
and only the fill differs: you downloaded another state's version, or values got mixed while editing by hand.

```
fill="#      fill:#      stroke="#      stroke:#
```

Extract all of these and look for **values that are not in the design tokens**. Those are the candidates.

> In one real case, two of seventeen icons used values that were not in the tokens. Looking at one alone, it was hard
> to notice; it only showed up **when placed next to other icons with the same role**.
