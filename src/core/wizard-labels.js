// wizard-prompts.yml label metadata parser: file location, field lookup, workflow display names.
// ⚠️ No YAML library — line-based parsing only (zero external dependencies + format tolerance).
import { join } from "node:path";
import * as nodeFs from "node:fs";
import { PATHS } from "./paths.js";
import { getLang } from "../i18n/index.js";

// wizard-prompts.yml location (relative to the repo root)
export const LABELS_FILE = ".github/config/wizard-prompts.yml";

// Strip surrounding quotes and trim ("value" → value).
function unquote(s) {
  const t = s.trim();
  if (t.startsWith('"') && t.endsWith('"') && t.length >= 2) return t.slice(1, -1);
  return t;
}

// wizard-prompts.yml text → parsed object (pure function — tests can use it directly).
// Returns { fields: Map<lookup key, {label?,help?,example?,label_ko?...}>, workflowNames: [{key,value}],
//         workflowNamesByLang: Map<language, [{key,value}]> }
//  - lookup key: "PROJECT_NAME" or "flutter.APP_ARTIFACT_NAME" (dotted type override)
//  - per-language text (#976): label/help/example = English original, label_ko etc. = translation. _workflow_names_ko = translation block
//  - old one-line form (KEY: "label") is absorbed as the label in fields (label only)
export function parseWizardPrompts(text) {
  const fields = new Map();
  const workflowNames = [];
  const workflowNamesByLang = new Map();
  let current = null;       // fields entry of the current block (owner of indented lines)
  let currentWfNames = null; // the list when inside a _workflow_names(_lang) block

  for (const raw of String(text).split(/\r?\n/)) {
    const line = raw.replace(/\r$/, "");
    if (!line.trim() || line.trim().startsWith("#")) continue; // Blank lines and comments do not end a block

    if (!/^\s/.test(line)) {
      // Top-level key line — ends the previous block
      current = null; currentWfNames = null;
      const m = line.match(/^([A-Za-z_][A-Za-z0-9_.\-]*):(.*)$/);
      if (!m) continue;
      const key = m[1];
      const rest = m[2].trim();
      const wfNamesBlock = key.match(/^_workflow_names(?:_([a-z]{2}(?:-[A-Z]{2})?))?$/);
      if (wfNamesBlock) {
        const lang = wfNamesBlock[1];
        if (!lang) currentWfNames = workflowNames;
        else {
          if (!workflowNamesByLang.has(lang)) workflowNamesByLang.set(lang, []);
          currentWfNames = workflowNamesByLang.get(lang);
        }
        continue;
      }
      const entry = fields.get(key) || {};
      if (rest) {
        // Old one-line form: KEY: "label" (used only as label)
        const q = rest.match(/^"([^"]*)"\s*$/);
        if (q) entry.label = q[1];
      }
      fields.set(key, entry);
      current = entry;
      continue;
    }

    // Indented line — belongs to the current block
    const m = line.match(/^\s+([A-Za-z_][A-Za-z0-9_.\-]*):\s*(.*)$/);
    if (!m) continue;
    if (currentWfNames) {
      // Only the "  KEY: "value"" form is accepted
      const q = m[2].match(/^"(.*)"\s*$/);
      if (q) currentWfNames.push({ key: m[1], value: q[1] });
      continue;
    }
    // Field name: label | help | example; translations use a _lang suffix (label_ko)
    if (current && /^(label|help|example)(_[a-z]{2}(-[A-Z]{2})?)?$/.test(m[1])) {
      // Take only the first occurrence in a block
      if (current[m[1]] == null) current[m[1]] = unquote(m[2]);
    }
  }
  return { fields, workflowNames, workflowNamesByLang };
}

// Find, read and parse wizard-prompts.yml.
// Priority: target project (targetRoot) → downloaded original (tempDir) fallback → null.
// WHY fallback: in a new integration, copy_config_folder runs after configure_workflow_env, so the
//          target has no file yet — without the fallback, label/help/example are all empty (only KEY names shown).
// fs can be injected (for tests) — default node:fs.
export function loadWizardPrompts(targetRoot = ".", tempDir = "", fs = nodeFs) {
  const candidates = [join(targetRoot, LABELS_FILE)];
  if (tempDir) candidates.push(join(tempDir, LABELS_FILE));
  for (const p of candidates) {
    if (fs.existsSync(p)) return parseWizardPrompts(fs.readFileSync(p, "utf8"));
  }
  return null;
}

// Field lookup. field: "label" | "help" | "example", lang: screen language (default: current CLI language)
// Priority: "{type}.KEY" block → "KEY" block (including the old one-line form) → fallback (KEY name for label, else "").
// Per block, translation (label_ko) first, else the English original (label)
export function wfField(prompts, type, key, field, lang = getLang()) {
  if (prompts && prompts.fields) {
    for (const q of [`${type}.${key}`, key]) {
      const entry = prompts.fields.get(q);
      for (const name of [`${field}_${lang}`, field]) {
        const v = entry?.[name];
        if (v != null && v !== "") return v;
      }
    }
  }
  return field === "label" ? key : "";
}

// Workflow file name → short human-readable name.
// Use the _workflow_names value whose "key is contained in the file name" — longest key first (tells REACT-CI from REACT-CICD).
// If none match, strip only the .yaml/.yml extension. If the language translation block (_workflow_names_ko) has the key, use that value
export function workflowDisplayName(prompts, filename, lang = getLang()) {
  const base = String(filename).split("/").pop().split("\\").pop(); // Strip the path
  const translated = new Map((prompts?.workflowNamesByLang?.get(lang) ?? []).map(({ key, value }) => [key, value]));
  let best = null; let bestLen = 0;
  for (const { key, value } of prompts?.workflowNames ?? []) {
    if (base.includes(key) && key.length > bestLen) { best = translated.get(key) ?? value; bestLen = key.length; }
  }
  if (best != null) return best;
  return base.replace(/\.ya?ml$/, "");
}
