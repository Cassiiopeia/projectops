# Secrets in a public repo

> When to read: setting up secrets for a new repo, adding a new secret key, or looking up a current secret value.

Every repo is public, and so are its Docker images. Secrets therefore live in exactly three places: GitHub Secrets
(the original), the server's config folder (the running copy), and the NAS backup. Never in a commit, an image,
an issue, a PR, a report or a log.

## Two kinds of GitHub Secrets

| Kind | Stored as | Examples |
|---|---|---|
| Workflow secrets (what CI itself needs) | one value per secret | `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`, `SERVER_HOST`, `SERVER_USER`, `SERVER_PASSWORD`, store signing material |
| Project runtime secrets (what the app reads) | **one whole file per platform** | Spring: `APPLICATION_PROD_YML` = the entire `application-prod.yml` (including the database URL and the shared account's password); Expo / Flutter / Python: one `.env` file (`ENV_FILE`, `AI_ENV_FILE`) |

- Binary files (keystore, `.p12`, provisioning profile, `.p8` when a tool wants base64) are stored base64-encoded, name
  ending in `_BASE64`.
- **New runtime key** = edit the local file (`server/.../application-prod.yml` or `mobile/.env`), then replace the whole
  secret once (`SECRET_VALUE` from the file, `pro-github secrets set <owner> <repo> APPLICATION_PROD_YML`).
  Do not add one GitHub Secret per key: the workflow stays unchanged and the file stays the single source.
- After replacing a secret, re-run the backup workflow by hand (secret changes are not pushes, nothing runs on its own).
- Record the secret *names* (never values) in the project's registry entry, `workflow` vs `runtime_files` with the
  local file each one holds (`project-registry.md`).

## Spring configuration split

| File | Committed | Content |
|---|---|---|
| `application.yml` | yes | Shared settings; every secret is a placeholder `${ENV_NAME:default}` with a harmless local default |
| `application-dev.yml` | no (gitignored) | Local values |
| `application-prod.yml` | no (gitignored) | Production values; its original is the `APPLICATION_PROD_YML` secret |

The bootJar task excludes the gitignored files, and the build job fails if one ends up inside the jar anyway:

```bash
# Fail before pushing a public image (pattern = the same list as the bootJar exclude)
if unzip -l <module>/build/libs/app.jar | grep -E "BOOT-INF/classes/(application-prod\.yml|application-dev\.yml|firebase-service-account\.json)$"; then
  echo "secret file inside the jar"; exit 1
fi
```

## Deploy writes the file to the server

The deploy job base64-encodes each runtime secret (`::add-mask::` the encoded value), sends it over SSH and writes it:

- Path: `{volume}/config/<file>`; folder mode 700, file mode 600, owned by root.
- Write `<file>.new` first, then `mv -f` over the old one, so a running container never reads a half-written file.
- Mount the folder read-only: `-v {volume}/config:/app/config:ro`. Spring reads `./config/application-prod.yml`
  from the working folder before the copy inside the jar, so a rollback to an old image still gets current settings.
- Other files (Firebase service account, store keys) go to the same folder and are passed as paths through
  environment variables (`-e FIREBASE_KEYPATH=/app/config/firebase-service-account.json`).
- A missing required secret fails the job; an optional one is skipped with a log line.

## Backup to the NAS

A separate workflow (projectops `--secret-backup`, `PROJECT-COMMON-SECRET-FILE-UPLOAD`) writes every secret file to
`{volume-base}/<project>/github_secret/<role>/<file>` and a timestamped copy under `<role>/<timestamp>/`.
Roles: `backend`, `app`, `ai`, ... The owner customizes the installed workflow to one line per secret,
`save_secret <SECRET_NAME> <role> <file> [b64]`, so a monorepo backs up every role in one run; a secret that is not set is skipped. Reason: some keys cannot be downloaded again (an Apple `.p8` is shown once), and GitHub Secrets
cannot be read back.

## Agents looking up current values

Agents can read the server over SSH (`pro-ssh`), so the server config folder is where to check what is live
(`sudo cat {volume}/config/application-prod.yml`). Use the value for the task at hand only. Never paste it into a repo
file, an issue, a PR, a report or a chat summary; quote key names, not values.
