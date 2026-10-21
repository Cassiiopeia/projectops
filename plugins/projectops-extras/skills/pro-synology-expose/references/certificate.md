> When to read: when you build the Step 3 (issue Let's Encrypt and attach it to the service) guide and the final checklist.

## Step 3: Issue the certificate and attach it to the service

### 3-1. Issue a Let's Encrypt certificate

**Location**: DSM > Control Panel > Security > Certificate tab > "Add"
(Korean DSM: 제어판 > 보안 > 인증서 > "추가")

| Step | Choose / enter |
|------|-----------|
| Choose action | "Add a new certificate" → Next |
| How to create the certificate | Select "Get a certificate from Let's Encrypt" |
| Set as default certificate | unchecked |
| Description | (leave empty or enter the subdomain) |
| Domain name | `{subdomain}.{domain}` |
| Email | `{email}` |
| Subject Alternative Name (SAN) | (leave empty) |

> DNS records can take a few minutes to propagate. If issuing the certificate fails, wait a moment and retry.

### 3-2. Attach the certificate to the service

**Location**: DSM > Control Panel > Security > Certificate tab > "Settings" button
(Korean DSM: 제어판 > 보안 > 인증서 > "설정")

In the service list of the settings pop-up, find the `{subdomain}.{domain}` entry, change its certificate drop-down to the `{subdomain}.{domain}` certificate you just issued → click "OK".

### Output example

```
[Step 3] Issue and attach the certificate

[3-1] Issue the certificate
  Control Panel > Security > Certificate > Add
  Method: Get a certificate from Let's Encrypt
  Domain: {subdomain}.{domain}
  Email: {email}

[3-2] Attach the certificate to the service
  Control Panel > Security > Certificate > Settings
  Service: {subdomain}.{domain} → Certificate: {subdomain}.{domain}
```

---

## Final check

When everything is set up, tell the user to open `https://{subdomain}.{domain}` in a browser and confirm it works.

Checklist if it is not reachable:
1. Confirm the DNS record is registered correctly (`nslookup {subdomain}.{domain}`)
2. Confirm ports 80 and 443 are open in the Synology firewall
3. Confirm the Docker container is running
4. Confirm the certificate is attached to the service correctly
