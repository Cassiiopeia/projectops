# Counting every state — what the design drew and what it left out

**Designers usually draw only the default screen.** They draw the list when it has items, and leave out empty,
failed, and long-text cases. Implementers also usually **build from that one default state.** So two skills do
the same job (#630).

| Skill | What it does with this rule |
|---|---|
| `pro-figma` | Counts whether **every** state drawn in the design was implemented |
| `pro-design-brief` | Asks the designer for states that exist in the code but are **missing from the design** |

How to read Figma itself: `figma-mcp.md`.

## 1. Count every state the design drew ⚠️

**A design draws one component in several states** — `enable`/`disable`, empty/filled,
in progress/done. In one measured file there were 479 variants such as `Property 1=disable` (`figma-mcp.md` ⑭).

If you pass only one node to `coverage`, **the other states are never counted.** When each state has its own
node, **run it for each one.**

| Commonly missed states |
|---|
| Not pressable (disabled) · pressed |
| Empty value · long text |
| In progress · done · failed |
| List with 0 items |

> In one real case, a check component was fixed on one screen only and **left as is on the other screens.**
> It had two states and only one was looked at.

## 2. A design is drawn with one set of content only

If you build to the text length in the design, **it breaks with long text.** A description wraps to two lines and
the bottom of the card is cut off, or a button ends up hidden behind the keyboard. In one measurement, 575 design
text items had a median length of 4 characters and a maximum of 35 (`figma-mcp.md` ⑮). Real data is longer.

**Also render it once with content the design does not have** — the longest text, empty values, a list with 0 items.
To render it, use `pro-launch` state staging (`web route`, `render run`); to walk through and check it, use
axis 1 (state combinations) of `pro-agent-test`.

## 3. Pull the states the code has — 5 axes

To know **what the design did not draw**, you need the list of states the code has. Pull them from the five axes
below. **No script scans the branches — the agent reads the code and writes them down.** A scan that guesses the
structure answers "none" when it is wrong, and that misleads.

| Axis | Where to pull from | Examples |
|---|---|---|
| **Data** | Async branches · empty checks · exception handling · error code lists | 0 items · 1 item · many · loading · failure · partial failure |
| **Input** | Validation · max length | Empty field · name too long · forbidden characters |
| **Environment** | Permission requests · network handling | Permission denied · offline · timeout |
| **People** | Roles · first use or not | Screen per role · first time · returning |
| **Display** | Font size · theme · width | Text 200% · dark · small phone · tablet · desktop |

- For each state, note **implemented / code exists but the screen is a placeholder / not implemented**.
- Include **only the axes that really apply to that screen.** Do not force them (a version label has no "0 items").
- Note **whether the state is reachable in the current flow** — check in the code whether the input path that
  creates the state (a UI that picks it, a value that gets saved) still exists. "Temporary" in a spec or comment
  describes the time it was written. Requesting a state that only appears in old data makes the designer draw a
  screen that never shows up (measured, #636).
- **Text sent by the server** (announcement popups, terms, server error messages) is also a state. Code search
  does not find it, so collect it from the production API or the admin screens.

> **A capture rendered by staging a state is not evidence of "this is how the app is now".** Modal overlays,
> offline-first paths, automatic retries, device width, and production settings were missing from the render,
> and it differed from the real thing in 7 places. Confirm facts on a real device or the production API.

## 4. Gap table

Putting the code's states (§3) next to the states the design drew (§1) shows the gaps.

| State | Code | Design | Action |
|---|---|---|---|
| List has items | Implemented | ✅ Drawn | Compare (`pro-figma`) |
| 0 items | Implemented (placeholder text) | ❌ Missing | **Ask the designer** (`pro-design-brief`) |
| Failure | Not implemented | ❌ Missing | Request + development issue |
| Loading | Implemented | ⚠️ Text differs between frames | **Do not fix it; raise it as a question** |

> **Do not fix** places where designs disagree with each other (the same state drawn differently in different frames).
> The designer decides which is right — raise it as a question.
