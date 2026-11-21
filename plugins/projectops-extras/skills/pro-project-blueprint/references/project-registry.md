# Project registry (project map)

> When to read: at the start of any work in a repo of the owner's (look the project up before asking), after a new
> project is set up (write its entry), or when a deploy, database or secret fact changes.

The `project-blueprint` section of the private config (`{HOME}/.projectops/config/config.json`) holds a registry of
the owner's projects next to the shared infra. Shape: `../config.sample.json`; schema table:
`../../references/config-rules.md` §7. It answers "what is this project" once, so no session re-asks it.

## Two halves: shared infra, referenced by name

```
project-blueprint
├── schema_version            2
├── infra                     defined once, referenced by name
│   ├── registry              provider, username, credential?
│   ├── dns                   provider, root_domain, api_host_pattern
│   ├── traefik               server, internal_port, network, entrypoint
│   ├── servers.<name>        kind, credential, host, ssh_port, user, docker_bin, volume_base_path, timezone
│   └── databases.<instance>  engine, server, container, host, port, default_account, accounts.<name>
├── defaults                  branch names and install options picked once
└── projects.<key>
    ├── status, display_name, gbrain_entity, notes
    ├── repos[]               github, local_path, worktree_path, stacks[], branches, secrets, store
    ├── deploy                server, services[] (role, image, container, blue_green, volume_path,
    │                         runtime_config, health_path, domains[] host + backend_port)
    └── database              instance, name, account?
```

- A project never repeats a server host, a database port or an account: it names `infra.servers.<name>` and
  `infra.databases.<instance>`. Change the server once and every project follows.
- `repos` is a list because one product can span several repositories (backend and app repos); a monorepo has one.
  Branches, stacks, secret names and store ids belong to the repo, deploy and database to the project.
- `database.account` may be omitted: the instance's `default_account` applies.

## Rules

1. **References and non-secret metadata only.** A `credential` field holds a launch credential *name*
   (`pro-ssh`/`pro-launch` resolve it), never a password. `secrets` lists GitHub Secret *names*, never values.
   Tokens and passwords stay in the launch credential store or GitHub Secrets.
2. **Record only what was verified** (git remote, `version.yml`, running containers, the reverse proxy, the database
   list). Leave a field out instead of guessing; absent means unknown.
3. **Keep unknown keys.** When writing, read the whole file, change only the keys you mean to change, and write every
   other key back unchanged, including keys this document does not describe. The schema grows by adding keys.
4. **`schema_version`** is `2`. A section without it is version 1 (flat `infra` keys); see migration below.
5. The registry stays in the private config only. Never copy its values into a repo, an issue, a PR or a report.

## Look up the current repo before asking

1. `git remote get-url origin` > normalize to `owner/name` (drop `https://github.com/`, `git@github.com:`, `.git`;
   compare case-insensitively) > the project whose `repos[].github` matches.
2. No remote match > `git rev-parse --show-toplevel` > the repo whose `local_path` or `worktree_path` is that folder
   or a parent of it (worktrees live inside the `-Worktree` folder).
3. Found > use its facts (stacks, branches, container, domains, database, secret names) without asking. Resolve the
   references through `infra`. Ask only for what the entry lacks, then save the answer into the entry.
4. Not found > it is a new or unregistered project: follow the new project checklist, then write the entry.

## Write the entry when a project is set up

At the end of the new project checklist (and whenever a deploy, domain, database or secret name changes):

- Key: the short lowercase product name (`<project>`), the same one used in container, database and volume names.
- Fill what the setup decided: `repos` (from the remote and the folder), `stacks` (from `version.yml`
  `project_types` and `project_paths`), `branches` (from `version.yml`), `deploy.services` (container, image, volume,
  domains with the reverse proxy backend port, health path), `database` (instance and name), `secrets` (names only,
  split into `workflow` and `runtime_files` with the local file each one holds), `store` ids.
- Validate that the file still parses as JSON and keeps file mode 600 before finishing.

## Shared database default

One database per project on the shared PostgreSQL instance, and every project connects with the instance's one
shared owner account (`default_account`). For a single owner this is simpler to run: one password to rotate, one
account for backups and admin tools. A per-project account is an option, not a requirement: add it under
`accounts` and set `database.account` on that project. Accounts kept restricted on purpose (a sandbox role, a
read-only role) are listed with a `notes` field so nobody grants them more.

## Migration from version 1

| Version 1 (`infra.*`) | Version 2 |
|---|---|
| `docker_username` | `infra.registry.username` |
| `ssh_server_name`, `server_host`, `ssh_port`, `server_user`, `volume_base_path`, `timezone` | `infra.servers.<name>`: `credential`, `host`, `ssh_port`, `user`, `volume_base_path`, `timezone` |
| `root_domain`, `api_host_pattern`, `dns_provider` | `infra.dns`: `root_domain`, `api_host_pattern`, `provider` |
| `traefik.*` | `infra.traefik.*` plus `server` |
| `postgres.host`, `postgres.port` | `infra.databases.<instance>`: `host`, `port` |

Read either shape. When you next write the section, convert it to version 2, set `schema_version: 2` and keep any
key that has no row here.
