# Security Policy

A Korean version is in [docs/i18n/SECURITY.ko.md](docs/i18n/SECURITY.ko.md).

## Reporting a vulnerability

Please **do not open a public issue** for security vulnerabilities. Report them privately through GitHub:

- [Report a vulnerability privately](https://github.com/Cassiiopeia/projectops/security/advisories/new)

Including the following helps us confirm the report faster:

- The affected file or workflow name, and the projectops version
- Steps to reproduce
- The expected impact (for example, exposure of a secret or arbitrary command execution)

## Supported versions

Only the most recently released version receives security fixes. If you use an older version, update with `npx projectops`.

## Scope

projectops installs GitHub Actions workflows and scripts into other repositories. Reports in these areas are especially welcome:

- Workflows and scripts that handle secrets such as SSH credentials, personal access tokens and keystores
- Workflows that grant too many `permissions`, or that pass external input into shell commands
- Files and settings that the `npx projectops` wizard writes into the target repository
