# Per-language store release note translation drafts (#829)

> When to read: in deploy step 5 / fix step 4, right after you finish the notes, and only when `release_language.store.translation_targets` from `detect-release-context` is **not empty**.
> If it is empty, you do not need this document. Proceed exactly as before.

## Where the language settings live (#977)

| Setting | Location | `release_language` field |
|---|---|---|
| Notes (= `CHANGELOG.md`) language | `version.yml` `language` | `notes_language` |
| Store languages | `version.yml` `store_locales` · `store_locales_ios` · `store_locales_play` | `store.locales*` · `store.base_locale` |
| One fixed text for every language | workflow env `STORE_WHATS_NEW_OVERRIDE` | `store.fixed_whats_new` |

All three are values CI reads, so they live in the repo, not in `config.json`. If the user asks "how did I set this up?", show these fields as they are.

## Why

Stores have a separate "What's New" field per language. If you upload one text to every language, English, Japanese and Chinese users see Korean. But you cannot leave untranslated languages empty either: App Store Connect rejects a review submission if even one language has an empty What's New. So **make translation drafts and get user approval**; for languages without a translation, the deploy step fills in the base-language text.

Do not call an external AI service. The agent running this skill translates directly.

## Choosing target languages

**The translation targets are exactly `release_language.store.translation_targets`** — every store language that differs from the notes language (`notes_language`). The CLI computes it from the keys below. Example: `store_locales: ["ko-KR", "en-US", "ja-JP", "zh-CN"]`.

| Key | Meaning |
|---|---|
| `store_locales` | Language list shared by both stores |
| `store_locales_ios` | (optional) only when the App Store differs — if present, the App Store uses this list |
| `store_locales_play` | (optional) only when Play differs — if present, Play uses this list |

- **The first entry is the base language** (`base_locale`). For languages without a translation, the deploy step fills in the notes text. Per-store lists also keep the same base language as their first entry.
- A language that only one store has is still a translation target, because that store uses it. Example: shared `[ko-KR, en-US]`, play `[ko-KR, en-US, ja-JP]`, notes `ko` → `en-US`, `ja-JP`.
- **If the notes language differs from the base language, the base language is a translation target too.** Example: notes `en`, `store_locales: [ko-KR, en-US]` → `ko-KR`. Miss it and English notes go up to the Korean store.
- On the approval screen, state in one line for each translation which store uses it (`App Store`/`Play`/`both`).
- A workflow with `store.fixed_whats_new` uploads that fixed text instead of the notes and translations. Still create the translations (other stores and `CHANGELOG.json` use them), and say in one line on the approval screen: "The App Store gets the fixed text '{text}' ({workflow})".

## Translation rules

- **The approved notes are the source.** Do not translate the commit log again.
- Keep the number and order of items. Store fields are small, so do not carry over category titles; write only `- ` items.
- Prefer app-update wording that speakers of that language understand over literal translation. As in the source notes, leave out file names, technical terms and issue numbers.
- **Respect the length.** Play allows 500 characters and the deploy step cuts at 480, so write **400 characters or fewer per language**. Anything longer gets cut off mid-sentence.
- For app review repos (`APP_RELEASE == true`), reviewers read this text. Do not bring back internal items that were removed from the source notes.
- If you are unsure of a phrase, do not invent one. Translate it simply and point it out on the approval screen.

## Format to append to the notes file (exactly this shape)

Append to the **very end** of the `NOTES_FILE` written in step 5, after the source notes. The parser reads the two marker lines and the `**locale-code**` title lines, so write them character for character.

```
<!-- projectops:store-notes -->
<details><summary>Store release notes (translations)</summary>

**en-US**
- Improved alert reliability
- Fixed a sign-in error

**ja-JP**
- 通知の安定性を改善しました
- ログインのエラーを修正しました

**zh-CN**
- 提升了提醒的稳定性
- 修复了登录错误

</details>
<!-- /projectops:store-notes -->
```

- Write the locale codes exactly as they appear in `store_locales` (`en-US`, `ja-JP`, `zh-CN`). Write only the languages in `translation_targets`; do not include the notes language.
- A `**locale-code**` line is only for language titles. Do not create a line that is only bold text inside a translation (it can be mistaken for a language title). Write items only as lines that start with `- `.
- This block goes into the PR body collapsed. After the merge, the release workflow pulls it out and saves it to `store_notes` in `CHANGELOG.json`. It does not mix into the change history (`CHANGELOG.md`).

## What to show at the approval gate (5.5 / 4.5)

Show the source notes and the translations **together**. Printing the whole notes file as is works. Add one line right below the B (manual) branch message:

```
🌐 Translation drafts are included (en-US, ja-JP, zh-CN). Tell me if any wording sounds off.
   Languages without a translation get the base-language text when deployed.
```

- If an edit request is about the source notes, fix them and **regenerate the translations too.** If you fix only the source, stale translations go to the store.
- If the request is to fix only a translation, fix only that language.
- In the A (auto) branch, translations are also only shown before proceeding. App review repos need manual approval even in auto mode, so the translations get confirmed too.

## When not to create translations

- When "leave it" was chosen with the `commit` provider (empty-body PR without a notes file) — no translations either. Languages without a translation go up with the base-language text, so the deploy does not stop. Leave just one line: "Proceeding without translations. Other-language stores get the base-language text."
- If the user says "skip the translations" ("번역은 빼줘"), do not append the block.

## fix mode

When you close the existing PR and open a new one, the notes file must have the same block. If you rewrite the notes in fix step 4, append the translations again. Do not copy the block from the previous PR body — the source notes may have changed.
