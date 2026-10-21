---
name: pro-synology-expose
description: "Guide to expose a new web service from a Synology NAS on an external domain: DNS record, DSM reverse proxy, Let's Encrypt certificate. Use for 'expose service', 'connect domain', 'add reverse proxy'."
---

# Synology Expose - guide to exposing a web service externally

## When to use

- "Expose a service", "connect a domain", "add a reverse proxy", "set up a subdomain"
  (Korean: '서비스 외부 노출', '도메인 연결', '역방향 프록시 추가', '서브도메인 설정')
- "Set up HTTPS", "issue a certificate", "attach a new service to Synology", "WebSocket proxy"
  (Korean: 'HTTPS 설정', '인증서 발급', '시놀로지에 새 서비스 붙이기', '웹소켓 프록시')

This skill walks the user through exposing a web service that runs on a Synology NAS (in Docker or similar) to the outside over HTTPS on a custom domain.

Reply to the user in the user's language (or the configured `language` preference).

## What you want → detailed document

| Stage | What it does | Details |
|---|---|---|
| Prepare | Check the config (NAS instances) · collect service info | below |
| Step 1 | Add a DNS record (Cloudflare · Route53 · others) | `references/dns.md` |
| Step 2 | Two DSM reverse proxy rules (443→local port, 80→443) + 9 headers and advanced settings for WebSocket | `references/reverse-proxy.md` |
| Step 3 | Issue Let's Encrypt → attach it to the service → final checklist | `references/certificate.md` |

**Fixed order: DNS → proxy → certificate.** The certificate can be issued only after DNS has propagated (if it fails, wait a moment and retry).

---

## Check the config file

Follow `../references/config-rules.md` §2–5 (`skill_id = synology-expose`).

> ⚠️ **Do not search for the config.** config.json lives at one fixed path, `{HOME}/.projectops/config/config.json` — read it directly with the Read tool. Do not look for it with `ls` or glob, and do not dig through the plugin cache.

- If the file exists → parse the `instances` array.
  - One instance: use it.
  - Several instances: number them and let the user choose:
    ```
    Several NAS instances are registered. Which one should I use?
    1. Home NAS (my-nas.synology.me)
    2. Office NAS (office-nas.synology.me)
    ```
- If the file does not exist → collect these items one by one, then save:
  - NAS name (e.g. Home NAS)
  - Synology DDNS address (e.g. my-nas.synology.me)
  - List of domains in use
  - Let's Encrypt email
  - DNS provider (cloudflare, route53, gabia, etc.)

  Save format:
  ```json
  {
    "instances": [
      {
        "name": "{NAS name}",
        "ddns": "{ddns address}",
        "domains": ["{domain}"],
        "email": "{email}",
        "dns_provider": "{cloudflare|route53|gabia}",
        "default": true
      }
    ]
  }
  ```

---

## Collect service info

Once the config file is ready, collect what is needed to expose the service. Users often give a lot at once, so **infer as much as possible from what they provided** and ask only for what is missing.

### Required info

| Item | How to infer |
|------|-----------|
| **Service name** | From the service name the user mentions or the service name in docker-compose |
| **Subdomain** | The user specifies it, or infer it from the service name. Ask if unclear |
| **Local port** | Extract it from what the user provided. Ask if missing |
| **Uses WebSocket** | Judge from the kind of service (chat, streaming, etc. likely use WebSocket). Ask if unclear |
| **Timeout** | Default 60 seconds. Change only when the user mentions it |

### Inference principles

- Infer as much as possible from what the user provided (description, config files, port numbers, etc.)
- One sentence can carry several items (e.g. "put grafana on port 3000 online")
- Do not ask about what you can determine with certainty. Ask only about what is unclear
- If the subdomain is not certain, recommend one and get confirmation


---

## Decision rules

- Branch on the config's `dns_provider` for the **DNS provider** (cloudflare · route53 · other).
- If the subdomain contains a dot (e.g. `test.api.{domain}`), Cloudflare **cannot proxy it — DNS only**.
- **Only for WebSocket services**, add the 9 headers + advanced settings to rule 1 (the HTTPS proxy). Skip it for regular services.
- Timeout defaults to 60 seconds. Change it only when the user says so.

## If it is not reachable

1. The DNS record is registered correctly (`nslookup {subdomain}.{domain}`)
2. Ports 80 and 443 are open in the Synology firewall
3. The Docker container is running
4. The certificate is attached to the service correctly

---

## Guide format

Show each step in order, with **every placeholder filled in from the config values and the service info the user gave**. Show all concrete values so the user can copy them and enter them as is.

DSM screen names in the reference documents follow the English DSM UI. If the user's DSM is in another language, use the matching labels of that UI.

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-synology-expose`.
Keys for this skill: the common `language`, `tone`, `rules` only.
Preferences change presentation only; approval gates, secret protection and `--dry-run` stay in force.
