# init — install the rules into a project

> When to read: "install my rules", "new project", "make this repo follow my style", or after an audit when there are no rule tests.

Goal: every later agent session follows the rules **without being told**, and CI blocks violations.

## 1. Current state

`detect PATH` → stacks, existing rule documents, existing rule tests. `conventions PATH check --stack <s>...` shows whether they are installed.

## 2. Install the rule documents

```
conventions PATH install --stack flutter --stack spring
```

- This creates `docs/architecture/CONVENTIONS.md` and `docs/architecture/stacks/<stack>.md` (existing files are not overwritten)
- If the status is `locally_modified`, the project has changed the rules. Do not overwrite; report only how it differs from the source
- If it is `outdated`, the source changed. Show the difference and use `--force` if the user wants

## 3. Link from the agent rule document

Add the paragraph below to `CLAUDE.md` (or `AGENTS.md` if there is no `CLAUDE.md`). If a similar section already exists, edit that section instead.
Write it in the language the project's documents use.

```markdown
## Coding rules

When writing or changing code, follow `docs/architecture/CONVENTIONS.md` and `docs/architecture/stacks/<stack>.md`.
- Before creating something new, look for something similar. Read the model file of the same layer first
- Comments hold only a one-line summary, step headers and the meaning of values. History and issue background go in commits
- When you change logic, make the comment above it match the current behavior. Do not edit comments on code you did not touch
- Never add lines to `docs/architecture/rules/*.allow` (frozen lists)
```

`prose_comment_inducing` from `rule-docs PATH` (for example "always add comments — focus on WHY", or in Korean "코드 주석 필수 — WHY 중심") invites prose comments.
Propose replacing it with the comment lines of the paragraph above. Fix `missing_references` (references to missing files) at the same time.

## 4. Model files

Using the stack document's "Choosing model files" criteria, pick one candidate per layer and show them to the user.
Once approved, add a `## Model files` section at the end of `docs/architecture/stacks/<stack>.md` with `path — one-line reason` entries.

## 5. Rule tests

```
install-tests PATH --stack flutter --module app
```

- Once per module. Existing files are not overwritten
- The test passes with zero rules. Pick the first rule from the audit results or the stack document's "First rule candidates"
- Confirm the new test actually runs in CI (run it once with that repo's test command)
- ArchUnit, import-linter and dependency-cruiser are more precise but are new dependencies — only propose them

## 6. Wrap up

Record the first baseline with `scan PATH --record`, show the list of changed files, then `/pro-commit` (type `chore`).
