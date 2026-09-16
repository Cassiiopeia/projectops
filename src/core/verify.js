// 설치 후 검증 (#549) — 설치된 워크플로우를 다시 읽어 "이대로 돌아가는가"를 본다.
//
// 왜 설치 전이 아니라 후인가: 치환은 파일 단위로 흩어져 일어나고 auto 토큰은 resolver 결과에
// 의존한다. 최종 디스크 내용을 보는 것이 실제로 배포될 것과 같은 것을 보는 유일한 방법이다.
import { join } from "node:path";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { PATHS } from "./paths.js";

// 치환 대상이 아닌 토큰 — 워크플로우 스크립트 안의 heredoc 구분자다. 값이 아니라 문법이므로
// 미치환 검사에서 제외한다. (예: cat <<'__SUH_FILE_CONTENT_EOF__')
const SENTINEL_RE = /^__SUH_[A-Z0-9_]*__$/;
const PLACEHOLDER_RE = /__[A-Z][A-Z0-9_]*__/g;

// 주석으로 죽어 있는 줄 — 실행되지 않으므로 검사 대상이 아니다.
// 템플릿에는 "[선택] ..." 예시 스텝이 통째로 주석 처리돼 들어 있는데, 이걸 세면
// 쓰지도 않는 Secret을 "등록하세요"라고 안내하게 된다.
const isCommented = (line) => /^\s*#/.test(line);

// 검사 대상 파일 목록. 호출부가 명시하지 않으면 설치된 워크플로우 전체를 스캔한다
// (복사 결과 목록을 조합해 넘기는 것보다, 최종 디스크 상태를 그대로 보는 쪽이 목적에 맞다).
function listWorkflowFiles(workflowsDir, filenames) {
  if (filenames && filenames.length) return filenames;
  if (!existsSync(workflowsDir)) return [];
  try {
    return readdirSync(workflowsDir, { withFileTypes: true })
      .filter((e) => e.isFile() && /\.ya?ml$/.test(e.name))
      .map((e) => e.name)
      .sort();
  } catch {
    return [];
  }
}

function readLines(workflowsDir, filename) {
  const p = join(workflowsDir, filename);
  if (!existsSync(p)) return null;
  try {
    return readFileSync(p, "utf8").split(/\r?\n/);
  } catch {
    return null;
  }
}

// 미치환 플레이스홀더 스캔.
// auto 토큰 계산이 실패해도(예: application.yaml을 못 찾아 경로가 빈 문자열) 그 줄을 건드리지
// 않고 넘어가므로, __APPLICATION_YML_DIR__ 이 그대로 남은 워크플로우가 "설치 성공"으로 끝난다.
// 문제는 배포 시점에야 그 이름의 디렉터리가 만들어지며 드러난다.
//
// 반환: [{ filename, line, token, text }] — 사람이 바로 고칠 수 있게 줄 번호까지 준다.
export function scanUnsubstituted(workflowsDir, filenames = []) {
  const found = [];
  for (const filename of listWorkflowFiles(workflowsDir, filenames)) {
    const lines = readLines(workflowsDir, filename);
    if (!lines) continue;
    lines.forEach((text, i) => {
      if (isCommented(text)) return;
      for (const token of text.match(PLACEHOLDER_RE) || []) {
        if (SENTINEL_RE.test(token)) continue;
        found.push({ filename, line: i + 1, token, text: text.trim() });
      }
    });
  }
  return found;
}

// GITHUB_TOKEN은 Actions가 자동 주입하므로 사용자가 등록할 대상이 아니다.
const AUTO_SECRETS = new Set(["GITHUB_TOKEN"]);

// 없어도 워크플로우가 도는 secret — 폴백이 문서화돼 있다. 필수와 섞어 "등록해야 동작합니다"라고
// 하면 안내 자체를 못 믿게 되므로 분리한다.
//   MODEL_API_KEY      → 없으면 GitHub Models(무료) → commit 규칙 fallback (#455 provider 사다리)
//   _GITHUB_PAT_TOKEN  → 없으면 GITHUB_TOKEN으로 머지하고 후속 워크플로우를 직접 깨운다 (#551)
export const OPTIONAL_SECRETS = new Set(["MODEL_API_KEY", "_GITHUB_PAT_TOKEN"]);

const SECRET_RE = /secrets\.([A-Z_][A-Z0-9_]*)/g;

// 설치된 워크플로우가 요구하는 GitHub Secret 목록.
// 완료 화면이 아무것도 안내하지 않는 바람에, 배포 워크플로우가 실제로 필요로 하는
// SERVER_HOST·SSH_KEY 같은 값이 드러나지 않았다. 설치 직후 상태로는 배포가 돌지 않는데
// 그 사실을 알 방법이 없다.
//
// 반환: Map<secretName, string[] 그 secret을 쓰는 파일명> (이름 오름차순)
export function collectRequiredSecrets(workflowsDir, filenames = []) {
  const out = new Map();
  for (const filename of listWorkflowFiles(workflowsDir, filenames)) {
    const lines = readLines(workflowsDir, filename);
    if (!lines) continue;
    for (const line of lines) {
      if (isCommented(line)) continue;
      for (const m of line.matchAll(SECRET_RE)) {
        const name = m[1];
        if (AUTO_SECRETS.has(name) || OPTIONAL_SECRETS.has(name)) continue;
        if (!out.has(name)) out.set(name, []);
        const users = out.get(name);
        if (!users.includes(filename)) users.push(filename);
      }
    }
  }
  return new Map([...out.entries()].sort(([a], [b]) => a.localeCompare(b)));
}

// 설치 직후 한 번에 돌리는 진입점. targetRoot 기준으로 워크플로우 폴더를 찾는다.
// 반환: { unresolved: [...], secrets: Map, ok: boolean }
export function verifyInstall(targetRoot = ".", filenames = []) {
  const workflowsDir = join(targetRoot, PATHS.workflowsDir);
  const unresolved = scanUnsubstituted(workflowsDir, filenames);
  const secrets = collectRequiredSecrets(workflowsDir, filenames);
  return { unresolved, secrets, ok: unresolved.length === 0 };
}
