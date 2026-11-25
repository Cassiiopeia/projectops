# Brain server (provisioner) contract

A provisioner is a brain server that can create a team brain for a project on request. `/pro-gbrain add --mode team`
uses it when the private registry declares one; without it the skill prints the manual server steps.

## Registry entry (private, never in a repo)

In `~/.projectops/config/config.json` → `project-blueprint` → `infra.brains`, one entry with `kind: "provisioner"`.
Values below are placeholders. Write it with `gbrain_cli.py registry add-provisioner --name brain-server --base-url
https://brain.example.com/api --credential brain-server-admin` (plan first, then `--apply --yes`), or copy it from another
machine with `registry export --out FILE` there and `registry import --file FILE` here (secret-looking keys are dropped,
existing values are kept, `config.json` is backed up first).

```json
"brain-server": {
  "kind": "provisioner",
  "provisioner": {
    "type": "control-tower",
    "base_url": "https://brain.example.com/api",
    "auth_header": "X-API-Key",
    "credential": "brain-server-admin",
    "credential_field": "token",
    "supports_dry_run": true,
    "server": "brain-host",
    "sync": {
      "root": "~/gbrains",
      "database_host": "127.0.0.1",
      "database_port": 15432,
      "sslmode": "require",
      "scheduler": "glob",
      "embedding_model": "provider:model",
      "embedding_dimensions": 1024
    }
  }
}
```

| Key | Meaning |
|---|---|
| `type` | Client to use. `control-tower` speaks the HTTP contract below |
| `base_url` | API root (https; a local address only for tests) |
| `auth_header` | Header carrying the admin key (default `X-API-Key`) |
| `credential` / `credential_field` | Credential store entry (`config-rules.md` §9) holding the admin key. A name, never the key |
| `supports_dry_run` | Set only when the server implements `dry_run`; otherwise the client never sends it (an older server could create for real) |
| `server` | Name of the host in `infra.servers`, copied into each team brain entry |
| `sync.root` | Folder on the syncing machine holding one folder per project (default `~/gbrains`) |
| `sync.database_*` | How the syncing machine reaches the brain database (often an SSH tunnel) |
| `sync.scheduler` | `glob`: an existing hourly job already runs `<root>/*/sync.sh`; otherwise the skill tells you to add one |
| `sync.embedding_*` | Embedding settings for the writer config; default: the user's own GBrain config |

After `add`, the skill writes (missing keys only, backup first):

- `infra.brains.<project>-team`: `engine`, `kind: team`, `database`, `mcp_url`, `mcp_server_name`, `service`, `port`,
  `server`, `provisioned_by`, `write` (`sync` or `direct`), `sync_script` (sync only).
- `projects.<project>.knowledge`: `enabled`, `brain`, `sync` (`repo-commit` or `direct-write`), and for sync `path`, `source_id`.

## HTTP contract

All calls send the admin key in `auth_header`. Bodies are JSON. Errors answer non-2xx with
`{"success": false, "code": "...", "error": "...", "next_step": "...", "steps": {...}}`; the client shows `code`,
`error` and `next_step`.

| Call | Request | Success body |
|---|---|---|
| Create or adopt | `POST /gbrain/teams` `{"project": "<key>"}` | `{"brain": {...}, "steps": {...}, "writer_secret": {...}}` |
| Preview | `POST /gbrain/teams` `{"project": "<key>", "dry_run": true}` | `{"dry_run": true, "plan": {...}, "brain": {...}}`, changes nothing |
| List | `GET /gbrain/teams` | `{"brains": [{...}]}` |
| One | `GET /gbrain/teams/<key>/status` | `{...brain fields}` |
| Issue a token | `POST /gbrain/tokens` `{"brain": "<key>", "name": "<label>", "scope_preset": "read_only" \| "read_write"}` | `{"token": {"id", "name", "scopes"}, "secret": "...", "mcp_url", "mcp_server_name"}` |
| Revoke | `POST /gbrain/tokens/<id>/revoke` `{"brain": "<key>"}` | `{"token": {...}}` |

`brain` fields: `project`, `mcp_url`, `mcp_server_name`, `database_name`, `writer_role`, `service_name`, `port`,
`is_healthy`, `service_state`. `writer_secret` (`name`, `database`, `password`, optional `sync_connection_url`) appears
only when the writer role was created by this call; the client stores it in `<sync root>/<project>/.writer-role.json`
(600) and never prints it.

### Server rules (what makes the flow safe to repeat)

1. **Idempotent create.** Calling create again for an existing brain succeeds and changes no data.
2. **Adopt, never drop.** An existing empty or unprepared database is prepared in place. A database with data the server
   cannot classify is refused with a stable code (e.g. `team_database_not_empty_unknown`). The server never drops a
   database, role, schema or table.
3. **Grants every time.** Writer role privileges are re-applied on every create, so a lost grant heals with `repair`.
   An existing writer password is not rotated unless asked.
4. **Stable codes.** Every failure has a `code`, a message, a `next_step` and the `steps` finished so far.
5. **Scoped member tokens.** `scope_preset: read_only` tokens can search but not write (sync team brains);
   `scope_preset: read_write` tokens can also write pages (direct team brains, where every member writes). A server that
   does not support `read_write` answers non-2xx with `code: invalid_scope_preset`; the client then tells the admin to
   issue the key by hand. Revoked tokens answer 401 on the next request.
6. **Write tools on request.** A server may list write tools only after `request_tools` asks for them; `verify` asks
   before probing, so the result reflects the token's scope, not the advertised surface.

## Plugging in your own server

Implement the calls above (any language), add the registry entry, store the admin key with
`python3 ~/.projectops/bin/projectops_cli.py launch cred set --name <credential> --secret-field token --prompt`,
then run `gbrain_cli.py status` (lists your brains) and `plan --mode team` in a repo. A different API shape needs a new
`type` in `scripts/gbrain_ops/provisioner.py` with the same methods (`create`, `list_brains`, `status`,
`issue_token`, `revoke_token`; `issue_read_only_token` is a read-only shortcut).
