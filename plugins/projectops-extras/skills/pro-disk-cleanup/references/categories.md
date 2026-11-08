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

| Key | macOS | Windows | Tier | Kind |
|---|---|---|---|---|
| `derived-data` | `~/Library/Developer/Xcode/DerivedData` | — | decide | aged |
| `ios-device-support` | `~/Library/Developer/Xcode/iOS DeviceSupport` | — | decide | aged |
| `xcode-archives` | `~/Library/Developer/Xcode/Archives` | — | decide | aged |
| `simulators-unavailable` | `xcrun simctl delete unavailable` | — | safe | tool |
| `simulator-caches` | `~/Library/Developer/CoreSimulator/Caches` | — | safe | aged |
| `core-device-fs` | `~/Library/Developer/CoreDevice/DeviceFS` (device mount) | — | keep | info |
| `npm` · `uv` · `pip` · `yarn` | tool clean-up | tool clean-up | safe | tool |
| `cocoapods` · `homebrew` | tool clean-up | — | safe | tool |
| `temp` | — | `%TEMP%` | safe | aged |
| `pub-cache` | `~/.pub-cache` | `%LOCALAPPDATA%\Pub\Cache` | decide | info |
| `trash` | `~/.Trash` | — | decide | info |
| `gradle-caches` · `gradle-wrapper` | `~/.gradle/...` | `%USERPROFILE%\.gradle\...` | decide | aged |
| `android-avd` | `~/.android/avd` | `%USERPROFILE%\.android\avd` | decide | info |
| `projectops-browser` | `~/.projectops/launch` cache folders | same | safe | browser |
| `projectops-backups` | `~/.projectops/backups/disk-cleanup` | same | keep | info |

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
