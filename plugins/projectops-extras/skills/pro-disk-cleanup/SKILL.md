---
name: pro-disk-cleanup
description: "Find and clear reclaimable disk space safely on any macOS, Windows or Linux machine and stack: read-only scan, three tiers (safe, decide, keep), closed-issue worktrees with backup, build output, caches, Docker. Use for 'disk is full', 'free up space'."
---

# Disk Cleanup

## When to use

- "The disk is full", "free up space", "how much space is left", "what is eating my disk"
  (Korean: "용량 확인해줘", "저장공간 정리", "디스크 꽉 찼어", "지워도 되는 거 지워줘")
- "Clean up the worktrees", "remove finished worktrees", "delete build folders"
  (Korean: "워크트리 정리", "끝난 워크트리 지워", "build 폴더 지워줘")
- Not this skill: creating a worktree is `pro-init-worktree`; temporary emulators and simulators are `pro-launch device gc`;
  leftover headless browsers are `pro-launch web close --stale`. Call those for their part instead of deleting by hand.

**The CLI collects facts and refuses unsafe deletes. You make the judgment.** Every deleting command returns a plan
unless you pass `--yes`. Reply in the user's language.

## Find the scripts

```bash
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
SCRIPTS="$ROOT/plugins/projectops-extras/skills/pro-disk-cleanup/scripts"
[ -d "$SCRIPTS" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops-extras/*skills/pro-disk-cleanup/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { SCRIPTS="$H"; break; }
done
[ -d "$SCRIPTS" ] || { echo "pro-disk-cleanup scripts not found. Check the projectops-extras installation."; exit 1; }
echo "PYTHON=$PYTHON SCRIPTS=$SCRIPTS"
```

The Bash tool resets its state on every call. Put the printed paths into `{PYTHON}` and `{SCRIPTS}` in later commands.
On Windows (PowerShell) run `python {SCRIPTS}\disk_cli.py ...`.

## What you want → command

Every command is `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/disk_cli.py <command> ...`. Output is always JSON (`ok`, `code`, `summary`, `next`).

| You want | Command |
|---|---|
| Free space only | `free` |
| Full read-only report: free space, every known location by size and tier, worktree summary, Docker, running builds | `scan [--roots DIR ...] [--skip-worktrees]` (1-4 minutes; run in the background) |
| Big folders under home that the known list does not cover (any tool, any stack) | `largest [--limit N]` (run next to `scan`) |
| Every worktree: repo, branch, issue number, real vs generated changes, unpushed commits, in use, last activity | `worktrees [--roots DIR ...] [--with-size]` |
| Build output inside worktrees (skips tracked, recent, in-use) | `generated` · then `clear-generated --yes` |
| Remove one worktree (backup first, branch kept) | `remove-worktree PATH --closed-issue N` or `--approved-stale`, then add `--yes` |
| Sub-folders of a cache older than N days (DerivedData, Gradle, DeviceSupport...) | `aged KEY --older-than-days N [--yes]` |
| A tool's own clean-up (npm, uv, pip, yarn, CocoaPods, Homebrew, unavailable simulators) | `tool KEY [--yes]` |
| pro-launch browser caches, logins kept, running browsers skipped | `browser [--yes]` |
| Docker facts · ordered clean-up | `docker` · `docker --volumes --images [--containers NAME ...] [--yes]` |

Worktree search roots: `--roots` > `disk-cleanup.roots` in `~/.projectops/config/config.json` > the folder that holds the current repo.
Anything touched within `--idle-hours` (default 2, `disk-cleanup.idle_hours`) is kept. Location keys and what each tier means: `references/categories.md`.

## Flow

1. **Scan, read only.** Run `scan` and `largest` (both in the background). Show the user free space and the biggest
   items grouped by tier, with real sizes. Do not delete anything in this step. A location marked `is_other_volume`
   (a device mount) uses no local disk; say so and skip it.
   The known list covers common tools on every OS, but this machine may have others. For each `largest` row with
   `relation: unclassified`, look at its name and a few entries inside and say what it probably is (a cache, a VM or
   emulator disk, a project, personal files). Unclassified folders are decide tier: never clear one without the user
   naming it, and never anything under `is_cloud_sync` (deleting a synced file deletes it on every device).
2. **Safe tier: one confirmation.** List what `safe` would clear and ask once ("clear these N GB?").
   On yes run, in this order: `clear-generated --yes` → `browser --yes` → `tool <key> --yes` for each safe tool.
   A general "clean everything" counts as yes for the safe tier only.
3. **Closed-issue worktrees.** Run `worktrees`. For every entry in `issues_to_check`, get the real state with
   `pro-github` (`get-issue`). Never decide from the branch name, folder date or a done label.
   For each closed one: `remove-worktree PATH --closed-issue N` (plan) → `--yes`. The CLI refuses a worktree that is
   in use, touched recently, locked, the main checkout, or whose branch points to another issue.
4. **Decide tier: only by name.** Open-issue worktrees, worktrees without an issue number, emulator images,
   DerivedData, Gradle caches, pub cache and Trash are cleared **only when the user names them**, never on a general
   "clean up everything". Ask with your agent's choice prompt (`AskUserQuestion` multi-select in Claude Code; a numbered list elsewhere), and for `aged` items ask for the age threshold
   ("not used in 7 days?"). An open-issue worktree the user named goes with `--approved-stale`.
   A worktree with `real_change_count > 0` and no issue: show `real_change_sample` and ask before removing; the backup
   keeps it, but the user must know it existed.
5. **Docker.** Run `docker` first and show stopped containers and unused volumes. Remove containers only by name the
   user agreed to. `docker --volumes` lists unused volumes **before** anything else is removed and deletes only that list;
   volumes that become unused after a container goes are reported in `newly_unused_volumes` and kept. Show them before
   any further volume removal. On macOS, space freed inside Docker shows on the host only after Docker Desktop reclaims
   its disk image.
6. **Report.** Free space before and after, what was removed, what was kept and why (`skip_reason`, refusal `code`),
   and where backups are (`backup_path`). Offer to post it as a comment on a related issue with `pro-github`.

## Never

- Never delete with `rm -rf` on a variable path. Every delete goes through this CLI's gate (empty, relative, home,
  top-level, outside-the-location and symlink paths are refused).
- Never touch login profiles, `.git` folders, branches, stashes or history. `remove-worktree` keeps the branch and,
  for a detached HEAD, writes `refs/disk-cleanup/<name>`.
- Never pass `--yes` to a decide-tier item the user did not name.
- Never clear the global DerivedData or Gradle cache on a blanket request; those come back slowly.
- Never back up build output, `node_modules`, app binaries or SDK archives; the backup keeps patches and small unique files only.

## Refusal codes

| `code` | Meaning | Do |
|---|---|---|
| `no_reason` | No `--closed-issue` or `--approved-stale` | Check the issue with `pro-github`, or ask the user |
| `issue_mismatch` | The branch points to another issue | Re-check which issue it belongs to |
| `in_use` · `recently_active` | A process has it open, or it was touched within the idle window | Keep it; another session may be working there |
| `main_worktree` · `locked` · `not_a_worktree` | Not a removable worktree | Leave it |
| `backup_not_private` | The backup folder could not be made private to you | Fix the folder's permissions or pass `--backup-dir` |
| `backup_failed` · `large_untracked_files` | Backup could not be verified, or files over 50 MB were not copied | Show the files; `--skip-large-untracked` only after the user agrees |
| `tool_missing` · `docker_not_running` | The tool or engine is not available | Skip that item and say so |

How "in use" is checked (`in_use_method`): macOS and Linux read every process's current folder (`lsof`, or `/proc` when
`lsof` is missing) and command line. Windows renames the folder for an instant and back; Windows refuses while any
program has a file or terminal open inside, so that counts as in use. If a result says `PROBE NOT RESTORED`, stop and
tell the user the exact rename to undo.
