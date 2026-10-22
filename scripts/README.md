# Claude Scripts

This directory holds Python utility scripts that Claude can use across projects.

## 📦 Included modules

### `worktree_manager.py` (v1.0.0)

A script that creates and manages Git worktrees automatically.

#### Features
- Creates the branch if it does not exist (branched from the current branch)
- Handles special characters in branch names (`#`, `/`, `\` and so on) safely
- Creates the worktree in a `myapp-Worktree` folder automatically
- Skips a worktree that already exists and just prints its path

#### Usage

**Run directly:**

```bash
python scripts/worktree_manager.py "20260120_#163_Add_GitHub_Projects_template"
```

Branch names with Korean or other non-ASCII characters work too. On Windows, pass them through the
`GIT_BRANCH_NAME` environment variable or a `BRANCH_NAME_FILE` file instead of an argument, so the console encoding cannot garble them
(run the script without a branch name to see these options).

#### Output

The script prints one line per step (the messages themselves are currently in Korean):

1. The branch name it received and the folder name derived from it (`#` and `/` removed, for example `20260120_163_Add_GitHub_Projects_template`)
2. Branch check: uses the local branch if it exists, otherwise creates it from `origin/<branch>` or from the current branch
3. The worktree path, for example `/Users/.../project/myapp-Worktree/20260120_163_Add_GitHub_Projects_template`
4. Worktree creation (or a note that it already exists) and the final path

## ✅ Benefits

- 🌏 **Full support for Korean paths**: stored as UTF-8, so it is safe
- 🔄 **Reusable**: works in every project
- 📝 **Kept permanently**: not deleted, so you can keep using it
- 🤖 **Automated**: from branch creation to worktree creation
- 📚 **Documented**: every function has a docstring
