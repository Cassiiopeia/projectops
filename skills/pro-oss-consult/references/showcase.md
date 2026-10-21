# Showcase playbook (README first screen · proof of value)

Basis: caveman (about 108k stars), uv, ruff, headroom, rtk, pxpipe, context-mode, oxc, superpowers,
plus 18 Trending repos and 5 user examples (reclip · PageIndex · openship). **Numbers are as of the research date (2026-09-30).** Add the date when you quote them.

Figures in this document such as "8 or fewer" and "5MB or less" are **rules of thumb observed in the researched repos, not GitHub limits.** Use them only as
reference values for "this much gets read", not as thresholds for deducting points.

## First-screen order (before scrolling)

1. Logo or banner (if you have light and dark versions, switch with `<picture>`)
2. A one-line tagline. Contrasting with something well known is strong ("ab replacement", "Vectorless RAG")
3. The problem in one line
4. **One piece of evidence**: a before/after table, one chart, or a demo GIF
5. A one-line caption saying what was measured
6. A one-line install (`npx ...`, `brew install ...`, a download button)
7. 8 badges or fewer (rule of thumb), all clickable to verify (context-mode's company logos with `href="#"` hurt trust)

Below that: Why / comparison table / when it does not fit / docs link / contributing / license.
Move details (all options, config reference, troubleshooting) to a documentation site and link to it from the README.

## What to measure (always pair "savings" with "evidence that quality held")

| Type | Savings | Quality evidence |
|---|---|---|
| `cli` · `tool` | Run time (warm and cold separately) | Same output |
| `ai` | Input and output tokens, cost, number of turns | How many of N are correct |
| Library | Throughput, latency, bundle size | Compatibility rate |
| `template` | Manual steps removed, config files and line counts before/after, time to first deploy | First CI success rate |
| `app` | (screenshots and a feature table rather than metrics) | Store rating and downloads (with verifiable links) |

Compare AI skills against **a control that says "just be concise"**, not against "no instructions at all". caveman's early
"up to 75%" claim was challenged; it added a control, lowered the numbers and published HONEST-NUMBERS.md. Inflated numbers backfire.

## Making it believable

- Put the reproduction command **above** the table (headroom's "Proof" section)
- Commit fixed inputs and seeds. If you commit raw output snapshots, CI can recompute without API keys
- A bench script writes the table between `<!-- BENCHMARK-TABLE-START -->` and `END` in the README,
  and a chart script reads that table to build the SVG. The table and chart cannot drift apart
- Keep unfavorable results too ("The day I hide a red row is the day you should stop trusting the green ones")
- State the measurement environment, date, N and confidence interval
- Give users a command to run the A/B themselves (`caveman trial -- claude`)

## How to draw it

| Purpose | Method |
|---|---|
| Hero chart | Static SVG in light and dark versions + `<picture>` (the uv · ruff approach: one horizontal bar chart + a one-line caption) |
| Before/after | A two-column HTML table with numbers in the headers ("Normal · 69 tokens" / "Caveman · 19 tokens") |
| Demo | Commit a vhs `.tape` so the GIF can be regenerated. In the README, a GIF of 5MB or less (rule of thumb; larger loads slowly); MP4 on the docs site |
| Live numbers | CI updates `stats.json` and a shields.io `dynamic/json` badge reads it |
| Star history | A star-history chart (with dark mode support) |
| Social preview | 1280×640 PNG, under 1MB (recommended). **There is no API upload, so a person uploads it in Settings** (no API as of the research date; check whether this is still true) |

None of the researched repos uses mermaid `xychart`. Support may depend on the mermaid version GitHub renders (**the currently supported version was not confirmed; needs checking**), so do not recommend it until rendering is confirmed. Static SVG is safe.

## Where to put documentation

- **Do not recommend the Wiki.** GitHub docs: "Search engines will only index wikis with 500 or more stars that you configure to prevent public editing."
  That is, **only wikis with 500+ stars and public editing disabled** are indexed. Nothing else is (https://docs.github.com/en/communities/documenting-your-project-with-wikis/about-wikis).
  PR review and translation management are also hard. Of the 18 Trending repos, 0 actually used the Wiki and 17 had a documentation site (as of research on 2026-09-30).
- GitHub Pages + Starlight (multilingual and landing page built in), or Docusaurus · MkDocs · VitePress.
  Keep the source in `website/` or `docs/`, and run the deploy workflow only when that path changes.
- Point the About homepage at the documentation site.
