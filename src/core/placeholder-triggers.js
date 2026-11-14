// Detect workflows that keep both an automatic trigger and sample values (#662)
// Sample values (your-project, etc.) slip past the unreplaced token (__X__) check, so doctor passed while failed runs piled up on every push or label.
// ⚠️ Line-based, no YAML parser (zero dependencies — the installer CLI has empty dependencies).
import { join } from "node:path";
import { existsSync, readFileSync, readdirSync } from "node:fs";

// The 3 triggers a person must fire by hand — everything else counts as automatic
const MANUAL_EVENTS = new Set(["workflow_dispatch", "workflow_call", "repository_dispatch"]);

// Sample value test: your-/your_ prefixed words, example.com-style domains, unreplaced tokens (excluding heredoc delimiters __SUH_*__)
const PLACEHOLDER_VALUE_RES = [
  /(^|[^a-z0-9])your[-_][a-z0-9]/i,
  /(^|[.@/])example\.(com|org|net)\b/i,
  /__(?!SUH_)[A-Z][A-Z0-9_]*__/,
];

// Only env-style lines: `  KEY: "value"` (avoids false hits on URLs and text inside run scripts)
const ENV_LINE_RE = /^\s*([A-Z][A-Z0-9_]*):\s*(?:"([^"]*)"|'([^']*)'|([^\s#][^#]*?))\s*(?:#.*)?$/;

const isCommented = (line) => /^\s*#/.test(line);

/**
 * on: block > event names (inline `on: push`, `on: [a, b]`, and block form — 3 shapes)
 */
export function parseTriggerEvents(text) {
  const lines = String(text || "").split(/\r?\n/);
  const start = lines.findIndex((l) => /^(on|"on"|'on'):/.test(l));
  if (start < 0) return [];
  const inline = lines[start].replace(/^[^:]*:\s*/, "").replace(/#.*$/, "").trim();
  if (inline) return inline.replace(/^\[|\]$/g, "").split(",").map((s) => s.trim()).filter(Boolean);

  // Block form: only keys at the indent depth of the first child line count as events
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
 * Workflow body > env lines that still hold sample values [{ key, value, line }]
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
 * Installed workflow folder > files with both an automatic trigger and sample values [{ file, triggers, values }]
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
