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
    // changelog provider 축 (#455 — null=미설정)
    changelogProvider: null, // 'github-ai'(기본) | 'coderabbit' | 'openai' | 'gemini' | 'claude' | 'ollama' | 'commit'
    changelogBaseUrl: null,  // ollama일 때만 값
    codeReviewCoderabbit: null,
    deployBranch: "",        // 릴리스 PR head 브랜치 (#456). 빈 값=metadata.deploy_branch 미출력
    intent: null,            // 프로젝트 성격 (#485 — app/library/both/none/manual). null=미설정(역추론)
    semverAuto: null,        // semver 자동 승격 (#546). null=미설정(신규 통합 true / 기존 레포 false)
    appRelease: null,        // 앱 심사 배포 레포인가 (#553). null=미설정(키 기록 안 함)
    templateVersion: "",
    tempDir: "",
    deployValues: new Map(), // "type.KEY" -> value
    counters: {},
    ...overrides,
  };
}
