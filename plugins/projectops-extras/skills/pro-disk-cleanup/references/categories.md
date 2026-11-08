# Categories and tiers

The location list itself lives in `scripts/disk/catalog.py`; `scan` prints the one for this OS. This page explains the tiers.

## Three tiers

| Tier | Meaning | When it may be cleared |
|---|---|---|
| `safe` | Comes back by itself: a build, `pub get`, `npm install` or a download recreates it | After one confirmation for the whole tier. A general "clean everything" counts |
| `decide` | Costly or personal to lose: in-progress work, emulator data, slow-to-rebuild global caches, your own files | Only when the user names the item, with an age threshold for `aged` locations |
| `keep` | Reported only: virtual mounts, this skill's own backups | Never by this skill |

Worktrees follow the same tiers: build output in idle worktrees is `safe`; a closed-issue worktree is cleared after the
issue is confirmed closed on GitHub; an open-issue or issue-less worktree is `decide`.

## Locations

Paths differ per OS and per install; `scan` prints the resolved path for this machine. Tool caches follow the tool's
own environment variables when set (`GOMODCACHE`, `GOCACHE`, `ANDROID_HOME`, `XDG_CACHE_HOME`, ...).
OS cache folder below means `~/Library/Caches` (macOS), `%LOCALAPPDATA%` (Windows), `~/.cache` (Linux).

| Group | Keys | Tier | Kind |
|---|---|---|---|
| JavaScript | `npm`, `pnpm`, `yarn`, `bun` | safe | tool |
| Python | `pip`, `uv`, `conda` | safe | tool |
| Go | `go-build` (safe), `go-modules` (decide) | — | tool |
| JVM | `gradle-caches`, `gradle-wrapper`, `maven` | decide | aged |
| Rust | `cargo-registry` | decide | aged |
| Dart / Flutter | `pub-cache` | decide | info |
| IDEs | `jetbrains-caches`, `vscode-cached-data`, `vscode-extension-downloads` | safe | aged |
| Android | `android-system-images`, `android-avd` | decide | info |
| Xcode (macOS) | `derived-data`, `ios-device-support`, `xcode-archives` (decide, aged); `xcode-previews`, `simulator-caches` (safe, aged); `simulators-unavailable` (safe, tool) | | |
| macOS | `cocoapods`, `homebrew` (safe, tool); `trash` (decide); `core-device-fs`, `docker-desktop-disk` (keep) | | |
| Windows | `temp`, `crash-dumps` (safe, aged); `docker-desktop-disk`, `store-app-data` (keep) | | |
| Linux | `thumbnails` (safe, aged); `trash` (decide) | | |
| projectops | `projectops-browser` (safe, browser); `projectops-backups` (keep) | | |

Anything else large under home shows in `largest` with `relation: unclassified` and is decide tier. Cloud-sync folders
(`is_cloud_sync`: iCloud, OneDrive, Dropbox, Google Drive) are keep tier: deleting there deletes on every device.
To add a tool for everyone, add a `Location` to `scripts/disk/catalog.py` with paths for all three OSes.

Kinds: `tool` runs the tool's own clean-up command, `aged` removes sub-folders whose newest change or access is older
than `--older-than-days`, `browser` removes only cache folders inside profiles whose browser is not running, `info` is
reported only (clear `info` items by the tool named in `note`, after the user names them).

A location whose `is_whole_folder_reclaimable` is false (unavailable simulators, browser caches, temp) is left out of
`totals_gb`; its dry run gives the real number.

## Lessons behind the rules (#1091)

- A folder that showed 46 GB was a device mount using no local disk → mounts and other volumes are not counted.
- Removing a container first turned its volume into "unused" and the next prune deleted it → the volume list is fixed first.
- A mobile `android/build` was tracked by git → tracked folders are never removed as build output.
- An issue-less worktree held about 1,500 lines of uncommitted work and looked like a stale one → real changes are listed
  separately from generated ones, and every removal backs up first.
- Closed state came from guesses → only GitHub's issue state counts.
- Measuring a folder updates its access time → age is read before size.
