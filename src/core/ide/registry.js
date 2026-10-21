// IDE 어댑터 레지스트리 — 유일한 확장 지점.
//
// 새 IDE를 지원하려면:
//   1) src/core/ide/adapters/<name>.js 에 어댑터 객체(adapter.js 계약) 작성
//   2) 아래에 import 추가하고 ADAPTERS 배열에 넣기
// 오케스트레이터·프롬프트·index 라우팅은 이 배열만 순회하므로 다른 파일은 손대지 않는다.
import { assertAdapter } from "./adapter.js";
import { claudeAdapter } from "./adapters/claude.js";
import { cursorAdapter } from "./adapters/cursor.js";
import { geminiAdapter } from "./adapters/gemini.js";
import { codexAdapter } from "./adapters/codex.js";
import { copilotAdapter } from "./adapters/copilot.js";
import { piAdapter } from "./adapters/pi.js";
import { piHarnessAdapter } from "./adapters/pi-harness.js";

// order 오름차순 정렬 + 계약 검증.
export const ADAPTERS = [
  claudeAdapter,
  cursorAdapter,
  geminiAdapter,
  codexAdapter,
  copilotAdapter,
  piAdapter,
  piHarnessAdapter,
].map(assertAdapter).sort((a, b) => (a.order ?? 100) - (b.order ?? 100));

export function adapterById(id) {
  return ADAPTERS.find((a) => a.id === id) || null;
}
