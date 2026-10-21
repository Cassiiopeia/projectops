# Phase 0 — Brainstorming (what to build and why)

A short design conversation in CREATE mode that comes **before Phase 1 slot extraction**. When the user says "make a skill", do not jump straight to filling slots. Think through "is this skill really needed / what shape works best" together once.

## Why this phase exists

Once built, a skill is called **tens or hundreds of times**. Skip five minutes of design up front and a skill with the wrong scope and wrong boundaries wastes the user's time on every call.

To borrow from the brainstorming skill: **"this skill is simple, so it needs no design" is an anti-pattern.** Even a skill that looks simple should go through a 1~2 minute scope conversation. It does not need to be long, but do not skip it.

## HARD GATE — no file writes before Phase 0 agreement

Until all 4 Phase 0 exit conditions (scope, approach, boundaries, overlap) are **agreed**, you may not enter Phase 3 (writing SKILL.md, scripts, config). No exceptions.

> **Why this is a gate**: once you start writing files, sunk cost appears. The agent thinks "it is half written, let's keep going", and the user thinks "deleting it feels wasteful". The skill ends up finished with the wrong scope. Nothing written to disk is **the cheapest moment to change course**.

When unsure, confirm once more with the user: "May I start writing files now?"

## Exit conditions

When the user agrees on the 4 items below, Phase 0 ends → enter Phase 1 (slot extraction):

1. **Scope is right** — neither too big (needs decomposing) nor too small (does it even need a skill?)
2. **1 approach chosen** — the user picked one of 2~3 alternatives
3. **Boundaries are clear** — "this skill does X but not Y" can be said in one line
4. **Relation to existing skills is settled** — you looked for similar skills, and decided what to do about any overlap

## Procedure

### Step A — Explore the project context

Before asking anything, the agent checks first:

- Which skill directories already exist? (`ls ~/.claude/skills`, `ls <plugin>/skills`)
- Which tools and workflows did the user mention in the recent conversation?
- Is there an existing skill with a similar name or function?

Share what you found briefly with the user. Example:
> "There are already `jenkins`, `pg-query` and `ssh-remote-execute` skills. How does the one we are building relate to them?"

### Step B — Scope check

Decide which of these the requested skill is:

| Verdict | Example | Action |
|------|------|------|
| ✅ **Right** | "Look up MRs, branches and changed files on the in-house GitLab, and create MRs" | Go to Step C |
| 🚫 **Too big** | "Integrated management of GitLab + Jenkins + Redmine + the deploy pipeline" | "This looks like it should be split into several skills. In what order should we build them?" — decompose first |
| ⚠️ **Too small** | "Wrap a single curl call in a skill" | "This is a one-line bash command. Is there a reason to make it a skill? (reuse frequency? sharing with the team?)" — reconfirm why a skill is needed |

### Step C — Present 2~3 approaches

bad: write the user's exact words into SKILL.md as a single design right away.

good: present **2~3 ways to solve the same need in different shapes**, with a recommendation.

Example (for a GitLab skill request):

```
There are a few ways to design this skill. My recommendation first:

Recommended) General-purpose CLI script + alias mapping
  — put every action (branches/mr-info/mr-create/...) in gitlab_api.py,
    and keep repo aliases in config.json.
  — Pros: managed in one place, easy to test
  — Cons: the script can get long

2) Split by function (gitlab-mr, gitlab-branch, gitlab-file, etc.)
  — split it into several skills
  — Pros: each skill is small with clear triggers
  — Cons: duplicated config and shared logic

3) Hybrid of an existing git CLI wrapper + the GitLab API
  — mix local git commands and API calls
  — Pros: fast when the repo is already checked out
  — Cons: needs a local clone

Which way should we go? (1 is usually the cleanest)
```

**Rules:**
- Put the recommended option **first**, with one line on why.
- One line each of pros and cons per alternative.
- Explain technical terms in plain words (H5).
- Present the options in one message. After the user answers, go to Step D.

### Step D — Clarify boundaries (what it does / does NOT do)

Once the user picks an approach, agree in one line on **"this skill does X but not Y"**. YAGNI (You Aren't Gonna Need It): leave out what is not needed now, and add it later if needed.

Example:
> "This skill **only looks things up on GitLab and creates MRs**; it **does not merge or run pipelines**. Is that OK?"

This one line becomes the breakwater against scope creep (feature bloat) later.

### Step E — Check for overlap

If a similar skill exists, decide what to do:

- **Extend**: change the existing skill to add the capability (you may switch to IMPROVE mode)
- **Separate**: build a new skill, with a clear division of roles
- **Replace**: delete the existing skill and use the new one

**If this decision is postponed, overlapping triggers confuse the agent about which skill to use.**

### Step F — Sketch the action units

Each action (CLI subcommand) in the skill should have **one clear purpose**. This step does not design every action; it only decides **a rough list + one line on what each action does**. Detailed arguments and error handling belong to Phase 3.

Questions to decide:

- Can you tell "what it does" from the action name alone? (e.g. `mr-changes` ✅ / `process` ❌)
- Does each action do **one thing**? Split actions that bundle several (e.g. `sync-all` ❌ → split into `fetch` + `upload`)
- Are the dependencies between actions clear? (e.g. the flow `branches` → `mr-create-from-branch` → `mr-info`)

Write one line each and stop. Example:

```
branches <project>        — list origin branches
mr-create <project> ...   — create an MR (manual)
mr-create-from-branch     — parse the branch name and create automatically
mr-info <project> <iid>   — MR details
mr-changes <project> <iid>— summarize only the MR's changed files
file-raw <project> ...    — raw file from a given branch
```

> **Why this step is here**: if "how should we split into actions" is missing between Phase 1 (slots) and Phase 3 (writing), the agent either crams everything into one action (a giant `do-everything`) or splits too finely (`get-mr`, `get-mr-changes`, `get-mr-commits` ...) and creates duplication everywhere. Setting rough action boundaries in Phase 0 avoids confusion in Phase 3.

## Do not ask in Phase 0 (ask in Phase 1)

The purpose of Phase 0 is to agree on **what to build and why**. **How to build it** (detailed inputs/outputs, UI paths, etc.) belongs to Phases 1~2. Keep them apart:

| Phase 0 | Phases 1~2 |
|---------|----------|
| Is this skill needed? | Which authentication method? |
| Which approach is best? | Where does the config file go? |
| Relation to existing skills? | Which CLI actions to provide? |
| YAGNI — what to leave out? | What message on error? |

## Example: a real conversation flow

**User:** "Make a skill that accesses the in-house GitLab and shows MR changed files"

**Step A — Explore:**
> "Looking through skills/, there are jenkins, pg-query and ssh-remote-execute. There is no GitLab skill, so this looks like the first one."

**Step B — Scope check:** verdict "right" (neither too big nor too small) → Step C.

**Step C — Present approaches:** as in the example above. The user picks option 1.

**Step D — Boundaries:**
> "This skill **only does GitLab lookups + MR creation**; no merges, pipelines or webhooks. We can extend it later if needed. Agreed?"

User: "Agreed"

**Step E — Overlap check:**
> "Nothing overlaps with existing skills, so we can create a new one."

→ Phase 0 ends, enter Phase 1 (slot extraction).

## When you may skip Phase 0

- The user **already clearly stated the relation to existing skills, the scope and the approach**. Example: "I want a new one, not a fix to the existing gitlab skill, and I am not considering other approaches"
- IMPROVE/REVIEW mode (Phase 0 is CREATE only)

Even when skipping, the agent tells the user in one line **"Skipped Phase 0 for this reason: ~"** and enters Phase 1. Do not skip silently.
