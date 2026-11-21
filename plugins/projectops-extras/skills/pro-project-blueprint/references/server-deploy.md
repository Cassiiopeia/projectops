# Server deploy pattern

> When to read: choosing projectops deploy answers for a server stack, preparing the NAS for a new project, or
> debugging a deploy or rollback.

Placeholders come from the `project-blueprint` section of the private config (`../config.sample.json` shows the shape).
An existing project's real values (container, volume, domains, database) are in its registry entry
(`project-registry.md`); read them there before asking.

## Topology

```
client --HTTPS--> DNS (<dns-provider>)  api.<project>.<root-domain>
       --> NAS reverse proxy (DSM, 443 and 80, certificate)
       --> Traefik  localhost:<traefik-port>  (routes by Host header)
       --> <project>-back-blue | <project>-back-green  (container port 8080, network <traefik-network>)
       --> shared PostgreSQL <postgres-host>:<postgres-port>  database <project>, shared account
```

- Self-hosted Synology NAS running Docker. One Traefik container serves every project on one fixed internal port.
- `pro-synology-expose` adds the DNS record, the two DSM reverse proxy rules (443 to Traefik, 80 forwarded with
  `X-Forwarded-Proto: http` so Traefik redirects it) and the Let's Encrypt certificate.
- One shared PostgreSQL instance; each project gets its own database, and by default every project connects with the
  instance's one shared owner account (`infra.databases.<instance>.default_account`). Simpler for a single owner:
  one account to rotate, back up and administer. A per-project account with rights on its database only is an
  option when a project needs isolation (`project-registry.md`). The password goes into `application-prod.yml`
  (and the launch credential store), nowhere else.

## Image

- Docker Hub, public: `<docker-username>/<project>-back-container` (the owner's `<project>-back...` naming; other
  services follow the same shape, e.g. `<project>-ai-container`).
- Three tags per build: `{branch}`, `{version from version.yml}`, `sha-<7-char sha>`. **Deploy by the sha tag**, so a
  deploy names one exact build.
- `workflow_dispatch` input `rollback_image_tag`: when set, skip the build and Blue-Green deploy that existing tag.
- No secrets in the image (`public-repo-secrets.md` jar check).

## Blue-Green deploy

Start from projectops `PROJECT-SPRING-NONSTOP-TRAEFIK-CICD` (blue/green swap, drain marker). The owner's deploys add
what that template does not have yet: sha-tag deploys with the rollback input, the read-only config mount, log
rotation and log archives, the check through Traefik and a deploy `concurrency` group. Add them when installing.

1. Pull the image. Find the active color (`<project>-back-blue` or `-green`); the new color is the other one.
2. Write runtime secret files to `{volume}/config/` (600, `.new` then move) and mount it read-only at `/app/config`.
3. Run the new color with Traefik labels (`Host(\`<service-domain>\`)`, entrypoint, service port), a health check
   (`/actuator/health`), `--restart unless-stopped` and log rotation `--log-driver json-file --log-opt max-size=20m
   --log-opt max-file=5` (the NAS default log driver cannot cap size).
4. Switch only when both pass: the container reports healthy **and** a request through Traefik
   (`Host` header + `X-Forwarded-Proto: https`) returns 200. On timeout, print the new container's logs and fail;
   the old color keeps serving.
5. Drain the old color (a marker file makes its health check fail, so Traefik stops sending traffic), wait for
   in-flight requests (about 25 s), archive its logs to `{volume}/logs/<container>-<yyyyMMdd-HHmmss>.log.gz`
   (delete archives older than 30 days), then remove it.
6. `concurrency` group per project with `cancel-in-progress: false`: two deploys must never touch the same color.

The workflow triggers on push to the deploy trigger branch, filtered to the stack folder (`paths: server/**`), plus
`workflow_dispatch`.

## New project on the NAS

1. Create the database on the shared PostgreSQL, owned by the shared account (`pro-ssh`); create a per-project
   account only if the project needs one.
2. Create `{volume-base}/<project>/backend` (the deploy creates `config/` and `logs/` inside).
3. Register workflow secrets: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`, `SERVER_HOST`, `SERVER_USER`,
   `SERVER_PASSWORD`, plus `APPLICATION_PROD_YML`. Put the SSH port and volume path in the workflow `env:`
   from the private config at install time.
4. `pro-synology-expose` for `api.<project>.<root-domain>` pointing at `localhost:<traefik-port>`.
5. First deploy, then check `https://api.<project>.<root-domain>/actuator/health` and the container logs.
6. Write the project's registry entry (`project-registry.md`).

## Apps

React Native (Expo) and Flutter apps build on GitHub Actions, not on paid cloud build services; public repos get
macOS runners for free. Store workflows also run on the deploy trigger branch, so promoting to deploy uploads to the
stores: only on the user's explicit request.
