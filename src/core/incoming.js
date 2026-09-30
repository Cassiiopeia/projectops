// 건너뛴 워크플로의 새 템플릿 보관소 (#654).
// 사용자가 수정한 워크플로는 덮어쓰지 않고 유지한다. 대신 "새 템플릿이 어떻게 다른지"를
// 비교할 수 있도록 추적되지 않는 자리에 사본을 남긴다.
// 절대 .github/workflows 에 쓰지 않는다 — 거기 생긴 파일은 GitHub 이 실제 워크플로로 실행한다.
import { join } from "node:path";
import { writeText } from "./fsutil.js";

export const INCOMING_DIR = ".github/.projectops/incoming";
// 폴더가 스스로 추적 제외 규칙을 들고 다닌다 (logs/.gitignore 와 같은 방식, 루트 .gitignore 무수정)
export const INCOMING_GITIGNORE = [
  "# projectops 가 건너뛴 워크플로의 새 템플릿 사본 — 저장소에 추적하지 않습니다.",
  "# 병합 검토용 임시 자료이며 실행할 때마다 최신으로 덮어씁니다.",
  "*",
  "!.gitignore",
  "",
].join("\n");

const toLines = (s) => {
  const lines = String(s).split(/\r?\n/);
  if (lines.length && lines[lines.length - 1] === "") lines.pop(); // 끝 개행이 만드는 빈 줄 제외
  return lines;
};

// 줄 단위 추가/삭제 개수. LCS 기반이라 줄이 이동만 한 경우도 과대 계상하지 않는다.
// removed: 사용자본에만 있는 줄, added: 새 템플릿에만 있는 줄.
export function lineDiffCounts(userText, incomingText) {
  const a = toLines(userText);
  const b = toLines(incomingText);
  // 공통 접두/접미는 LCS에서 뺀다 (워크플로 대부분이 같아 표가 작아진다)
  let s = 0;
  while (s < a.length && s < b.length && a[s] === b[s]) s++;
  let ea = a.length; let eb = b.length;
  while (ea > s && eb > s && a[ea - 1] === b[eb - 1]) { ea--; eb--; }
  const x = a.slice(s, ea); const y = b.slice(s, eb);
  if (x.length * y.length > 25_000_000) {
    // 비정상적으로 큰 파일 — 정확도 대신 크기 차이로 근사한다 (실패시키지 않는다)
    return { added: y.length, removed: x.length };
  }
  let prev = new Array(y.length + 1).fill(0);
  for (let i = 1; i <= x.length; i++) {
    const cur = new Array(y.length + 1).fill(0);
    for (let j = 1; j <= y.length; j++) {
      cur[j] = x[i - 1] === y[j - 1] ? prev[j - 1] + 1 : Math.max(prev[j], cur[j - 1]);
    }
    prev = cur;
  }
  const common = prev[y.length];
  return { added: y.length - common, removed: x.length - common };
}

// incoming 폴더에 새 템플릿을 저장한다. 반환: 대상 기준 상대 경로(항상 '/').
export function saveIncoming(targetRoot, filename, content) {
  writeText(join(targetRoot, INCOMING_DIR, ".gitignore"), INCOMING_GITIGNORE);
  writeText(join(targetRoot, INCOMING_DIR, filename), content);
  return `${INCOMING_DIR}/${filename}`;
}
