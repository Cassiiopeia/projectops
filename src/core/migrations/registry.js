// 레거시 마이그레이션 단일 레지스트리 (#470) — 유일한 관리 지점.
//
// ⚠️ 템플릿에서 워크플로우/루트 파일을 리네임·폐기하면 반드시 여기에 구 이름을 한 줄 추가한다.
//    (test/migrations.test.js가 "레지스트리 항목이 현행 배포 세트와 겹치지 않는지" 자동 검증)
//
// 항목 스키마:
//   id         - 고유 식별자 (kebab-case)
//   category   - "workflow" | "root-file" | "legacy-dir" | "util-file"  (rules/ 폴더의 구현이 detect/apply 담당)
//                util-file: .github/util/ 모듈 안의 폐기 파일 — root-file rule 재사용(정확 경로 삭제).
//                           util 복사(copy/util.js)는 overlay라 구 파일을 지우지 않는다 — 정리는 여기가 유일 경로.
//   tier       - "safe"    : 신형이 같은 기능을 대체(순수 리네임). 공존 시 이중 트리거 실해
//                            → 확인 1회 후 자동 무해화(.bak) / 삭제
//                "confirm" : 배포 파이프라인일 수 있음(그 레포의 유일한 현역 배포 가능성)
//                            → 기본은 건드리지 않고 완료 요약·doctor 에 목록만 안내한다.
//                              --remove-legacy(비대화형) 또는 대화형 확인(기본 아니오)이 있을 때만 .bak 으로 무해화 (#809)
//                "ask"     : 사용자 콘텐츠가 담긴 폴더 등 — 손실 없는 이동이지만 사용자 소유물 (#476)
//                            → 대화형: 확인 후 이동 / 비대화형: 자동 조치 없이 안내만
//   file       - 정확한 파일명 (글롭 금지 — 사용자 커스텀 보호의 핵심)
//   replacedBy - 대체 신형 파일명 (없으면 null)
//   since      - 구 파일이 폐기된 템플릿 버전(참고용)
//   reason     - 계획 카드에 표시할 사유
//   contentMarker - (선택) 파일명이 범용적일 때 오탐 방지용 내용 마커 — 이 문자열이
//                   파일 내용에 있을 때만 템플릿 소유로 판정
//   settingsExtractor - (선택) 무해화 직전 실행할 설정 이관기 이름
//                       (rules/settings-extractors.js의 EXTRACTORS 키)
//
// 데이터 출처: git 히스토리 삭제/리네임 전수 + 실제 통합 레포 14개 스캔 (2026-07-11, 설계 문서 참조)
import { tEn } from "../../i18n/index.js";

export const MIGRATIONS = [
  // ── workflow / safe — 순수 리네임·대체 (공존 시 중복 실행 실해) ──────────────
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
    settingsExtractor: "suh-issue-helper-module" }, // 무해화 전 with: 커스텀 값을 version.yml로 이관
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

  // ── workflow / confirm — 배포/업로드 계열 (현역 배포일 수 있어 자동 조치 금지) ──
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
  // #661 — 템플릿에서 사라졌는데 레거시로 잡히지 않던 릴리스 워크플로우. 이 파일의 trunk-based 분기는
  // 지금은 없는 `changelog_manager.py ai-summary` 를 불러 릴리스 때 실패한다. 그 레포의 유일한
  // 릴리스 경로일 수 있어 자동으로 건드리지 않고 안내만 한다. 같은 파일명을 쓰는 사용자 파일을
  // 오탐하지 않도록 내용 마커로 한 번 더 확인한다.
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

  // ── root-file / safe — 구 설치 가이드 (사용자가 매번 수동 삭제하던 것) ─────────
  { id: "root-setup-guide-v2", category: "root-file", tier: "safe",
    file: "SUH-DEVOPS-TEMPLATE-SETUP-GUIDE.md", replacedBy: "PROJECTOPS-SETUP-GUIDE.md",
    since: "4.3.0", reasonKey: "migrate.reason.guideRebrand" },
  { id: "root-setup-guide-v1", category: "root-file", tier: "safe",
    file: "SETUP-GUIDE.md", replacedBy: "PROJECTOPS-SETUP-GUIDE.md",
    since: "2.x", reasonKey: "migrate.reason.guideOld",
    contentMarker: "SUH" }, // 범용 파일명이라 내용에 템플릿 마커가 있을 때만 소유 판정

  // ── legacy-dir / ask — 구명칭 산출물 폴더 (사용자 문서 보존 이동, #476) ────────
  { id: "dir-docs-suh-template", category: "legacy-dir", tier: "ask",
    file: "docs/suh-template", replacedBy: "docs/projectops",
    since: "4.2.9", reasonKey: "migrate.reason.docsDir" },

  // ── util-file / safe — Flutter 마법사 스크립트 Python 단일화 (#500) ──────────
  // 로컬 실행 도구라 CI 중복 실행 위험은 없지만, 신형 py와 공존 시 사용자가 구 스크립트를
  // 실행해 갈라진 동작을 볼 수 있다. 마법사 폴더에 사용자 상태가 없어 삭제가 기대 동작.
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

// 사유는 영문 정본(tEn)으로 노출해 실행 로그·가이드에 그대로 쓰고,
// 화면 표시는 reasonKey를 t()로 번역해 쓴다.
for (const m of MIGRATIONS) {
  Object.defineProperty(m, "reason", { enumerable: true, get: () => tEn(m.reasonKey) });
}
