# Contributing

A short version of how to take an issue and send a pull request. The full guide (setup, checks, commit format, code conventions) is [CONTRIBUTING.md](https://github.com/Cassiiopeia/projectops/blob/main/CONTRIBUTING.md) on GitHub.

## Claim an issue

Issues labeled `good first issue` or `help wanted` can be claimed with a comment, so two people do not fix the same thing.

| Comment (on its own line) | What happens |
|---|---|
| `/assign` | A bot assigns the issue to you, or tells you who already has it |
| `/unassign` | You give the issue back |

- If no pull request is linked within **7 days**, the assignment is released and the issue is free again (a daily job checks this).
- For anything bigger (a new project type, a new workflow, a behavior change), open an issue first and wait for a maintainer to confirm the direction.
- Questions go to [Discussions](https://github.com/Cassiiopeia/projectops/discussions), not issues.

## Open a pull request

1. Open the pull request against **`develop`**, not `main`. `main` only takes release PRs.
2. Write `Fixes #<number>` in the description so the PR is linked to the issue.
3. Run the checks before you push:

```bash
npm test
python3 -m pytest scripts/tests/ .github/scripts/test/ -q
```

From a fork, any branch name works. Write commit messages and the PR title as Conventional Commits (`fix: ...`, `docs: ...`); the maintainer rewrites the title into the project format when merging.

## Related pages

- [Branch naming](./branch-convention.md): the `YYYYMMDD_#number_title` format the maintainer's automation uses
- [Workflow comment style](./workflow-comment-guidelines.md): how workflow files are commented
- [Translating](../TRANSLATING.md): add a language by adding files
