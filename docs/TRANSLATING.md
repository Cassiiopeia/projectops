# Translating projectops

projectops writes a few messages into **your** repository: issue and PR templates, bot comments,
release-notes notices, the `CHANGELOG.md` header and workflow commit messages. English is the source
language. Any other language is added by adding files plus one line in a list (step 3 below).

The language of a repository is `options.language` in `version.yml`:

```yaml
metadata:
  template:
    options:
      language: en   # en | ko | ...
```

- New installs get `en`. Existing installs without the key keep `ko`, so an update never changes the
  wording in a repository that already uses it.
- Change it with `npx projectops --language <code>`.
- A message that is missing in a language **falls back to English**. A partial translation never breaks a
  workflow, so you can contribute a few messages at a time.

## Add a language

Pick the language code (`ja`, `zh-CN`, `de`, ...). Three things:

1. **Message catalog.** Copy `.github/scripts/i18n/en.json` to `.github/scripts/i18n/<code>.json` and
   translate the values. You may delete keys you have not translated yet.
2. **Template overlay.** Copy the Korean overlay folder `.github/i18n/ko/` to `.github/i18n/<code>/` and
   translate the issue and PR templates. Keep the structure identical (sections, `labels`, `assignees`,
   the `[Tag]` in the title examples). A test compares the structure with the English templates.
3. **One line in the language list.** Add the code to `REPO_LANGUAGES` in `src/core/repo-language.js`.
   The list must match the files; a test fails if they disagree. The `version.yml` parser, `--language`
   validation and `npx projectops --mode options` all read this list, so nothing else needs the code.
   The comments written into `version.yml` fall back to English until you add a block for your language
   to `COMMENTS` (and a header) in `src/core/version-yml.js` — optional, and it never breaks anything.

Run the checks:

```bash
npm test
python3 -m pytest .github/scripts/test/test_i18n_messages.py -q
```

## Rules for messages

- Keys look like `area.event.part` (for example `qa_bot.comment.created`). Keep keys identical across languages.
- Use `{name}` placeholders only. Every placeholder in the English text must appear in your translation, and
  you must not add new ones. Do not translate the placeholder names.
- Do not put these strings in a catalog. Older workflows already installed in other repositories read them with
  regular expressions, so they are never translated. They live in `.github/scripts/i18n/contracts.py`:
  `### 브랜치`, `Guide by ProjectOps`, `Guide by SUH-LAB`, `Summary by CodeRabbit`.
- Do not write `[skip ci]` in a message. The workflow appends it.
- Keep Markdown structure (headings, tables, code blocks) the same as English.

## What is not translated yet

Log lines in the Actions tab, the util wizards (HTML), the skills and most of `docs/` are still Korean or
English only. They are tracked in issue #769.
