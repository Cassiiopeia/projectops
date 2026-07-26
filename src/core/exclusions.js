// 템플릿 다운로드 후 제거하는 항목 (복사 제외 목록).
// ⚠️ CLAUDE.md "템플릿 전용 파일 추가" 규칙의 동기화 지점:
//    template_initializer.sh(삭제) / 이 파일(복사 제외)
//    (구 template_integrator.sh/.ps1의 배열은 #458 EOF로 소멸 — 여기가 유일한 복사 제외 지점)
export const DOCS_TO_REMOVE = [
  "CONTRIBUTING.md",
  "CLAUDE.md",
  "AGENTS.md",
  "GEMINI.md",
  "gemini-extension.json",
  // 릴리스마다 changelog-deploy 파이프라인이 재생성하는 이 레포 전용 작업 산출물.
  // 사용자 프로젝트에는 의미가 없으므로 복사하지 않는다.
  "pr_body.md",
];

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
  ".github/workflows/PROJECT-TEMPLATE-PLUGIN-VERSION-SYNC.yaml",
  ".github/workflows/PROJECT-TEMPLATE-NPM-PUBLISH.yaml",
];
// ⚠️ skills/ 는 제외하지 않는다 (Cursor 설치 소스로 보존)
