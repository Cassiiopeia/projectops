// wizard-prompts.yml 라벨 메타 파서: 파일 위치, 필드 조회, 워크플로우 표시 이름.
// ⚠️ YAML 라이브러리 금지 — 라인 기반 파싱만 한다(외부 의존성 0 + 포맷 관용성).
import { join } from "node:path";
import * as nodeFs from "node:fs";
import { PATHS } from "./paths.js";

// wizard-prompts.yml 위치 (레포 루트 기준 상대경로)
export const LABELS_FILE = ".github/config/wizard-prompts.yml";

// 따옴표 감싸진 값이면 벗기고 trim ("값" → 값).
function unquote(s) {
  const t = s.trim();
  if (t.startsWith('"') && t.endsWith('"') && t.length >= 2) return t.slice(1, -1);
  return t;
}

// wizard-prompts.yml 텍스트 → 파싱 객체 (순수 함수 — 테스트 직접 사용 가능).
// 반환: { fields: Map<조회키, {label?,help?,example?}>, workflowNames: [{key,value}] }
//  - 조회키: "PROJECT_NAME" 또는 "flutter.APP_ARTIFACT_NAME" (dotted 타입 오버라이드)
//  - 구형 1줄(KEY: "라벨")은 fields의 label로 흡수 (label만 의미)
export function parseWizardPrompts(text) {
  const fields = new Map();
  const workflowNames = [];
  let current = null;       // 현재 블록의 fields 엔트리 (들여쓰기 라인 소속처)
  let inWfNames = false;    // _workflow_names 블록 내부 여부

  for (const raw of String(text).split(/\r?\n/)) {
    const line = raw.replace(/\r$/, "");
    if (!line.trim() || line.trim().startsWith("#")) continue; // 빈 줄·주석은 블록을 끊지 않음

    if (!/^\s/.test(line)) {
      // 최상위 키 라인 — 이전 블록 종료
      current = null; inWfNames = false;
      const m = line.match(/^([A-Za-z_][A-Za-z0-9_.\-]*):(.*)$/);
      if (!m) continue;
      const key = m[1];
      const rest = m[2].trim();
      if (key === "_workflow_names") { inWfNames = true; continue; }
      const entry = fields.get(key) || {};
      if (rest) {
        // 구형 1줄: KEY: "라벨" (label로만 사용)
        const q = rest.match(/^"([^"]*)"\s*$/);
        if (q) entry.label = q[1];
      }
      fields.set(key, entry);
      current = entry;
      continue;
    }

    // 들여쓰기 라인 — 현재 블록 소속
    const m = line.match(/^\s+([A-Za-z_][A-Za-z0-9_.\-]*):\s*(.*)$/);
    if (!m) continue;
    if (inWfNames) {
      // "  KEY: "값"" 형식만 인정
      const q = m[2].match(/^"(.*)"\s*$/);
      if (q) workflowNames.push({ key: m[1], value: q[1] });
      continue;
    }
    if (current && (m[1] === "label" || m[1] === "help" || m[1] === "example")) {
      // 블록 내 첫 등장만 채택
      if (current[m[1]] == null) current[m[1]] = unquote(m[2]);
    }
  }
  return { fields, workflowNames };
}

// wizard-prompts.yml을 찾아 읽고 파싱.
// 우선순위: 대상 프로젝트(targetRoot) → 다운로드 원본(tempDir) 폴백 → null.
// WHY 폴백: 신규 통합에서는 copy_config_folder가 configure_workflow_env보다 늦게 실행되어
//          대상에 아직 파일이 없다 — 폴백 없으면 label/help/example이 전부 빈값(KEY명만 출력)이 된다.
// fs 주입 가능(테스트용) — 기본 node:fs.
export function loadWizardPrompts(targetRoot = ".", tempDir = "", fs = nodeFs) {
  const candidates = [join(targetRoot, LABELS_FILE)];
  if (tempDir) candidates.push(join(tempDir, LABELS_FILE));
  for (const p of candidates) {
    if (fs.existsSync(p)) return parseWizardPrompts(fs.readFileSync(p, "utf8"));
  }
  return null;
}

// 필드 조회. field: "label" | "help" | "example".
// 우선순위: "{type}.KEY" 블록 → "KEY" 블록(구형 1줄 포함) → 폴백(label이면 KEY명, 아니면 "").
export function wfField(prompts, type, key, field) {
  if (prompts && prompts.fields) {
    for (const q of [`${type}.${key}`, key]) {
      const v = prompts.fields.get(q)?.[field];
      if (v != null && v !== "") return v;
    }
  }
  return field === "label" ? key : "";
}

// 워크플로우 파일명 → 사람이 읽는 짧은 이름.
// _workflow_names에서 "키가 파일명에 포함되면" 그 값 사용 — 최장 키 우선(REACT-CI vs REACT-CICD 구분).
// 미매칭이면 .yaml/.yml 확장자만 제거해 반환.
export function workflowDisplayName(prompts, filename) {
  const base = String(filename).split("/").pop().split("\\").pop(); // 경로 제거
  let best = null; let bestLen = 0;
  for (const { key, value } of prompts?.workflowNames ?? []) {
    if (base.includes(key) && key.length > bestLen) { best = value; bestLen = key.length; }
  }
  if (best != null) return best;
  return base.replace(/\.ya?ml$/, "");
}
