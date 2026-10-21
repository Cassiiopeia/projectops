# Phase 1 — The 6 slots and automatic inference rules

Used in CREATE mode Phase 1. Extract the information the user already gave and fill as many of the 6 slots below as you can.

## Slot definitions

| Slot | What it holds | Inference clues | May it be empty? |
|------|------------|-----------|-------------------|
| `purpose` | The skill's one-line purpose | Verb + noun in the user's words | ❌ required |
| `triggers` | Which user utterances invoke it | "use this when ~", examples of similar tasks | ❌ required |
| `inputs` | Information the user must provide (files, values, environment) | Everything the user provided | ⭕ some skills have no inputs |
| `outputs` | Shape of the result | "create a file", "run a command", "a report" | ❌ required |
| `auto_extract` | Inputs that can be extracted automatically | Values readable directly from attached material | ⭕ |
| `pain_points` | What was confusing when done by hand | "before, ~ was hard" | ⭕ OK to be empty |

> Exit condition: Phase 1 ends when the 3 required slots (purpose/triggers/outputs) have values and each of the 3 optional slots is settled as either "has value" or "OK to be empty".

## Automatic inference rules (enforces H2)

Never ask again for information the user already gave. Extract automatically from these clues:

| What the user gave | Automatically extracted values |
|----------------|------------------|
| `docker-compose.yml` content | `service_name`, `ports`, `volumes`, `environment`, `image` |
| URL (`https://...`) | domain, port, protocol, path structure |
| Screenshot | UI screen name, menu path, button position |
| Error log | failing API, error code, cause hints |
| File path (`C:/.../foo.json`) | operating system, file format, project structure |
| Natural language like "the port is 3000" | fill that slot immediately |
| Git/repo URL | project name, hosting service (GitHub/GitLab/Bitbucket) |

## How to talk with the user

Do not show the whole slot table — it is too much information and overwhelms the user. Instead:

1. Present **only a one-line summary of the intent**: "So this is a skill that does '{purpose}', is invoked in situations like '{one representative trigger}', and produces '{outputs}' — right?"
2. User says "yes" / "right" → Phase 1 ends
3. User corrects "no, X is Y" → update only that slot and confirm again

## Example

**User utterance:**
> "Make a skill that accesses GitLab and fetches MR info. Ours is the in-house gitlab.example.com, with repos like platform/git-cm and pf/api-server. When I give an MR URL, extract the changed files; when I give a branch name, it should also create the MR automatically."

**Automatically extracted slots:**

| Slot | Value |
|------|-----|
| purpose | Look up MR and branch info and create MRs on the in-house GitLab |
| triggers | "show me the MR changed files", "open an MR from this branch", pasting a gitlab.example.com URL |
| inputs | repo alias, MR URL or iid, source branch name |
| outputs | JSON (changed file list), MR creation response |
| auto_extract | MR URL → project+iid, branch name → title/target/Redmine issue number |
| pain_points | (the user did not mention any — do not ask, skip) |

**One-line summary to show the user:**
> "So this is a skill that does 'MR and branch lookups + automatic MR creation on gitlab.example.com', invoked by things like 'pasting an MR URL' or 'what branches does the repo have?' — right?"

If the answer is "yes", Phase 1 ends → go straight to Phase 3 (0 empty slots).
