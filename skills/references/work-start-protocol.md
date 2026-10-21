# Work start and Git context check protocol (detail)

The detail behind `common-rules.md` §"Work start protocol" and §"Git context check protocol". Do this before
starting work that changes code (implementation, bug fixes, refactoring, and so on).

Ask the questions below in the user's language (or the configured `language` preference). The English text is the reference wording.

## Step 1: Check the current branch

```bash
git branch --show-current
```

- **main** (production / default branch; master or similar in some repos) → **stop immediately** and confirm with the user. main is
  the deploy branch and must be updated only by releases (develop→main PR).
- **Development branch** (`metadata.development_branch` in `version.yml` (old name `deploy_branch`), or `develop` if absent) → check the repo's rules first.
  - If the repo's `CLAUDE.md` or `AGENTS.md` declares working directly on the development branch as the default (for example "work directly on develop",
    "commit straight to develop"), **pass without stopping**. Use the issue number from the user's message if there is one; otherwise
    ask at commit time.
  - If there is no such declaration, confirm with the develop question in step 3.
- **Feature branch** → step 2.

## Step 2: Check the issue number

Check whether the branch name has the form `YYYYMMDD_#number_title`.

- **Has a number** → look up that issue, print its title and state, and proceed with the work
- **No number** → confirm with the user in step 3

## Step 3: Confirmation message to the user

When the branch is main or develop, or there is no issue number, **always** ask in the format below (in a repo that
declares direct work on develop, develop already passed in step 1, so do not ask). One question at a time.

**On the main branch (⚠️ main is production — no direct commits or pushes):**
```
You are about to work on the main (production) branch. main is not a target for direct commits or pushes; it must be updated only through develop→main release PRs.
Is there an issue linked to this work?

1. Tell me the issue number → I'll compute the branch name and guide you
2. No issue → shall I create one? (go to the issue creation workflow in `/pro-github`)
3. Work directly on main anyway (exceptions such as a hotfix — confirm carefully before proceeding)
```

**On the develop branch (the default development branch):**
```
You are about to work on the develop branch.
Is there an issue linked to this work?

1. Tell me the issue number → I'll compute the branch name and guide you
2. No issue → shall I create one? (go to the issue creation workflow in `/pro-github`)
3. Work directly on develop without an issue (minor fixes and so on)
```

**On a feature branch without an issue number:**
```
The current branch [{branch name}] has no issue number.
Is there a linked issue?

1. Tell me the issue number
2. Work directly on the current branch without an issue
```

## Step 4: Handling the user's choice

| Choice | Action |
|------|------|
| Issue number given | Look up the issue → compute the branch name (`YYYYMMDD_#number_title`) → ask about a worktree → proceed |
| Create a new issue | Go to the issue creation workflow in `/pro-github` (come back after creating it and do the work) |
| Work directly on main | Allowed because the user explicitly chose it — commits may use a free format |
| Work directly on the current branch | Allowed — proceed |

## Asking about a worktree

When the issue number is confirmed and a new branch is needed, always ask.

```
Should I work in an isolated worktree, or just create the branch in the current directory?

1. Create a worktree (run /pro-init-worktree)
2. Create the branch only, in the current directory
```

## Issue filing order (for issue-based work)

1. Save the issue file locally (`YYYYMMDD_001_title.md` from `get-output-path issue`)
2. Ask the user to review the content
3. File it on GitHub after approval
4. Check the real issue number returned
5. Adding `--rename-body-file` to `create-issue ...` when filing renames the file to the real number (`YYYYMMDD_245_title.md`)
6. Commits are allowed only after the issue number is confirmed
