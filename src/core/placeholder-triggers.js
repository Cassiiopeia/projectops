// 자동 트리거 + 예시 값이 함께 남은 워크플로우 감지 (#662)
// 예시 값(your-project 등)은 미치환 토큰(__X__) 검사에 걸리지 않아, 푸시·라벨마다 실패 런이 쌓여도 doctor 가 통과시켰다.
// ⚠️ YAML 파서 없이 라인 단위로 본다 (의존성 0 — 설치 CLI 는 dependencies 가 비어 있다).
import { join } from "node:path";
import { existsSync, readFileSync, readdirSync } from "node:fs";

// 사람이 직접 눌러야 도는 트리거 3개 — 나머지는 전부 자동 트리거로 본다
const MANUAL_EVENTS = new Set(["workflow_dispatch", "workflow_call", "repository_dispatch"]);

// 예시 값 판정: your-/your_ 접두 단어, example.com 류 도메인, 미치환 토큰 (heredoc 구분자 __SUH_*__ 제외)
const PLACEHOLDER_VALUE_RES = [
  /(^|[^a-z0-9])your[-_][a-z0-9]/i,
  /(^|[.@/])example\.(com|org|net)\b/i,
  /__(?!SUH_)[A-Z][A-Z0-9_]*__/,
];

// 환경변수형 줄만 본다: `  KEY: "값"` (run 스크립트 안 URL·문구 오탐 방지)
const ENV_LINE_RE = /^\s*([A-Z][A-Z0-9_]*):\s*(?:"([^"]*)"|'([^']*)'|([^\s#][^#]*?))\s*(?:#.*)?$/;

const isCommented = (line) => /^\s*#/.test(line);

/**
 * on: 블록 > 이벤트 이름 목록 (인라인 `on: push`, `on: [a, b]`, 블록 형식 3가지)
 */
export function parseTriggerEvents(text) {
  const lines = String(text || "").split(/\r?\n/);
  const start = lines.findIndex((l) => /^(on|"on"|'on'):/.test(l));
  if (start < 0) return [];
  const inline = lines[start].replace(/^[^:]*:\s*/, "").replace(/#.*$/, "").trim();
  if (inline) return inline.replace(/^\[|\]$/g, "").split(",").map((s) => s.trim()).filter(Boolean);

  // 블록: 첫 하위 줄의 들여쓰기 깊이에 있는 키만 이벤트로 센다
  const events = [];
  let depth = null;
  for (const line of lines.slice(start + 1)) {
    if (!line.trim() || isCommented(line)) continue;
    const indent = line.match(/^\s*/)[0].length;
    if (indent === 0) break;
    if (depth === null) depth = indent;
    if (indent !== depth) continue;
    const key = line.trim().match(/^([A-Za-z_]+):/);
    if (key) events.push(key[1]);
  }
  return events;
}

/**
 * 워크플로우 본문 > 예시 값이 남은 환경변수 줄 [{ key, value, line }]
 */
export function findPlaceholderValues(text) {
  const found = [];
  String(text || "").split(/\r?\n/).forEach((line, index) => {
    if (isCommented(line)) return;
    const match = line.match(ENV_LINE_RE);
    if (!match) return;
    const value = match[2] ?? match[3] ?? match[4] ?? "";
    if (PLACEHOLDER_VALUE_RES.some((re) => re.test(value))) {
      found.push({ key: match[1], value, line: index + 1 });
    }
  });
  return found;
}

/**
 * 설치된 워크플로우 폴더 > 자동 트리거와 예시 값을 함께 가진 파일 [{ file, triggers, values }]
 */
export function scanPlaceholderTriggers(workflowsDir) {
  if (!existsSync(workflowsDir)) return [];
  const files = readdirSync(workflowsDir).filter((f) => /\.ya?ml$/.test(f)).sort();
  const result = [];
  for (const file of files) {
    let text;
    try { text = readFileSync(join(workflowsDir, file), "utf8"); } catch { continue; }
    const triggers = parseTriggerEvents(text).filter((e) => !MANUAL_EVENTS.has(e));
    if (!triggers.length) continue;
    const values = findPlaceholderValues(text);
    if (values.length) result.push({ file, triggers, values });
  }
  return result;
}
