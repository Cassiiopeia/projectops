// 상태 라벨 표기(#776): 영문 표준("en")과 기존 한글("ko").
// 템플릿 원본은 영문 하나다. 한글 모드는 복사 직후 이름만 되돌려 만든다 —
// 한글 사본을 따로 두면 두 벌이 어긋난다.
import { join } from "node:path";
import { existsSync, readFileSync, writeFileSync, readdirSync } from "node:fs";

export const LABEL_STYLES = ["en", "ko"];

// [영문 표준, 한글 기존]
export const LABEL_PAIRS = [
  ["status: todo", "작업전"],
  ["status: in progress", "작업중"],
  ["status: needs review", "담당자확인"],
  ["status: feedback", "피드백"],
  ["status: done", "작업완료"],
  ["status: on hold", "보류"],
  ["status: cancelled", "취소"],
  ["priority: urgent", "긴급"],
  ["documentation", "문서"],
];
const EN_TO_KO = new Map(LABEL_PAIRS);

// version.yml 에 저장값이 없을 때의 결정. 신규 설치는 영문, 이미 설치된 레포는 한글 유지.
// 이미 쓰는 레포의 라벨 이름이 업데이트만으로 바뀌면 Projects 보드 매핑이 조용히 멈추기 때문이다.
export function resolveLabelStyle({ flag, stored, existing }) {
  if (LABEL_STYLES.includes(flag)) return flag;
  if (LABEL_STYLES.includes(stored)) return stored;
  return existing ? "ko" : "en";
}

function rewrite(file, fn) {
  if (!existsSync(file)) return false;
  const before = readFileSync(file, "utf8");
  const after = fn(before);
  if (after === before) return false;
  writeFileSync(file, after);
  return true;
}

const quoted = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// 한글 모드: 복사된 파일의 라벨 이름을 한글로 되돌린다. 영문 모드는 아무것도 하지 않는다.
// 반환: 바뀐 파일의 상대경로 목록.
export function applyLabelStyle(targetRoot, style) {
  if (style !== "ko") return [];
  const changed = [];
  const gh = join(targetRoot, ".github");

  // 라벨 정의: name 줄만 바꾸고, 이름 변경용 from_name 줄은 지운다(이미 한글이라 필요 없다).
  const labelsFile = join(gh, "config", "issue-labels.yml");
  if (rewrite(labelsFile, (txt) => {
    let out = txt.replace(/^\s*from_name:.*\n/gm, "");
    for (const [en, ko] of LABEL_PAIRS) {
      out = out.replace(new RegExp(`^(- name:\\s*)"?${quoted(en)}"?\\s*$`, "gm"), `$1${ko}`);
    }
    return out;
  })) changed.push(".github/config/issue-labels.yml");

  // 이슈 템플릿 기본 라벨: front matter 의 labels 줄만 대상으로 한다.
  const tplDir = join(gh, "ISSUE_TEMPLATE");
  if (existsSync(tplDir)) {
    for (const name of readdirSync(tplDir).filter((f) => f.endsWith(".md"))) {
      const f = join(tplDir, name);
      if (rewrite(f, (txt) => txt.replace(/^labels:\s*\[(.*)\]\s*$/m, (m, inner) => {
        let list = inner;
        for (const [en, ko] of LABEL_PAIRS) list = list.split(`"${en}"`).join(ko).split(`'${en}'`).join(ko);
        return `labels: [${list}]`;
      }))) changed.push(`.github/ISSUE_TEMPLATE/${name}`);
    }
  }

  // QA 이슈 생성 봇이 붙이는 기본 라벨
  const bot = join(gh, "workflows", "PROJECT-COMMON-QA-ISSUE-CREATION-BOT.yaml");
  if (rewrite(bot, (txt) => txt.replace(/labels:\s*\['status: todo'\]/g, `labels: ['${EN_TO_KO.get("status: todo")}']`))) {
    changed.push(".github/workflows/PROJECT-COMMON-QA-ISSUE-CREATION-BOT.yaml");
  }
  return changed;
}
