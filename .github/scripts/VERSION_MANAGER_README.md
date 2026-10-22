# Version Manager Documentation

## Overview
This script manages the version centrally across many project types.
It works with GitHub Actions to manage and sync versions automatically.

## Synced files by project type

### Spring (`spring`)
- **Synced file**: `build.gradle`
- **Version format**: `version = "x.y.z"` or `version = 'x.y.z'`
- **Notes**: every nested build.gradle file is updated too

### Flutter (`flutter`)
- **Synced file**: `pubspec.yaml`
- **Version format**: `version: x.y.z`
- **Notes**: the standard version file of a Flutter project

### React/Node.js (`react`, `node`)
- **Synced file**: `package.json`
- **Version format**: `"version": "x.y.z"`
- **Notes**: kept in sync with the npm/yarn package version

### React Native (`react-native`)
- **iOS synced file**: `ios/*/Info.plist`
  - **Version format**: `<key>CFBundleShortVersionString</key><string>x.y.z</string>`
- **Android synced file**: `android/app/build.gradle`
  - **Version format**: `versionName "x.y.z"`
- **Notes**: iOS wins when it exists; otherwise the Android file is used

### React Native Expo (`react-native-expo`)
- **Synced file**: `app.json`
- **Version format**: `"expo": { "version": "x.y.z" }`
- **Notes**: the version file of an Expo managed project

### Python (`python`)
- **Synced file**: `pyproject.toml`
- **Version format**: `version = "x.y.z"`
- **Notes**: the standard version file of a Python project (FastAPI, Django and so on)

### Basic/other (`basic` or anything else)
- **Synced file**: only `version.yml`
- **Version format**: `version: "x.y.z"`
- **Notes**: when there is no specific project type, only version.yml is managed

## How it works

### Version sync
1. Compare the version in `version.yml` with the project file
2. Sync both to the higher version automatically
3. Update every related file at once

### Version increment
`increment` takes the bump size with `--bump`. When omitted it is `patch` (the original behavior).

- **Patch**: bump the third number (x.y.Z -> x.y.Z+1) — `--bump patch` or omitted
- **Minor**: bump the second number and reset patch to 0 (x.Y.z -> x.Y+1.0) — `--bump minor`
- **Major**: bump the first number and reset the rest to 0 (X.y.z -> X+1.0.0) — `--bump major`
- **version_code**: always +1, whatever the bump size

When `metadata.template.options.semver_auto` in `version.yml` is `true`, the release workflow
classifies the commit titles (`changelog_manager.py classify-bump`) to pick this value.
When the key is missing or `false`, it is always `patch`. See `docs/VERSION-CONTROL.md` for the full rules.

## Commands

```bash
# show the current version (syncs too)
./version_manager.sh get

# increment the version (patch by default)
./version_manager.sh increment

# choose the bump size
./version_manager.sh increment --bump minor   # 1.2.3 -> 1.3.0
./version_manager.sh increment --bump major   # 1.2.3 -> 2.0.0

# set a specific version
./version_manager.sh set 1.2.3

# sync only
./version_manager.sh sync

# validate the version format
./version_manager.sh validate 1.2.3
```

## GitHub Actions workflow

The workflow works like this:
1. Runs automatically on a push to the main branch
2. Checks and syncs the current version
3. Increments the patch version automatically
4. Commits the changes and creates a tag

## Notes

- Do not change `project_types` after the first setup (the first entry is the primary type)
- The version must always keep the `x.y.z` format
- Between the project file and version.yml, the higher version wins
- If the commit message contains `[skip ci]`, the workflow does not run
