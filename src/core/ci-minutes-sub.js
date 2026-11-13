// CI 사용 시간 절약 치환 (#1114) — version.yml options.ci_minutes_saver: true 일 때만.
// 비공개 레포는 Actions 분이 과금된다. 같은 커밋에 두 번 도는 CI·문서 변경 CI·macOS 러너(분당 10배)를 줄인다.
// 꺼져 있으면 호출되지 않는다 (설치 결과 바이트 동일). 패턴을 못 찾으면(사용자 수정본) 그 변환만 건너뛴다.
// 브랜치 치환보다 먼저 돈다 — 템플릿 원문(develop) 기준으로 패턴을 맞춘다.

// PR 에서 문서만 바뀐 경우 CI 생략 (코드 경로를 고르는 paths 는 레포마다 달라 템플릿이 정할 수 없다)
const DOCS_ONLY_PATHS_IGNORE = `    paths-ignore: ["**/*.md", "docs/**", "LICENSE"]   # ci_minutes_saver: docs-only changes skip CI\n`;

// on: 아래 push: 이벤트 블록 (자식 줄 4칸 이상). branches 필터만 있는 블록일 때만 지운다
const PUSH_BLOCK_RE = /^ {2}push:[ \t]*\n((?: {4,}.*\n|[ \t]*\n)*)/m;

// 같은 변경에 PR 과 push 로 두 번 도는 CI > push 제거 (PR 만)
function dropPushTrigger(s) {
  const m = s.match(PUSH_BLOCK_RE);
  if (!m) return s;
  const children = m[1].split("\n").filter((line) => line.trim() && !line.trim().startsWith("#"));
  const isBranchFilterOnly = children.every((line) => /^\s+(branches:|-\s)/.test(line));
  return isBranchFilterOnly ? s.replace(PUSH_BLOCK_RE, "") : s;
}

// 이벤트(pull_request · push) 바로 아래에 문서 경로 제외 추가
function addDocsPathsIgnore(s, event) {
  const re = new RegExp(`^( {2}${event}:[ \\t]*\\n)`, "m");
  if (!re.test(s) || s.includes("ci_minutes_saver: docs-only")) return s;
  return s.replace(re, `$1${DOCS_ONLY_PATHS_IGNORE}`);
}

// iOS(macOS 러너) 빌드 자동 실행 끔 — 수동 실행 입력 enable_ios 로만 켠다
function disableIosByDefault(s) {
  // 한 글자 늘어난 만큼 뒤 공백 하나를 먹어 주석 열을 맞춘다
  return s.replace(/^( {2}ENABLE_IOS: )"true" ?/m, `$1"false"`);
}

// 파일 이름(정확 일치) > 적용할 변환 목록. 스토어 배포·댓글 트리거 빌드는 넣지 않는다
export const CI_MINUTES_SAVER_RULES = new Map([
  ["PROJECT-FLUTTER-CI.yaml", [dropPushTrigger, (s) => addDocsPathsIgnore(s, "pull_request"), disableIosByDefault]],
  ["PROJECT-PYTHON-CI.yaml", [dropPushTrigger, (s) => addDocsPathsIgnore(s, "pull_request")]],
  ["PROJECT-SPRING-NEXUS-CI.yml", [dropPushTrigger, (s) => addDocsPathsIgnore(s, "pull_request")]],
  // PR 트리거가 없어 push 는 남기고 문서 변경만 거른다
  ["PROJECT-REACT-CI.yaml", [(s) => addDocsPathsIgnore(s, "push")]],
  // 푸시와 무관한 작업 > 수동 실행만
  ["PROJECT-COMMON-SECRET-FILE-UPLOAD.yaml", [dropPushTrigger]],
]);

export function substituteCiMinutesSaver(content, filename = "") {
  const transforms = CI_MINUTES_SAVER_RULES.get(filename);
  if (!transforms) return content;
  return transforms.reduce((s, transform) => transform(s), String(content));
}
