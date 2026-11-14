// IDE adapter registry — the only extension point.
//
// To support a new IDE:
//   1) write an adapter object (adapter.js contract) in src/core/ide/adapters/<name>.js
//   2) add the import below and put it in the ADAPTERS array
// The orchestrator, prompts and index routing only iterate this array, so no other file needs changes.
import { assertAdapter } from "./adapter.js";
import { claudeAdapter } from "./adapters/claude.js";
import { cursorAdapter } from "./adapters/cursor.js";
import { geminiAdapter } from "./adapters/gemini.js";
import { codexAdapter } from "./adapters/codex.js";
import { copilotAdapter } from "./adapters/copilot.js";
import { piAdapter } from "./adapters/pi.js";
import { piHarnessAdapter } from "./adapters/pi-harness.js";

// Sort by order ascending + check the contract.
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
