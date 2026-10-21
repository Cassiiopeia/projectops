# GitHub Actions secret management

> When to read: for requests such as "update the BACKEND_ENV_FILE secret", "change the secret", "upload the env file as a secret", "register an Actions secret" (Korean: "secret 업데이트해줘", "secret 바꿔줘", "환경변수 secret 올려줘", "Actions secret 등록해줘").

Commands have the form `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py secrets <list|set> ...` (SKILL.md "Find the scripts").

## Automatic lookup

Even if the user does not name the secret or give a value, the skill looks first.

**Step 1: decide the secret name**

- Name given in `$ARGUMENTS` → use it
- Not given → list the current repo's secrets and offer numbered choices

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py secrets list {owner} {repo}
```

**Step 2: decide the secret value**

- Value given in `$ARGUMENTS` → use it
- Not given → search for `.env` files in the project root and subdirectories:

  ```bash
  find "{PROJECT_ROOT}" -maxdepth 3 -name ".env" -not -path "*/node_modules/*" -not -path "*/.git/*" 2>/dev/null
  ```

  - `.env` found → show its content and confirm "Update with this content?"
  - No `.env` → ask the user to enter the value

> **Note**: `.env` content can contain sensitive data, so always show it to the user and get confirmation before proceeding.

## Update the secret

Pass the value through the `SECRET_VALUE` environment variable. A multi-line `.env` is preserved without argument escaping. `secrets set` encrypts it with the GitHub public key via PyNaCl, then PUTs it. If PyNaCl is not installed, it tries to install it; if that fails, it returns JSON with `code:"pynacl_missing"`.

```bash
SECRET_VALUE="{secret_value}" PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py secrets set {owner} {repo} {secret_name}
```

## Errors

| Error | Cause | Action |
|------|------|------|
| `403` on secrets API | PAT lacks the `repo` scope | Tell the user to check the full `repo` scope when reissuing the PAT |
| `404` on secrets list | No permission on a private repo | Tell the user to check permissions |
| `pynacl_missing` / `nacl` import error | PyNaCl install failed | Tell the user to run `pip install PyNaCl --user` manually |
| Special characters in `.env` content | Argument escaping issue | Pass it through the `SECRET_VALUE` environment variable |
