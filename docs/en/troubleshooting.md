# Troubleshooting

Common problems and how to fix them.

---

## GitHub Actions

### Workflow does not run

**Symptom**: Pushing does not trigger the workflow

**Check**:
```
1. Check that the workflow is enabled in the Actions tab
2. Check that the branch name matches the trigger condition
3. Check whether the file is covered by paths-ignore
```

**Fix**:
```
Settings → Actions → General
→ Select "Allow all actions and reusable workflows"
```

---

### GitHub token permission error

**Symptom**:
```
remote: Permission to ... denied to github-actions[bot]
```

**Cause**: `_GITHUB_PAT_TOKEN` is missing or has insufficient permissions

**Fix**:
```
1. GitHub → Settings → Developer settings
   → Personal access tokens (Classic)

2. Generate a token
   - Scopes: check repo, workflow

3. Repository Settings → Secrets and variables → Actions
   → New repository secret
   - Name: _GITHUB_PAT_TOKEN
   - Value: [the token you generated]
```

---

### PR auto-merge fails

**Symptom**: The PR was created but not merged automatically

**Check**:
```
1. Repository Settings → General → Pull Requests
   → Check "Allow auto-merge"

2. Check whether the branch protection rule is too strict
   (required reviews, status checks, etc.)

3. Check the Organization settings
   Settings → Actions → General
   → Check "Allow GitHub Actions to create and approve pull requests"
```

---

## Version management

### Version sync fails

**Symptom**: Versions in several files do not match

**Fix**:
```bash
# Manual sync
.github/scripts/version_manager.sh sync
```

---

### Duplicate Git tag

**Symptom**: `tag 'v1.0.0' already exists` error

**Fix**:
```bash
# Delete the remote tag
git push origin :refs/tags/v1.0.0

# Delete the local tag
git tag -d v1.0.0

# Push again
git push
```

---

### Script permission error

**Symptom**: `bash: permission denied`

**Fix**:
```bash
chmod +x .github/scripts/version_manager.sh
chmod +x .github/scripts/changelog_manager.py
git add .github/scripts/
git commit -m "fix: add execute permission to scripts"
```

---

## Changelog

### Changelog is not generated

**Symptom**: CHANGELOG is not updated even after the PR is merged

**Check**:
```
1. Check that the release PR was opened as develop → main
   (if the head is not develop, the whole pipeline is skipped)

2. Check that the PR was newly opened
   (the only trigger is opened, so pushing again to an existing PR does not re-run it)

3. Check the changelog provider in version.yml
   - coderabbit (default when unset): CodeRabbit app installed + Summary written
   - github-ai / openai family / commit: that provider's requirements are met

4. Check the Secret settings
   - _GITHUB_PAT_TOKEN (common)
   - MODEL_API_KEY (when the provider is openai/gemini/claude)

5. In the Actions log, check which provider the fallback-summary job finished with
```

> Thanks to the provider ladder (selected provider → github-ai → commit), the release notes are never left completely empty. See [Changelog automation](./changelog-automation.md#release-note-provider-ladder) for details.

---

### Summary parsing fails

**Symptom**: `Could not parse CodeRabbit summary`

**Fix**:
```
1. Check the CodeRabbit Summary in the PR comments
2. Check that the HTML format is not broken
3. You can update the CHANGELOG manually:
   python3 .github/scripts/changelog_manager.py generate-md
```

---

### After upgrading from an old version, the first release PR fails with `invalid choice: 'ai-summary'` (#661)

**Symptom**: You re-integrated a repository that was originally integrated with an old generation (v0.x to 2.x) using the latest version, then opened the first release PR (develop → main). The old workflow (`PROJECT-AUTO-CHANGELOG-CONTROL` or `PROJECT-COMMON-RELEASE-PUBLISH`) calls the `ai-summary` subcommand of `changelog_manager.py` and fails.

**Cause**: The new `RELEASE-CHANGELOG` uses `pull_request_target`, so it runs with the **definition on the base (main)**. For the first PR right after re-integration, main does not have it yet, so it does not run and only the old workflow left on develop runs. But re-integration replaced `changelog_manager.py` with the new one, so the `ai-summary` that the old workflow called no longer exists.

**Fix (two-step transition)**
1. For this one transition deploy, do not delete the old workflow. Handle it **together with the old scripts (`changelog_manager.py`, `version_manager.py`, `truncate_release_notes.sh`)**. If you delete only the old workflow, no workflow runs at all, and version finalization and the changelog update are both skipped.
2. Delete the old workflow **from the next deploy after** the new workflow has reached main. When the wizard finds an old file such as `RELEASE-PUBLISH`, it does not touch it automatically and only prints a notice.

## PR Preview

### Build fails

**Symptom**: Error after `@projectops server build`

**Check**:
```
1. Check the Actions log
2. Check the Dockerfile path (./Dockerfile by default)
3. Check the Secrets settings:
   - SERVER_HOST
   - SERVER_USER
   - SERVER_PASSWORD
   - DOCKER_REGISTRY_URL
   - DOCKER_USERNAME
   - DOCKER_PASSWORD
```

---

### Health Check fails

**Symptom**: "Health check failed" after the deployment completes

**Fix**:
```yaml
# Check the Health Check settings in the workflow
env:
  HEALTH_CHECK_PATH: '/actuator/health'  # Spring
  # or
  HEALTH_CHECK_LOG_PATTERN: 'Started .* in [0-9.]+ seconds'
```

**Enable Actuator in Spring**:
```gradle
// build.gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

---

### Branch not found from the Issue

**Symptom**: "브랜치를 찾을 수 없습니다" (Korean tool message: "Branch not found")

**Check**:
```
1. Check that the Issue Helper comment exists
2. Check that the branch has been pushed:
   git branch -r | grep [branch name]
3. Check that the ISSUE_HELPER_MARKER value is correct
```

---

### Container is not removed

**Symptom**: The container remains after the Issue/PR is closed

**Manual removal** (Synology SSH):
```bash
# Remove the container
docker stop project-pr-123
docker rm project-pr-123

# Remove the image
docker rmi registry/project-pr-123:latest
```

---

## SSH + Docker deployment

> The deployment engine is not tied to a specific vendor. It works the same on any server you can reach over SSH, such as a Synology NAS, AWS EC2, or a generic Linux host. See the [SSH+Docker deployment guide](../SSH-DOCKER-DEPLOYMENT-GUIDE.md) for details.

### SSH connection fails

**Symptom**: `Connection refused` or `Permission denied`

**Check**:
```
1. Enable the SSH service on the server
   (On Synology: Control Panel → Terminal & SNMP → enable SSH service)

2. Check that the auth method (SSH_AUTH_METHOD) and the Secret match
   - password → SERVER_PASSWORD
   - key      → SSH_KEY (the entire contents of the .pem file)

3. Check the Secrets values
   - SERVER_HOST: IP or domain
   - SERVER_USER: login account

4. Check that SSH_PORT in the workflow matches the server's actual SSH port
   (the template default is 2022, not 22 — change it to fit your server)

5. Allow that SSH port in the firewall
```

---

### Docker registry authentication fails

**Symptom**: `unauthorized: authentication required`

**Fix**:
```bash
# SSH into the deployment server and test the login directly
docker login [REGISTRY_URL] -u [USERNAME] -p [PASSWORD]
```

For workflows that use DockerHub, check the `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` Secrets.

---

## Flutter

### iOS build fails

**Symptom**: Provisioning profile error

**Check**:
```
1. Check the APPLE_PROVISIONING_PROFILE_BASE64 value
2. Check that the Profile has not expired
3. Check that the Bundle ID matches
```

---

### Android signing error

**Symptom**: `keystore was tampered with`

**Check**:
```
1. Check the RELEASE_KEYSTORE_BASE64 encoding
   base64 -w 0 keystore.jks > keystore_base64.txt

2. Check that the passwords are correct
   - RELEASE_KEYSTORE_PASSWORD
   - RELEASE_KEY_PASSWORD
```

---

## Organization settings checklist

When automation does not work in an Organization repository:

```
Settings → Actions → General
├── ✅ Allow all actions and reusable workflows
├── ✅ Allow GitHub Actions to create and approve pull requests
└── ✅ Read and write permissions

Settings → General → Pull Requests
├── ✅ Allow auto-merge
├── ✅ Allow squash merging
└── ✅ Automatically delete head branches
```

---

## Debugging

### Check the Actions log

```
GitHub → Actions tab → click the failed workflow
→ Expand each Job to see the detailed log
```

### Diagnose version file state

```bash
# Check the state of all version files (read-only, does not change files)
.github/scripts/version_manager.sh get

# Validate the version format
.github/scripts/version_manager.sh validate 1.2.3

# Actual sync (modifies files — there is no preview option)
.github/scripts/version_manager.sh sync
```

> ⚠️ `version_manager` does not support options such as `--dry-run`. `sync` always modifies files, so use `get` if you only want to see the state.

### Run a workflow manually

```
Actions → the workflow → Run workflow
→ Trigger it manually to test
```

---

## Getting help

If the problem is not resolved:

1. Search [GitHub Issues](https://github.com/Cassiiopeia/projectops/issues)
2. When creating a new issue, include:
   - The full error message
   - The Actions log (remove sensitive information)
   - The project type
   - Steps to reproduce
