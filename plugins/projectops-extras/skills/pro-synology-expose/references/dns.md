> When to read: when you build the Step 1 (add a DNS record) guide. Where to enter it and the field table per DNS provider, plus an output example.

## Step 1: Add a DNS record

Vary the guide by the config file's `dnsProvider`.

### Cloudflare

**Location**: Cloudflare Dashboard > DNS > Records > "Add record"

| Field | Value |
|------|-----|
| Type | `{dnsRecordType}` |
| Name | `{subdomain}` |
| Target(Content) | `{ddnsAddress}` |
| Proxy status | `{dnsProxyStatus}` |
| TTL | `Auto` |

> If the subdomain contains a dot (e.g. `test.api.{domain}`), Proxied cannot be used — only DNS only.

### Route53

**Location**: AWS Console > Route 53 > Hosted zones > {domain} > "Create record"

| Field | Value |
|------|-----|
| Record name | `{subdomain}` |
| Record type | `{dnsRecordType}` |
| Value | `{ddnsAddress}` |
| TTL | `300` |
| Routing policy | `Simple routing` |

### Other DNS providers (gabia, self-managed, etc.)

Add the record below on the DNS management page:

| Field | Value |
|------|-----|
| Type | `{dnsRecordType}` |
| Host/Name | `{subdomain}` |
| Value/Target | `{ddnsAddress}` |
| TTL | default |

### Output example

```
[Step 1] Add DNS record ({dnsProvider})
  Type: {dnsRecordType}
  Name: {subdomain}
  Target: {ddnsAddress}
  (Cloudflare only) Proxy status: {dnsProxyStatus}
```
