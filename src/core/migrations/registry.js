// Single registry for legacy migrations (#470) — the only place to manage them.
//
// ⚠️ When the template renames or retires a workflow/root file, always add the old name here in one line.
//    (test/migrations.test.js automatically checks "registry entries do not overlap the current shipped set")
//
// Entry schema:
//   id         - unique identifier (kebab-case)
//   category   - "workflow" | "root-file" | "legacy-dir" | "util-file"  (implementations in rules/ handle detect/apply)
//                util-file: obsolete files inside .github/util/ modules — reuses the root-file rule (exact-path delete).
//                           The util copy (copy/util.js) is an overlay and does not delete old files — this is the only cleanup path.
//   tier       - "safe"    : the new file replaces the same function (pure rename). Coexisting causes real double triggers
//                            → auto-neutralize (.bak) / delete after one confirmation
//                "confirm" : may be a deploy pipeline (possibly the repo's only live deploy)
//                            → left alone by default; only listed in the finish summary and doctor.
//                              Neutralized as .bak only with --remove-legacy (non-interactive) or interactive confirmation (default no) (#809)
//                "ask"     : folders holding user content etc. — a lossless move, but owned by the user (#476)
//                            → interactive: move after confirmation / non-interactive: notice only, no automatic action
//   file       - exact file name (no globs — key to protecting user customizations)
//   replacedBy - replacement new file name (null if none)
//   since      - template version that retired the old file (reference)
//   reason     - reason shown on the plan card
//   contentMarker - (optional) content marker to avoid false hits when the file name is generic — owned by the
//                   template only when this string is in the file content
//   settingsExtractor - (optional) name of the settings migrator to run right before neutralizing
//                       (key of EXTRACTORS in rules/settings-extractors.js)
//
// Data sources: full git history of deletes/renames + scan of 14 real integrated repos (2026-07-11, see design doc)
import { tEn } from "../../i18n/index.js";

export const MIGRATIONS = [
  // ── workflow / safe — pure renames/replacements (coexisting causes real duplicate runs) ──────────────
  { id: "wf-version-control", category: "workflow", tier: "safe",
    file: "PROJECT-VERSION-CONTROL.yaml", replacedBy: "PROJECT-COMMON-VERSION-CONTROL.yaml",
    since: "2.x", reasonKey: "migrate.reason.gen1VersionControl" },
  { id: "wf-readme-version-update", category: "workflow", tier: "safe",
    file: "PROJECT-README-VERSION-UPDATE.yaml", replacedBy: "PROJECT-COMMON-README-VERSION-UPDATE.yaml",
    since: "2.x", reasonKey: "migrate.reason.gen1Readme" },
  { id: "wf-sync-issue-labels-v1", category: "workflow", tier: "safe",
    file: "PROJECT-SYNC-ISSUE-LABELS.yaml", replacedBy: "PROJECT-COMMON-SYNC-ISSUE-LABELS.yaml",
    since: "2.x", reasonKey: "migrate.reason.gen1Labels" },
  { id: "wf-sync-issue-labels-v0", category: "workflow", tier: "safe",
    file: "sync-issue-labels.yaml", replacedBy: "PROJECT-COMMON-SYNC-ISSUE-LABELS.yaml",
    since: "2.x", reasonKey: "migrate.reason.gen0Labels" },
  { id: "wf-issue-comment-v1", category: "workflow", tier: "safe",
    file: "PROJECT-ISSUE-COMMENT.yaml", replacedBy: "PROJECT-COMMON-SUH-ISSUE-HELPER.yaml",
    since: "2.x", reasonKey: "migrate.reason.helperGen1" },
  { id: "wf-issue-comment-v2", category: "workflow", tier: "safe",
    file: "PROJECT-COMMON-ISSUE-COMMENT.yaml", replacedBy: "PROJECT-COMMON-SUH-ISSUE-HELPER.yaml",
    since: "2.x", reasonKey: "migrate.reason.helperGen2" },
  { id: "wf-issue-helper-api", category: "workflow", tier: "safe",
    file: "PROJECT-COMMON-SUH-ISSUE-HELPER-API.yaml", replacedBy: "PROJECT-COMMON-SUH-ISSUE-HELPER.yaml",
    since: "4.3.0", reasonKey: "migrate.reason.helperApi" },
  { id: "wf-issue-helper-module", category: "workflow", tier: "safe",
    file: "PROJECT-COMMON-SUH-ISSUE-HELPER-MODULE.yml", replacedBy: "PROJECT-COMMON-SUH-ISSUE-HELPER.yaml",
    since: "4.3.0", reasonKey: "migrate.reason.helperModule",
    settingsExtractor: "suh-issue-helper-module" }, // Move with: custom values to version.yml before neutralizing
  { id: "wf-auto-changelog-v1", category: "workflow", tier: "safe",
    file: "PROJECT-AUTO-CHANGELOG-CONTROL.yaml", replacedBy: "PROJECT-COMMON-RELEASE-CHANGELOG.yaml",
    since: "2.x", reasonKey: "migrate.reason.releaseGen1" },
  { id: "wf-auto-changelog-v2", category: "workflow", tier: "safe",
    file: "PROJECT-COMMON-AUTO-CHANGELOG-CONTROL.yaml", replacedBy: "PROJECT-COMMON-RELEASE-CHANGELOG.yaml",
    since: "4.3.0", reasonKey: "migrate.reason.releaseRename" },
  { id: "wf-comqa-bot", category: "workflow", tier: "safe",
    file: "COMQA-ISSUE-CREATION-BOT.yaml", replacedBy: "PROJECT-COMMON-QA-ISSUE-CREATION-BOT.yaml",
    since: "2.x", reasonKey: "migrate.reason.qaBot" },
  { id: "wf-template-util-sync", category: "workflow", tier: "safe",
    file: "TEMPLATE-UTIL-VERSION-SYNC.yml", replacedBy: "PROJECT-COMMON-TEMPLATE-UTIL-VERSION-SYNC.yml",
    since: "2.x", reasonKey: "migrate.reason.utilSync" },
  { id: "wf-backlog-manager", category: "workflow", tier: "safe",
    file: "PROJECT-COMMON-PROJECT-BACKLOG-MANAGER.yaml", replacedBy: "PROJECT-COMMON-PROJECTS-SYNC-MANAGER.yaml",
    since: "3.x", reasonKey: "migrate.reason.projectsSync" },
  { id: "wf-suh-lab-build-trigger", category: "workflow", tier: "safe",
    file: "PROJECT-FLUTTER-SUH-LAB-APP-BUILD-TRIGGER.yaml", replacedBy: "PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml",
    since: "4.3.0", reasonKey: "migrate.reason.buildTrigger" },
  { id: "wf-next-ci", category: "workflow", tier: "safe",
    file: "PROJECT-NEXT-CI.yaml", replacedBy: "PROJECT-REACT-CI.yaml",
    since: "4.1.0", reasonKey: "migrate.reason.nextType" },
  { id: "wf-next-cicd", category: "workflow", tier: "safe",
    file: "PROJECT-NEXT-CICD.yaml", replacedBy: "PROJECT-REACT-CICD.yaml",
    since: "4.1.0", reasonKey: "migrate.reason.nextType" },
  { id: "wf-flutter-ci-yml-ext", category: "workflow", tier: "safe",
    file: "PROJECT-FLUTTER-CI.yml", replacedBy: "PROJECT-FLUTTER-CI.yaml",
    since: "2.x", reasonKey: "migrate.reason.ymlExt" },
  { id: "wf-flutter-android-pr-ci", category: "workflow", tier: "safe",
    file: "PROJECT-FLUTTER-ANDROID-PR-CI.yaml", replacedBy: "PROJECT-FLUTTER-CI.yaml",
    since: "3.x", reasonKey: "migrate.reason.mergedCi" },

  // ── workflow / confirm — deploy/upload kind (may be the live deploy, so no automatic action) ──
  { id: "wf-syn-spring-simple", category: "workflow", tier: "confirm",
    file: "PROJECT-SPRING-SYNOLOGY-SIMPLE-CICD.yaml", replacedBy: "PROJECT-SPRING-SIMPLE-CICD.yaml",
    since: "3.0.137", reasonKey: "migrate.reason.synSsh" },
  { id: "wf-syn-spring-nonstop", category: "workflow", tier: "confirm",
    file: "PROJECT-SPRING-SYNOLOGY-NONSTOP-CICD.yaml", replacedBy: "PROJECT-SPRING-NONSTOP-NGINX-CICD.yaml",
    since: "3.0.137", reasonKey: "migrate.reason.synNonstop" },
  { id: "wf-syn-spring-preview", category: "workflow", tier: "confirm",
    file: "PROJECT-SPRING-SYNOLOGY-PR-PREVIEW.yaml", replacedBy: "PROJECT-SPRING-PR-PREVIEW.yaml",
    since: "3.0.137", reasonKey: "migrate.reason.syn" },
  { id: "wf-syn-flutter-android", category: "workflow", tier: "confirm",
    file: "PROJECT-FLUTTER-ANDROID-SYNOLOGY-CICD.yaml", replacedBy: "PROJECT-FLUTTER-ANDROID-SELFHOSTED-CICD.yaml",
    since: "3.0.137", reasonKey: "migrate.reason.synSmb" },
  { id: "wf-syn-python-cicd", category: "workflow", tier: "confirm",
    file: "PROJECT-PYTHON-SYNOLOGY-CICD.yaml", replacedBy: "PROJECT-PYTHON-SIMPLE-CICD.yaml",
    since: "3.0.137", reasonKey: "migrate.reason.syn" },
  { id: "wf-syn-python-preview", category: "workflow", tier: "confirm",
    file: "PROJECT-PYTHON-SYNOLOGY-PR-PREVIEW.yaml", replacedBy: "PROJECT-PYTHON-PR-PREVIEW.yaml",
    since: "3.0.137", reasonKey: "migrate.reason.syn" },
  { id: "wf-syn-secret-upload", category: "workflow", tier: "confirm",
    file: "PROJECT-COMMON-SYNOLOGY-SECRET-FILE-UPLOAD.yaml", replacedBy: "PROJECT-COMMON-SECRET-FILE-UPLOAD.yaml",
    since: "3.0.137", reasonKey: "migrate.reason.synSecret" },
  // #661 — release workflow gone from the template but not caught as legacy. Its trunk-based branch
  // calls `changelog_manager.py ai-summary`, which no longer exists, and fails on release. It may be the repo's only
  // release path, so it is not touched automatically, only reported. A content marker double-checks it so a user file
  // with the same name is not misdetected.
  { id: "wf-release-publish-v1", category: "workflow", tier: "confirm",
    file: "PROJECT-COMMON-RELEASE-PUBLISH.yaml", replacedBy: "PROJECT-COMMON-RELEASE-CHANGELOG.yaml",
    since: "2.x", reasonKey: "migrate.reason.releasePublish1", contentMarker: "ai-summary" },
  { id: "wf-spring-ci-v1", category: "workflow", tier: "confirm",
    file: "PROJECT-SPRING-CI.yaml", replacedBy: null,
    since: "2.x", reasonKey: "migrate.reason.springCi1" },
  { id: "wf-spring-cicd-v1", category: "workflow", tier: "confirm",
    file: "PROJECT-SPRING-CICD.yaml", replacedBy: "PROJECT-SPRING-SIMPLE-CICD.yaml",
    since: "2.x", reasonKey: "migrate.reason.springDeploy1" },
  { id: "wf-python-cicd-v1", category: "workflow", tier: "confirm",
    file: "PROJECT-PYTHON-CICD.yaml", replacedBy: "PROJECT-PYTHON-SIMPLE-CICD.yaml",
    since: "3.x", reasonKey: "migrate.reason.pythonDeploy1" },
  { id: "wf-android-cicd-v1", category: "workflow", tier: "confirm",
    file: "PROJECT-ANDROID-CICD.yaml", replacedBy: "PROJECT-FLUTTER-ANDROID-PLAYSTORE-CICD.yaml",
    since: "2.x", reasonKey: "migrate.reason.androidDeploy1" },
  { id: "wf-ios-testflight-v1", category: "workflow", tier: "confirm",
    file: "PROJECT-IOS-TESTFLIGHT-CICD.yml", replacedBy: "PROJECT-FLUTTER-IOS-TESTFLIGHT.yaml",
    since: "2.x", reasonKey: "migrate.reason.iosDeploy1" },
  { id: "wf-flutter-ios-cicd", category: "workflow", tier: "confirm",
    file: "PROJECT-FLUTTER-IOS-CICD.yaml", replacedBy: "PROJECT-FLUTTER-IOS-TESTFLIGHT.yaml",
    since: "3.x", reasonKey: "migrate.reason.iosTestflight" },
  { id: "wf-file-upload-spring", category: "workflow", tier: "confirm",
    file: "PROJECT-SPRING-AUTO-FILE-UPLOAD.yaml", replacedBy: "PROJECT-COMMON-SECRET-FILE-UPLOAD.yaml",
    since: "3.x", reasonKey: "migrate.reason.secretUpload" },
  { id: "wf-file-upload-flutter", category: "workflow", tier: "confirm",
    file: "PROJECT-FLUTTER-AUTO-FILE-UPLOAD.yaml", replacedBy: "PROJECT-COMMON-SECRET-FILE-UPLOAD.yaml",
    since: "3.x", reasonKey: "migrate.reason.secretUpload" },
  { id: "wf-file-upload-python", category: "workflow", tier: "confirm",
    file: "PROJECT-PYTHON-AUTO-FILE-UPLOAD.yaml", replacedBy: "PROJECT-COMMON-SECRET-FILE-UPLOAD.yaml",
    since: "3.x", reasonKey: "migrate.reason.secretUpload" },
  { id: "wf-file-upload-v1", category: "workflow", tier: "confirm",
    file: "PROJECT-FILE-AUTO-UPLOAD.yaml", replacedBy: "PROJECT-COMMON-SECRET-FILE-UPLOAD.yaml",
    since: "2.x", reasonKey: "migrate.reason.secretUpload" },
  { id: "wf-nexus-publish-v1", category: "workflow", tier: "confirm",
    file: "PROJECT-NEXUS-PUBLISH.yml", replacedBy: "PROJECT-SPRING-NEXUS-PUBLISH.yml",
    since: "2.x", reasonKey: "migrate.reason.nexusPublish" },
  { id: "wf-nexus-ci-v1", category: "workflow", tier: "confirm",
    file: "PROJECT-NEXUS-MODULE-CI-BUILD-CHECK.yml", replacedBy: "PROJECT-SPRING-NEXUS-CI.yml",
    since: "2.x", reasonKey: "migrate.reason.nexusCi" },
  { id: "wf-ci-build-check-v0", category: "workflow", tier: "confirm",
    file: "PROJECT-CI-BUILD-CHECK.yml", replacedBy: "PROJECT-SPRING-NEXUS-CI.yml",
    since: "2.x", reasonKey: "migrate.reason.libCi0" },
  { id: "wf-publish-v0", category: "workflow", tier: "confirm",
    file: "PROJECT-PUBLISH.yml", replacedBy: "PROJECT-SPRING-NEXUS-PUBLISH.yml",
    since: "2.x", reasonKey: "migrate.reason.libPublish0" },
  { id: "wf-deploy-trigger", category: "workflow", tier: "confirm",
    file: "PROJECT-DEPLOY-TRIGGER.yaml", replacedBy: null,
    since: "3.x", reasonKey: "migrate.reason.deployTrigger" },

  // ── root-file / safe — old setup guides (the ones users deleted by hand every time) ─────────
  { id: "root-setup-guide-v2", category: "root-file", tier: "safe",
    file: "SUH-DEVOPS-TEMPLATE-SETUP-GUIDE.md", replacedBy: "PROJECTOPS-SETUP-GUIDE.md",
    since: "4.3.0", reasonKey: "migrate.reason.guideRebrand" },
  { id: "root-setup-guide-v1", category: "root-file", tier: "safe",
    file: "SETUP-GUIDE.md", replacedBy: "PROJECTOPS-SETUP-GUIDE.md",
    since: "2.x", reasonKey: "migrate.reason.guideOld",
    contentMarker: "SUH" }, // Generic file name, so owned only when the content has the template marker

  // ── legacy-dir / ask — old-name output folders (moved, keeping user documents, #476) ────────
  { id: "dir-docs-suh-template", category: "legacy-dir", tier: "ask",
    file: "docs/suh-template", replacedBy: "docs/projectops",
    since: "4.2.9", reasonKey: "migrate.reason.docsDir" },

  // ── util-file / safe — Flutter wizard scripts unified into Python (#500) ──────────
  // Local tools, so no risk of duplicate CI runs, but alongside the new py a user could run an old script
  // and see diverging behavior. The wizard folders hold no user state, so deletion is the expected behavior.
  { id: "util-playstore-setup-sh", category: "util-file", tier: "safe",
    file: ".github/util/flutter/playstore-wizard/playstore-wizard-setup.sh", replacedBy: "playstore-wizard.py",
    since: "4.3.0", reasonKey: "migrate.reason.wizSetup" },
  { id: "util-playstore-setup-ps1", category: "util-file", tier: "safe",
    file: ".github/util/flutter/playstore-wizard/playstore-wizard-setup.ps1", replacedBy: "playstore-wizard.py",
    since: "4.3.0", reasonKey: "migrate.reason.wizSetup" },
  { id: "util-playstore-apply-sh", category: "util-file", tier: "safe",
    file: ".github/util/flutter/playstore-wizard/playstore-wizard-apply.sh", replacedBy: "playstore-wizard.py",
    since: "4.3.0", reasonKey: "migrate.reason.wizApply" },
  { id: "util-playstore-apply-ps1", category: "util-file", tier: "safe",
    file: ".github/util/flutter/playstore-wizard/playstore-wizard-apply.ps1", replacedBy: "playstore-wizard.py",
    since: "4.3.0", reasonKey: "migrate.reason.wizApply" },
  { id: "util-playstore-detect-sh", category: "util-file", tier: "safe",
    file: ".github/util/flutter/playstore-wizard/detect-application-id.sh", replacedBy: "playstore-wizard.py",
    since: "4.3.0", reasonKey: "migrate.reason.wizDetect" },
  { id: "util-playstore-detect-ps1", category: "util-file", tier: "safe",
    file: ".github/util/flutter/playstore-wizard/detect-application-id.ps1", replacedBy: "playstore-wizard.py",
    since: "4.3.0", reasonKey: "migrate.reason.wizDetect" },
  { id: "util-playstore-patch-py", category: "util-file", tier: "safe",
    file: ".github/util/flutter/playstore-wizard/patch-build-gradle.py", replacedBy: "playstore-wizard.py",
    since: "4.3.0", reasonKey: "migrate.reason.wizPatch" },
  { id: "util-firebase-setup-sh", category: "util-file", tier: "safe",
    file: ".github/util/flutter/firebase-wizard/firebase-wizard-setup.sh", replacedBy: "firebase-wizard.py",
    since: "4.3.0", reasonKey: "migrate.reason.wizSetup" },
  { id: "util-firebase-setup-ps1", category: "util-file", tier: "safe",
    file: ".github/util/flutter/firebase-wizard/firebase-wizard-setup.ps1", replacedBy: "firebase-wizard.py",
    since: "4.3.0", reasonKey: "migrate.reason.wizSetup" },
  { id: "util-firebase-test-sh", category: "util-file", tier: "safe",
    file: ".github/util/flutter/firebase-wizard/test/setup-script-test.sh", replacedBy: "test/setup-script-test.py",
    since: "4.3.0", reasonKey: "migrate.reason.wizTest" },
  { id: "util-firebase-test-ps1", category: "util-file", tier: "safe",
    file: ".github/util/flutter/firebase-wizard/test/setup-script-test.ps1", replacedBy: "test/setup-script-test.py",
    since: "4.3.0", reasonKey: "migrate.reason.wizTest" },
  { id: "util-testflight-setup-sh", category: "util-file", tier: "safe",
    file: ".github/util/flutter/testflight-wizard/testflight-wizard-setup.sh", replacedBy: "testflight-wizard.py",
    since: "4.3.0", reasonKey: "migrate.reason.wizSetup" },
];

// Reasons are exposed as the English source (tEn) and used as is in run logs and guides;
// the screen translates reasonKey with t().
for (const m of MIGRATIONS) {
  Object.defineProperty(m, "reason", { enumerable: true, get: () => tEn(m.reasonKey) });
}
