// 워크플로우 브랜치 치환 (#477) — 대상 레포의 브랜치 전략이 표준(main/develop)과 다를 때
// 복사된 워크플로우의 브랜치 리터럴을 설정값으로 교체한다.
// 표준값이면 입력을 그대로 반환(no-op) — 템플릿 원본과 바이트 동일이 유지되어야
// isUnchanged 스킵 로직과 "표준 레포 무변화" 계약이 깨지지 않는다.
//
// 치환 대상은 실측 전수조사(#477)된 패턴만 다룬다 (글롭·전면 replace 금지 — 오살 방지):
//   1) 트리거 인라인:   branches: ["main"] / [develop] / [ develop ] / ["develop"]
//   2) 트리거 멀티라인: "  - main" / "  - develop" 단독 라인 (뒤 주석 허용)
//   3) 릴리스 가드:     == 'develop'  (RELEASE-CHANGELOG automerge head 가드)
//   4) step 내부:       git fetch origin main  (RELEASE-CHANGELOG 커밋 분석)
//   5) 배포 트리거(#1114): 배포 워크플로 파일만, main > deployTriggerBranch (아래 DEPLOY_TRIGGER_WORKFLOWS)

// main(기본 브랜치) 계열 치환
function subDefault(s, db) {
  s = s.replace(/^(\s*branches:\s*\[\s*["']?)main(["']?\s*\])/gm, `$1${db}$2`);
  s = s.replace(/^(\s*-\s*)main(\s*(?:#.*)?)$/gm, `$1${db}$2`);
  s = s.replace(/\bgit fetch origin main\b/g, `git fetch origin ${db}`);
  return s;
}

// develop(개발/릴리스 head 브랜치) 계열 치환
function subDeploy(s, dev) {
  s = s.replace(/^(\s*branches:\s*\[\s*["']?)develop(["']?\s*\])/gm, `$1${dev}$2`);
  s = s.replace(/^(\s*-\s*)develop(\s*(?:#.*)?)$/gm, `$1${dev}$2`);
  s = s.replace(/== 'develop'/g, `== '${dev}'`);
  return s;
}

// 푸시되면 배포가 도는 워크플로 (파일 이름 정확 일치). 기본 브랜치와 배포 브랜치를 나눈 레포에서만 쓴다.
// 공통 워크플로(버전 올림 · README 버전 · 릴리스 노트 · 이슈 닫기)는 여기 없다: 기본 브랜치를 따른다.
// 배포 워크플로를 추가하면 이 표에도 넣는다 (안 넣으면 그 파일은 기본 브랜치에서 배포가 돈다)
export const DEPLOY_TRIGGER_WORKFLOWS = new Set([
  "PROJECT-FLUTTER-ANDROID-FIREBASE-CICD.yaml", "PROJECT-FLUTTER-ANDROID-PLAYSTORE-CICD.yaml",
  "PROJECT-FLUTTER-ANDROID-SELFHOSTED-CICD.yaml", "PROJECT-FLUTTER-IOS-TESTFLIGHT.yaml",
  "PROJECT-SPRING-SIMPLE-CICD.yaml", "PROJECT-PYTHON-SIMPLE-CICD.yaml", "PROJECT-REACT-CICD.yaml",
  "PROJECT-COMMON-VERCEL-DEPLOY.yaml", "PROJECT-NODE-NPM-PUBLISH.yaml",
  "PROJECT-SPRING-NEXUS-PUBLISH.yml", "PROJECT-SPRING-GITHUB-PACKAGES-PUBLISH.yml",
]);

// 배포 트리거 브랜치 치환: 트리거 · 체크아웃 ref · pull · 실행 조건의 main
function subDeployTrigger(s, trigger) {
  s = s.replace(/^(\s*branches:\s*\[\s*["']?)main(["']?\s*\])/gm, `$1${trigger}$2`);
  s = s.replace(/^(\s*-\s*)main(\s*(?:#.*)?)$/gm, `$1${trigger}$2`);
  s = s.replace(/^(\s*ref:\s*)main(\s*(?:#.*)?)$/gm, `$1${trigger}$2`);
  s = s.replace(/\bgit pull origin main\b/g, `git pull origin ${trigger}`);
  s = s.replace(/refs\/heads\/main\b/g, `refs/heads/${trigger}`);
  return s;
}

// content에 브랜치 설정을 적용한 결과를 반환. branches 미지정/표준값이면 원본 그대로.
// 플레이스홀더 2단 치환: 값 충돌 방지 (예: 기본 브랜치=develop인 레포에서 main→develop 치환 결과가
// 곧이어 develop→X 치환에 다시 걸리는 연쇄 오염을 차단).
// filename: 배포 트리거 치환(#1114)이 배포 워크플로 파일에만 걸리게 하는 기준. 없으면 배포 트리거 치환은 건너뛴다.
export function substituteBranches(content, branches = null, filename = "") {
  if (!branches) return content;
  const db = branches.defaultBranch || "main";
  const dev = branches.deployBranch || "develop";
  const trigger = branches.deployTriggerBranch || "";
  let s = String(content);
  const T_DB = "__PJOPS_DEFAULT__";
  const T_DEV = "__PJOPS_DEPLOY__";
  const T_TRIGGER = "__PJOPS_TRIGGER__";
  // 배포 워크플로의 main 은 기본 브랜치가 아니라 배포 트리거 브랜치로 간다 (먼저 자리표시자로 빼 둠)
  if (trigger && DEPLOY_TRIGGER_WORKFLOWS.has(filename)) s = subDeployTrigger(s, T_TRIGGER);
  if (dev !== "develop") s = subDeploy(s, T_DEV);
  if (db !== "main") s = subDefault(s, T_DB);
  return s.replaceAll(T_TRIGGER, trigger).replaceAll(T_DEV, dev).replaceAll(T_DB, db);
}
