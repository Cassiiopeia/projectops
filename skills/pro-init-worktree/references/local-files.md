> When to read: Step 4 after creating the worktree (survey, judge and selectively copy gitignored local-file candidates). Candidate criteria, exclusion list, search commands, classification, reference checks and output format are here.

# Survey and selectively copy gitignored local files

After the worktree is created, **first survey the gitignored local-file candidates that exist in the source project**, let the agent judge whether each needs copying, then copy only those.

The goal is not to copy every file in `.gitignore` blindly. Spring, React, React Native, Flutter and other project types need different local config files, so build an inventory of candidates and record the reasons, to reduce misses that would recur.

## 4-0. Recall last time's copy set (recall): always first

The set to copy is almost the same every time for a repo. Remember the last set so you do not judge from scratch each time (#839,
memory principles in `../../references/memory-principles.md`). The memory lives in `~/.projectops/worktree/<owner__repo>.json`
as **paths only**; file contents are not stored. It is the same memory whether called from the source or a worktree (the key is the git remote).

```bash
PYTHONIOENCODING=utf-8 "{PYTHON}" "{SCRIPTS}/worktree_cli.py" recall --root "{source_root}"
```

| Response field | Meaning | What to do |
|---|---|---|
| `verdict: first_time` | No memory | Do all of 4-2 to 4-5 (`candidates` is the inventory) |
| `verdict: same` | Candidates are the same as last time | Copy only `copy_now` (4-6), skip judging |
| `verdict: changed` | New candidates appeared | Copy `copy_now`, judge **only `new_candidates`** with 4-4 and 4-5 |
| `last.skipped` | Skipped last time | Do not judge again |
| `gone` | In memory but gone from the source | Do not copy (dropped automatically on the next record) |
| `last.age_days` | How old the memory is | If old, skim `copy_now` once too |

`candidates` is the output of `git ls-files --others --ignored --exclude-standard --directory` minus the exclusion list in 4-2
and files over 1MB. A folder ignored as a whole shows as one line, such as `secrets/`.

## 4-1. Fix the source and target paths

- **Source root**: the project root you are working in (check with `git rev-parse --show-toplevel`)
- **Target (worktree) root**: the `WORKTREE_PATH` from Step 3

## 4-2. Build the candidate inventory from .gitignore

Read `.gitignore` in the source root and first build the **file/directory candidates that really exist in the source project**. Do not pick only file names you recognize; always judge from this inventory.

**Include** (all conditions must hold):
- No `!` (negation) prefix
- Not a comment (`#`) line
- Not an empty line
- The pattern is a simple path without a `**` glob, or a simple extension (around `*.yml`)

**Obvious exclusions** (drop from the copy candidates if the pattern or real path contains any of these strings):
```
build/  target/  .gradle  node_modules  Pods/  .dart_tool
Generated  generate  .last_build_id  .framework  .flx  .zip
DerivedData  XCBuildData  .class  .pyc  .log  .symbols  .map.json
.pub-cache  .pub/  migrate_working_dir  .history  .svn  .swiftpm
bin/  out/  dist/  nbproject  .sts4-cache  .springBeans
.idea  .vscode  .DS_Store  .flutter-plugins  flutter_export_environment.sh
```

> `worktree_cli.py recall` also filters Python and web caches (`__pycache__` `.pytest_cache` `.venv` `.next/` `.turbo` `.cache/` `coverage/`) and `-Worktree/` on top of this list (`EXCLUDE_MARKERS`).

## 4-3. Find files that really exist

For each candidate pattern, check whether real files exist in the source root:

```bash
# Simple path pattern (e.g. android/key.properties)
ls [source_root]/[pattern]

# Wildcard pattern (e.g. *.env, src/main/resources/application-*.yml)
find [source_root] -name "[file name part of the pattern]" \
  -not -path "*/build/*" \
  -not -path "*/target/*" \
  -not -path "*/.gradle/*" \
  -not -path "*/node_modules/*" \
  -not -path "*/Pods/*" \
  -not -path "*/.dart_tool/*" \
  -not -path "*/*-Worktree/*" \
  -type f -size -1M
```

> `-size -1M`: files over 1MB are unlikely to be sensitive config files, so they are excluded

## 4-4. Agent judgment criteria

Do not copy every found candidate right away. Classify them as `copy recommended` / `needs judgment` / `copy not recommended` with these criteria.

**Copy recommended**:
- Runtime environment config: `.env`, `.env.local`, `.env.*`, `application-*.yml`, `application-*.yaml`, `application-*.properties`
- Auth, key and signing config: `key.properties`, `*.jks`, `*.keystore`, `service-account*.json`, `firebase-key*.json`
- Platform local config: `google-services.json`, `GoogleService-Info.plist`
- Gitignored files referenced directly by build or runtime config files

**Needs judgment**:
- Project-specific `*.json`, `*.yml`, `*.yaml`, `*.properties`, `*.toml`, `*.xcconfig` files
- Local config files whose purpose is hard to tell from the name, that exist in the source but not in the worktree

**Copy not recommended**:
- Regenerable caches and build output
- IDE state files
- Dependency directories
- Logs, temporary files, large files

## 4-5. Check references

For candidates where copying is unclear, check whether project files reference them. Promote referenced gitignored files to `copy recommended`.

Example check:
```bash
rg -n "candidate_file_name|candidate_file_name_without_extension" [source_root] \
  -g '!build/**' -g '!target/**' -g '!node_modules/**' -g '!Pods/**' \
  -g '!.dart_tool/**' -g '!*.lock'
```

Reference examples:
- iOS/Flutter: `#include` in `*.xcconfig`
- Android/Gradle: signing config, `key.properties`, keystore references
- Spring: profile/import settings, `application-*.yml`, `application-*.properties`
- React/React Native/Node: dotenv/env loaders, Firebase config references

## 4-6. Compute paths and copy

For each file found:

1. **Relative path**: `absolute path` → path relative to the source root
2. **Target path** = `target_root` + `relative path`
3. **Copy**:
```bash
mkdir -p [parent directory of the target file]
cp [source absolute path] [target absolute path]
```

Always print copy/skip results with reasons:

```
✅ copied ios/Flutter/Secrets.xcconfig
reason: local build input included from ios/Flutter/Debug.xcconfig or Release.xcconfig

⏭ skipped .dart_tool/package_config.json
reason: cache file Flutter regenerates
```

## 4-6-1. Record the copy set (record): always right after copying

Record it **as the very next step** after copying. If you skip this call, the next worktree repeats the same judgment from scratch.

```bash
PYTHONIOENCODING=utf-8 "{PYTHON}" "{SCRIPTS}/worktree_cli.py" record --root "{source_root}" \
  --copied ".env,android/key.properties" --skipped ".idea/workspace.xml"
```

- `--copied`: every relative path **actually copied successfully** this time (including `copy_now`). Do not include failed copies (❌).
- `--skipped`: relative paths judged and skipped this time. Past judgments not handled this time carry over if they still exist in the source.
- **Pass paths only.** Absolute paths, `..`, `=` or line breaks are rejected with `code: bad_path`. Never pass file contents or values.
- If nothing was copied or skipped, do not record (`code: empty`).

## 4-7. Copy results and missing candidates

After copying each file, check that the target path exists. Mark the result `✅` / `❌`.

Then print again the inventory candidates that do not exist in the target worktree. This step is not treated as a failure, but the agent must give a reason for not copying each missing candidate.

Example output:
```
⚠️ Gitignored candidates not copied:
  - ios/Flutter/Secrets.xcconfig
    judgment: copy recommended
    reason: included from ios/Flutter/Debug.xcconfig
    action: recheck whether it must be copied

  - .idea/workspace.xml
    judgment: copy not recommended
    reason: IDE local state file
    action: not copied
```
