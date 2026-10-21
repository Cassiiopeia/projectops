> When to read: when interpreting the JSON from `collect` · `list-repos` · `local-facts`. What each field means, and which ones mean "could not see" rather than "missing".

# Reading the collected facts

## collect

Returns JSON with: metadata (description, topics, homepage, license, `is_template`, Discussions); health files (checked directly in the root, `.github` and `docs`,
because the community profile API does not recognize yml issue forms; names allow case, hyphen and extension variants); label names;
the README first screen as source text (`readme.top`), the heading list and media links; releases (with `prerelease` marked); and an issue sample (number, date, whether it is a PR).
For CONTRIBUTING and SECURITY it returns the first 15 lines (`head`) and the line count (`lines`), for spotting empty documents.

- **No verdicts are included.** You judge "is there a comparison section", "is the label scheme good" or "is the demo convincing" by reading the source.
- **If `errors` is present, those items are "could not check".** Only part may have been collected because issues are disabled (410) or permission is missing (403).
  Keep what is missing (`null`) apart from what you could not see (`errors`). When only part fails, the top-level `code` is `partial` and `ok` is `true`.
  If `truncated` is **not empty** or `capped` is `true`, you saw only part. If `sanitized` is present, an overlong string was cut or
  control characters such as direction overrides were removed. If you need the original, look at the repo directly.
- When a field tells you "where it looked", such as `unsupported_manifests` or `files.privacy_searched`, open anything outside that range yourself.

## list-repos (batch)

- When looking up an account returns repos owned by other organizations, they are reported in `other_owners`. **They are excluded by default.** If they are team repos, ask the user whether to include them.
- **If there are more than 20 targets**, confirm the scope with the user first. `collect` uses about 10 API calls per repo.
  If you get `rate_limited`, stop until the time given. Do not get the account blocked with a burst of retries.
- In batch audits, use `--include-all` (includes private repos) only when the user asks, and never write private repo content into anything public.

## local-facts (axes C·D·E)

`collect` only looks at the GitHub API. Whether it is easy to contribute, whether the code is extensible, and whether dependency licenses are safe
can only be known **by reading the repo and walking through it**. If you have a local clone path, use it. If not:

- In a small-tool review, do not ask; **leaving it as "D unverified" is the default** (asking for a clone adds a lot of friction).
- If the user wants the code reviewed too, or it is an audit, ask whether to clone. For an unknown repo, using only the API and not cloning is safer
  (risk of malicious config; `local-facts` runs with dangerous git settings disabled, but the clone itself is not trusted either).
- In batch, skip it and mark "code unverified".

It returns: `co_change` (pairs of files that changed together, **approximated per commit**; version-sync and generated-file candidates and large commits are excluded and reported in `excluded`.
Check through PRs and issues whether a remaining pair is an intended copy); `natural_language_strings` (files with many Korean or other CJK string literals, excluding tests and comments) and
`string_catalog_dirs`; `dependency_manifests` (declared dependency names) and `unsupported_manifests` (manifests it could not read,
which is different from an empty `{}`. **Open them and look yourself**. A file that is in `manifests_seen` but not in `dependency_manifests` is also "could not read":
it was broken or too large and skipped, so do not conclude "no manifest"); and `committed_secret_paths` (tracked paths that may be secrets; contents are not read).
**It makes no verdicts.** Look at the values and decide. In particular:

- Are the shared rules (branches, commits, style, tests, what is accepted) visible in one place and short, and are they enforced by tools?
- How many files does adding one feature touch? Count **per PR or issue, not per commit**, and leave out intended copies and generated files
- Are user-facing strings separated into a catalog?
- Dependency licenses: judge by **what actually ends up in the distributed artifact**
- Are `.env` files, key files or tokens committed? If so, report it **before anything else**. A committed secret has leaked even if you remove it from history,
  so **revoke (rotate) it first**. Do not write secret values or paths verbatim in public issues, comments or the report body; mask them
