// 여러 파일이 함께 써야 하는 값 목록의 정본.
//
// 왜 한 곳인가: deploy·publish 목록이 CLI 인자 검사(args.js), 마법사 질문(options-ask.js),
// 복사 엔진(copy/workflows.js), version.yml 파서(version-yml.js), 옵션 표(options-schema.js)
// 다섯 곳에 따로 적혀 있었다. 하나만 고치면 "CLI 는 받는데 파서가 버린다" 같은 조용한 불일치가 생긴다.
// 값을 추가할 때는 여기 한 줄만 고치고, 그 값에 해당하는 워크플로우 폴더를 만든다
// (deploy: project-types/common/deploy/<값>/ · publish: project-types/<type>/publish/<값>/).
//
// 이 파일은 아무것도 import 하지 않는다 — 어디서 불러도 순환 import 가 생기지 않게.
// 레포 문구 언어 목록은 repo-language.js 의 REPO_LANGUAGES 가 정본이다 (번역 파일과 같이 검사된다).

/** 실행물을 어디에 배포하나 — 택1 (#439) */
export const DEPLOY_TARGETS = Object.freeze(["docker-ssh", "vercel", "none"]);

/** 라이브러리를 어느 레지스트리에 내나 — 0..n (#439) */
export const PUBLISH_TARGETS = Object.freeze(["nexus", "npm", "github-packages"]);

/** 프로젝트 성격 — deploy/publish 질문을 유도한다 (#485) */
export const INTENT_VALUES = Object.freeze(["app", "library", "both", "none", "manual"]);

/** 상태 라벨 표기 — en: `status: todo`, ko: 기존 한글 `작업전` (#776) */
export const LABEL_STYLES = Object.freeze(["en", "ko"]);

/**
 * 릴리스 노트 생성기 (#455, #566). 기본값은 commit — 외부 의존이 없어 어디서나 결과가 나온다.
 * 실제 구현은 .github/scripts/changelog_providers/ 에 있고, 그쪽 목록과의 정합은 테스트가 본다.
 */
export const CHANGELOG_PROVIDERS = Object.freeze(["copilot", "coderabbit", "openai", "gemini", "claude", "groq", "mistral", "ollama", "commit"]);
