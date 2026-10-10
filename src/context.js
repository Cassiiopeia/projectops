// 마법사 전역 상태를 하나의 객체로 명시화 (bash 전역 변수군 대체)
// next 타입은 v4.1.0에서 react로 흡수됨 (breaking)
export const VALID_TYPES = [
  "spring", "flutter", "react",
  "react-native", "react-native-expo", "node", "python", "basic",
];

export const DEFAULT_VERSION = "1.3.14"; // .sh DEFAULT_VERSION (배너 폴백용 — breaking 비교엔 안 씀)

export function createContext(overrides = {}) {
  return {
    mode: "interactive",
    force: false,
    types: [],
    version: "",
    branch: "",
    paths: new Map(),        // type -> path
    // 배포/publish 축 (#439 — 타입 비종속. null=미설정)
    deployTarget: null,      // 'docker-ssh'(기본) | 'vercel' | 'none'
    publishTargets: null,    // ['nexus','npm','github-packages'] 부분집합
    includeSecretBackup: null,
    projectsSync: null,  // Projects 보드 동기화 포함 여부 (#716). null=미설정(신규 false / 이미 설치된 레포는 유지)
    aiPrSummary: null,   // #566 — AI 변경 요약 워크플로우 포함 여부
    // changelog provider 축 (#455 — null=미설정)
    changelogProvider: null, // 'commit'(기본) | 'coderabbit' | 'openai' | 'gemini' | 'claude' | 'ollama' | 'commit'
    changelogBaseUrl: null,  // ollama일 때만 값
    codeReviewCoderabbit: null,
    deployBranch: "",        // 릴리스 PR head 브랜치 (#456). 빈 값=metadata.deploy_branch 미출력
    intent: null,            // 프로젝트 성격 (#485 — app/library/both/none/manual). null=미설정(역추론)
    semverAuto: null,        // semver 자동 승격 (#546). null=미설정 → 신규·기존 모두 true (#814). 명시적 false 만 끈다
    closeOnRelease: null,    // 릴리스 시 완료 이슈 닫기 (#771). null=미설정(신규 true / 기존 레포 키 없음)
    language: null,          // 레포 문구 언어 (#769). null=미설정(신규 en / 기존 레포 ko)
    labelStyle: null,        // 상태 라벨 표기 (#776). null=미설정(신규 en / 기존 레포 ko)
    excludedWorkflows: null, // 설치하지 않을 워크플로우 파일명 (#810). null=없음
    storeLocales: null,      // 스토어 릴리스 노트 언어 (#829). null=미설정 → 현행 동작 유지
    appRelease: null,        // 앱 심사 배포 레포인가 (#553). null=미설정(키 기록 안 함)
    templateVersion: "",
    tempDir: "",
    deployValues: new Map(), // "type.KEY" -> value
    counters: {},
    ...overrides,
  };
}
