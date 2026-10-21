# PR create · read · merge · release notes fallback

> When to read: when creating, reading, commenting on, closing or merging a PR, or when filling release notes into a release PR body yourself.

Commands have the form `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py ...` (SKILL.md "Find the scripts").

## Create a PR

Detect the current branch name automatically and create the PR.

**Before creating the PR, always check that the branch exists on the remote (prevents 422 errors with non-ASCII branch names):**

```bash
HEAD_BRANCH=$(git branch --show-current)
git ls-remote --heads origin "$HEAD_BRANCH" | grep -q "$HEAD_BRANCH" || echo "Branch not on the remote. Run git push first."
```

Always give `head` as `owner:branch` (prevents 422 errors with branch names that contain non-ASCII text):

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py create-pr {owner} {repo} "{title}" "{PR body file path}" --head "{owner}:{head_branch}" --base {base_branch}
# Positional arguments (… "{title}" "{body}" "{owner}:{head}" {base}) also work, but the order is often wrong, so prefer the flags
```

If head or base contains a space, the title landed in a branch slot, so it is rejected with `code: argument_order`.

For a work PR, `{base_branch}` is the **development (release source) branch**: `metadata.development_branch` in `version.yml` (old name `deploy_branch`), else `develop` (or the default branch for a single-branch repo with no development branch on the remote). Release PRs to the default (deploy) branch (`main`) are created by `/pro-changelog-deploy`, not by this recipe. If the user names a base, use it.

### PR title rule (required)

If the branch name has the form `YYYYMMDD_#number_title`, extract the number and read the title through the issue API (`get-issue`). Use as the PR title only the plain text left after **removing the leading emoji and every `[tag]`** from the issue title.

Example: issue title `❗[Bug][DevTools] SSE log stream closes at once and subscribers pile up`
→ PR title: `SSE log stream closes at once and subscribers pile up`
(Korean tags such as `[버그]` are stripped the same way.)

### PR body rule (required)

The PR body must include the related issue link. Extract the issue number from the branch name (`YYYYMMDD_#number_...`) automatically.

```
- https://github.com/{owner}/{repo}/issues/{issue_number}
```

## List PRs

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py list-prs {owner} {repo} --state open
# Include closed PRs: --state closed or --state all
```

Output JSON: `{"count":N,"prs":[{number,title,url,state,head,base,merged_at}]}`. Whether a closed PR was merged shows in `merged_at` (null if not merged).

## PR details / comments / state / merge

`get-pr` returns a `verdict` (mergeable/blocked/computing/merged/closed); use it to check state before merging.

```bash
# PR details (mergeable_state etc.); decide mergeability from verdict
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py get-pr {owner} {repo} {pr_number}
# Add a PR comment (body file)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py add-pr-comment {owner} {repo} {pr_number} "{comment body file}"
# Edit PR body, title, state (body file optional)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py update-pr {owner} {repo} {pr_number} "{body file}" --title "New title"
# Close / reopen a PR
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py close-pr {owner} {repo} {pr_number}
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py reopen-pr {owner} {repo} {pr_number}
# Merge a PR (merge|squash|rebase, default merge). --message sets the merge commit body
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py merge-pr {owner} {repo} {pr_number} --method squash --title "Merge title"
```

If the `get-pr` `verdict` is `computing` (mergeable_state not computed yet), query again shortly. If `merge-pr` fails, tell the cause from `verdict` (failure code table in SKILL.md). **Merging and closing PRs are destructive, so run them only when the user explicitly asks.**

## Update PR release notes (CodeRabbit fallback)

When a release PR (develop→main) has no CodeRabbit Summary, analyze the commits yourself, write release notes and update the PR body. Run this for requests such as "update the release notes", "changelog fallback", "update the PR body" (Korean: "릴리스 노트 업데이트해줘", "PR 본문 업데이트").

Write the release notes in the configured `language` preference; if none is set, match the repo's existing release notes or the user's language.

1. Find the PR number (from the user, or the latest release PR via `list-prs`)
2. Collect the commits ahead of main (production)

   ```bash
   git fetch origin main 2>/dev/null || true
   git log origin/main..HEAD --pretty=format:"%H %s" | grep -v "\[skip ci\]" | head -60
   ```

3. Analyze the commit messages and write the release notes
   - `feat:` → New features / `fix:` → Bug fixes / `refactor:`·`perf:`·`style:` → Improvements / `docs:` → Docs / the rest → Other
   - Do not copy commit messages as is; rewrite them as sentences users can easily understand
4. Save the release notes body to a file, then send it as a PATCH with `update-pr`:

   ```bash
   PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py update-pr {owner} {repo} {pr_number} "{release notes file path}"
   ```
