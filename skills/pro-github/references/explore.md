# Repo exploration (explore)

> When to read: for requests such as "show my repos", "explore the repo list", "fetch the README", "show {repo name} info", "explore org repos" (Korean: "내 레포 보여줘", "레포 목록 탐색해줘", "README 가져와줘", "{레포명} 정보 봐줘", "Org 레포 탐색해줘").

Commands have the form `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py explore <sub> ...` (SKILL.md "Find the scripts"). Parse the output JSON as is and decide from it.

## Phase 0: Decide the owner

1. "My repos" or no owner given → use the owner of the default repo in the config or of the current git remote. If the user wants the repo list of the actual PAT owner, ask them to name the owner.
2. Owner given ("acme-org", "acme-user", etc.) → use that owner. The default `--type auto` detects user vs org automatically.

## Phase 1: Repo list

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py explore list-repos {owner} --type auto
# If you know it is a user or an org: --type user or --type org
```

**Filtering**: if the user asks for "exclude forks", "Java only", "highest stars first" and so on, filter the result above yourself without another API call.

## Phase 2: Single repo details

When a specific repo is named, collect the four items below in order. Each call is independent; if one fails, continue with the rest.

```bash
# 2-1. Basic metadata (visibility: repo.private · repo.visibility)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py explore repo-detail {owner} {repo}
# 2-2. README
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py explore readme {owner} {repo}
# 2-3. Languages
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py explore languages {owner} {repo}
# 2-4. Last 10 commits
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py explore commits {owner} {repo} --limit 10
```

If there is a `next` value, run it as is to continue the exploration.
