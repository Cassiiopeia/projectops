# Extra criteria for distributed apps (`app`)

Repos that visitors **download and install** rather than import as code. The README plays the role of a product page.

Basis (as of research on 2026-09-30): stablyai/orca, localsend, immich, rustdesk, AppFlowy, jan, ente, Aegis, saber-notes/saber.
**The sample is 9 public FOSS apps.** It contains almost no store-only apps, so do not carry over the "must" items below as they are.
First determine how the app is distributed.

## 0. Determine the distribution model first

| Model | Clues | What applies |
|---|---|---|
| **A. Installers distributed through GitHub releases** | apk · ipa · dmg · exe assets in Releases | All "must" items in section 1 + section 3 |
| **B. Store only** (Play · App Store) | No Release assets, only store links | From section 1, only download path, screenshots, minimum OS and bug form. **Release files and signing are not applicable**. Section 2 store requirements apply |
| **C. Both** | Store + Releases (sideload) | Everything |

If the distribution model is unclear, ask the user.

## 1. Must (for model A; for B, only what the table marks)

| Item | Question | Basis | B (store only) |
|---|---|---|---|
| Download path at the top of the README | Are official store badges (Play · App Store · F-Droid · Flathub) or a platform × channel table on the first screen? | All 9 | Applies |
| Real screenshots | Device frames are rare. Real screens are enough | All 9 | Applies |
| Minimum OS version | Does it say which Android or iOS version is required? | | Applies |
| CI-built release files with consistent names | `<app>-<version>-<os>-<arch>.<ext>`; on Android, per-ABI + universal | arm64 dominates (as of research: localsend arm64 about 115k vs arm32 about 12k) | Not applicable |
| Readable release notes | A plain-language summary first, then "action required / migration" | immich | Not applicable if there are no GitHub releases |
| Version and OS in the bug form | Does it also explain where to find the version inside the app? | All 9 | Applies |
| Signed builds | Are distributed APKs and AABs **signed with a release key** (not a debug signature)? Is the signing certificate fingerprint published in the README or SECURITY.md? If the fingerprint differs per channel (GitHub APK · Play), does it say which is which? | Aegis and saber publish them | Not applicable (the store manages signing) |

## 2. Store review requirements (models B and C)

These items are **review issues, not taste**. The repo cannot show "whether it was submitted", so **ask the user.** Only what was confirmed in official documentation is stated as fact.

| Item | Confirmed facts (source) | What to look at in the repo |
|---|---|---|
| Privacy policy URL | **Apple: required for every app** (https://developer.apple.com/help/app-store-connect/manage-app-information/manage-app-privacy). **Google Play: a privacy policy is needed to submit the Data safety form** (https://support.google.com/googleplay/android-developer/answer/10787469). Play policy says the policy must be at an "active, publicly accessible and non-geofenced URL (no PDFs) and is non-editable" (https://support.google.com/googleplay/android-developer/answer/10144311) | `files.privacy_policy` from `collect`. If present, note the path; if not, check whether the README has a privacy section |
| **Is a README section or GitHub blob page accepted as that URL?** | **Needs checking.** The official docs above do not say whether anchor URLs or GitHub-rendered pages are allowed. Do not conclude. The docs also say nothing about how "non-editable" relates to GitHub pages | Ask the user which URL they actually entered in the store |
| Account deletion | **Apple**: apps that support account creation must let users start account deletion inside the app (since 2022-06-30). Deactivation alone is not enough (https://developer.apple.com/support/offering-account-deletion-in-your-app/). **Google Play**: apps with account creation need an in-app deletion path and a web link for users who uninstalled the app (https://support.google.com/googleplay/android-developer/answer/13327111) | Does the app have sign-up? If so, is the account deletion path (in-app and web) in the README or the app code? |
| Data safety (Play) · privacy nutrition labels (Apple) | Both require **declaring the data you collect and use in the store console** (the Play 10787469 and Apple manage-app-privacy links above). The declaration must match what the app actually does | The repo cannot show whether it was submitted. Ask the user, and compare the permissions and SDKs in the code (location, ads, analytics) with the declaration |

- The remaining detailed requirements in the table above (how to fill in each item, exceptions) **were not confirmed (needs checking).** Tell the user to open the official docs and check.
- Some apps keep `privacy_policy.md` in the repo and use it as the store URL (its change history stays in git; saber). Whether that satisfies the requirements depends on store policy, so leave it as needs checking.

## 3. Should

- The bug form asks for the **install source** (Play / App Store / TestFlight / Firebase App Distribution / GitHub APK) and the log location
- Keep store metadata in the repo: `fastlane/metadata/android/<locale>/`, and the store "What's new" in
  `changelogs/<versionCode>.txt`. If README screenshots come from here too, there is one set to maintain (Aegis · saber)
- Beta or RC channels
- Auto-update, or recommend installing from the store (the update manifest gets downloaded far more often than the installer)
- SECURITY.md (with a reporting channel), `SHA256SUMS`, and the published signing certificate fingerprint. With Play App Signing, Play re-signs with a different key,
  so say in the README which fingerprint belongs to which channel
- Translations of the app itself (Weblate · Crowdin · inlang)
- **For apps using sensitive permissions (location, microphone, camera, contacts etc.), a permission table**: which permission, why and when it is used, and whether data is collected or sent.
  None of the 9 researched apps did this. It sets the app apart, and it is the supporting material for matching the store data declaration above to what the app actually does

## 4. Nice to have

- F-Droid and reproducible builds, package managers (winget · Homebrew)
- Separate build variants (store, sideload, FOSS)
- Trademark guidance (so forks cannot use the name)

## 5. Patterns seen when auditing real app repos

- **`files.privacy_policy` from `collect`** looks for a privacy policy file in the root, docs and .github. There really were app repos with no file and only a privacy section
  in the README. In that case record "no file, README section present", and leave whether it can serve as the store URL as **needs checking**, per section 2.
- **fastlane and store metadata may not be in the root.** Flutter apps keep them under `android/fastlane` and `ios/fastlane`.
  Even if `files.store_metadata_root` is `false`, do not conclude they are missing; look inside the folders in `files.mobile_dirs`.
- App repos sometimes have numbered documents in `docs/` (requirements, releases, operations etc.) and a `release-notes/` folder. Check `root_entries` first
  to see whether release notes live in the README, a CHANGELOG or elsewhere.

## 6. License context

- Apps with a server component (immich · rustdesk · AppFlowy · ente) mostly used AGPL at the time of research. AGPL can require offering source to users
  even when a modified program is provided over a network. The intent behind this choice differs per repo, so do not guess.
- Pure client apps used MIT, Apache and GPL.
- Do not recommend a license; explain only the options and differences. Whether GPL-family code is compatible with store distribution stays as needs checking, per `rubric.md` E3.

## 7. Connection to projectops (only for repos that use projectops workflows)

If the repo uses projectops's Flutter workflows (Play Store · TestFlight · Firebase · APK build), propose release file and store metadata
improvements **as changes to those workflows**. One rule to keep: **every fastlane lane a workflow calls must actually exist in the Fastfile.**
The setup wizard overwrites the Fastfile, so do not add lanes by hand; fit the workflow to the lanes that already exist. For test builds, set the deploy mode
explicitly so the mode that leads to automatic review submission is not turned on.
