// 템플릿 다운로드 후 제거하는 항목 (복사 제외 목록).
// ⚠️ CLAUDE.md "템플릿 전용 파일 추가" 규칙의 동기화 지점:
//    template_initializer.py(삭제) / 이 파일(복사 제외)
//    (구 template_integrator.sh/.ps1의 배열은 #458 EOF로 소멸 — 여기가 유일한 복사 제외 지점)
export const DOCS_TO_REMOVE = [
  "CONTRIBUTING.md",
  "SECURITY.md",
  "CODE_OF_CONDUCT.md",
  "ARCHITECTURE.md",
  "CLAUDE.md",
  "AGENTS.md",
  "GEMINI.md",
  "llms.txt",
  "gemini-extension.json",
  // 릴리스마다 changelog-deploy 파이프라인이 재생성하는 이 레포 전용 작업 산출물.
  // 사용자 프로젝트에는 의미가 없으므로 복사하지 않는다.
  "pr_body.md",
];

// ⚠️ `.github/i18n`(한국어 템플릿 오버레이, #769)은 여기에 넣지 않는다. 이 목록은 내려받은 템플릿 폴더에서
// 항목을 지우는데, 오버레이는 language: ko 설치 때 그 폴더에서 읽어 와야 한다. 사용자 레포로는
// copyIssueTemplates 가 ISSUE_TEMPLATE/PULL_REQUEST_TEMPLATE 만 골라 복사하므로 새지 않는다.
// ("Use this template" 경로는 template_initializer.py 가 지운다.)
export const PLUGIN_ITEMS_TO_REMOVE = [
  ".claude-plugin",
  ".codex-plugin",
  ".agents",
  ".cursor",
  "scripts",
  "package.json",
  "harness",
  "bin",
  "src",
  "site",
  ".github/CODEOWNERS",
  ".github/workflows/PROJECT-TEMPLATE-PLUGIN-VERSION-SYNC.yaml",
  ".github/workflows/PROJECT-TEMPLATE-NPM-PUBLISH.yaml",
  ".github/workflows/PROJECT-TEMPLATE-DOCS-DEPLOY.yaml",
  ".github/workflows/PROJECT-TEMPLATE-SYNC-COMMUNITY-LABELS.yaml",
  ".github/config/community-labels.yml",
];
// ⚠️ skills/ 는 제외하지 않는다 (Cursor 설치 소스로 보존)
