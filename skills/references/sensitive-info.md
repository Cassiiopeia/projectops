# Protecting sensitive information (detail)

The detail behind `common-rules.md` §"Protecting sensitive information", §"Masking rules", and §"Self-review right before saving a file".
Read it right before saving an artifact file (issue, report, plan, note, and so on) or posting to GitHub.

The `docs/projectops/` folder is committed publicly to Git. Keep sensitive information out of every artifact.

## Never include

- Real values of GitHub PATs, API keys, Secrets, tokens, or passwords
- Server IPs, internal domains, SSH connection details
- Personal data such as personal email addresses and phone numbers
- `.env` file contents, DB connection details

## Masking rules

Write placeholders instead of real values.

| Kind | Notation |
|------|-----------|
| API Key / PAT / Token | `{API_KEY}`, `{PAT}`, `{TOKEN}` |
| Password / Secret | `{PASSWORD}`, `{SECRET}` |
| DB username / account name | `{DB_USERNAME}`, `{ADMIN_ID}` |
| Server address | `{SERVER_HOST}` |
| Personal data | `{EMAIL}`, `{PHONE}` |

### Extra care when writing reports and issues

- If an error log contains a token or key, always mask it before including it
- In reproduction steps, use placeholders such as `{SERVER_HOST}` instead of real server details
- When quoting screenshots or logs, replace sensitive values with placeholders (no anonymous asterisks like `***` — they hide what kind of value it was, so the meaning is lost)

## Self-review right before saving a file

**Right before** saving an artifact file, review everything you wrote against the checklist below.

| Item | Risky example | Safe example |
|------|-----------|-----------|
| Real password value | `password: abc123`, `비번: qwer1234` (Korean for "pw:") | `password: {PASSWORD}` |
| Real ID / account / DB username | `admin/mypassword`, `아이디: hong123` (Korean for "ID:"), `username: kimchi` | `{ADMIN_ID}/{PASSWORD}`, `{DB_USERNAME}` |
| Real API key / token | `sk-abc123xyz`, `AIza...` | `{API_KEY}` |
| Real GitHub PAT | `ghp_abc123...` (a real, valid-looking long string) | `{PAT}` |
| Real DB connection details | `mysql://user:pass@192.168.0.1` | `mysql://{DB_USER}:{DB_PASS}@{DB_HOST}` |
| Personal data | Phone number, national ID number, real name + bank account | `{PHONE}`, `{SSN}` |

**Criteria**:
- `${{ secrets.XXX }}` form — **safe** (a key name, not a real value)
- `{DB_USERNAME}`, `{PASSWORD}` form — **safe** (named placeholders)
- A long string that looks really valid, like `ghp_ru0dCYe...` — **risky**
- A real value exposed in plain text, like `password: admin123` — **risky**
- A real account name exposed, like `username: kimchi` or `user: hong123` — **risky**
- Anonymous asterisks like `********` — **not allowed** (replace with a placeholder)

**How to handle it**:
1. If you find a risky item → replace that value with a placeholder, then save
2. If anything was masked, tell the user after saving (in the user's language):
   ```
   ⚠️ Sensitive information masked:
   - [kind of item]: real value → {placeholder}
   ```
3. If there are no risky items → save as is (no extra message needed)
