// Store multi-language setup detection (#843): only finds and reports repos that push one text to many languages without store_locales.
// Changes neither behavior nor version.yml. Output is one line on the finish screen + one migration guide checklist item.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

// Shape of a language folder name (ko, ko-KR, en-US, zh-Hans)
const LOCALE_NAME = /^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$/;
// DELIVER_LOCALES assignment (yaml `KEY: "a,b"`, shell `KEY=a,b`, Ruby `ENV["KEY"] = "a,b"`). A `||` default is not an assignment and is excluded
const DELIVER_LOCALES_ASSIGN = /DELIVER_LOCALES["']?\]?\s*[:=]\s*["']?([A-Za-z0-9_, -]+)/g;
const MINIMUM_LOCALE_COUNT = 2;

/**
 * Collect 3 multi-language store signals: DELIVER_LOCALES with 2+ entries, Play metadata language folders, release-notes language folders
 * null if storeLocales already exists (not null) or there is no signal
 */
export function detectMultiLocaleStore({ root, flutterPath = ".", storeLocales = null }) {
  if (storeLocales != null) return null;
  const appRoot = join(root, flutterPath || ".");
  const signals = [
    ...findDeliverLocales(root, appRoot),
    ...findLocaleDirectories(root, join(appRoot, "android/fastlane/metadata/android"), "play-metadata"),
    ...findLocaleDirectories(root, join(appRoot, "release-notes"), "release-notes"),
  ];
  // Also check the root release-notes only when the root and app folder differ (same would be a duplicate)
  if (appRoot !== join(root, ".")) signals.push(...findLocaleDirectories(root, join(root, "release-notes"), "release-notes"));
  if (signals.length === 0) return null;
  const locales = [...new Set(signals.flatMap((s) => s.locales))];
  return { signals, locales };
}

// DELIVER_LOCALES in workflows (.yml/.yaml) + Fastfiles (ios, android, root)
function findDeliverLocales(root, appRoot) {
  const candidates = [];
  const workflowsDir = join(root, ".github/workflows");
  if (existsSync(workflowsDir)) {
    for (const name of readdirSync(workflowsDir)) {
      if (/\.ya?ml$/.test(name)) candidates.push(join(workflowsDir, name));
    }
  }
  for (const sub of ["ios/fastlane/Fastfile", "android/fastlane/Fastfile", "fastlane/Fastfile"]) {
    candidates.push(join(appRoot, sub));
  }
  const found = [];
  for (const file of new Set(candidates)) {
    if (!isFile(file)) continue;
    const text = readFileSync(file, "utf8");
    for (const match of text.matchAll(DELIVER_LOCALES_ASSIGN)) {
      const locales = match[1].split(",").map((s) => s.trim()).filter((s) => LOCALE_NAME.test(s));
      if (locales.length >= MINIMUM_LOCALE_COUNT) {
        found.push({ source: "deliver-locales", path: toRelative(root, file), locales });
        break; // One hit per file is enough
      }
    }
  }
  return found;
}

// 2+ <dir>/<lang>/ folders count as one signal
function findLocaleDirectories(root, dir, source) {
  if (!existsSync(dir) || !statSync(dir).isDirectory()) return [];
  const locales = readdirSync(dir)
    .filter((name) => LOCALE_NAME.test(name) && statSync(join(dir, name)).isDirectory())
    .sort();
  return locales.length >= MINIMUM_LOCALE_COUNT ? [{ source, path: toRelative(root, dir), locales }] : [];
}

function isFile(path) {
  return existsSync(path) && statSync(path).isFile();
}

// Screen and guide text use the / separator regardless of OS
function toRelative(root, path) {
  return relative(root, path).split("\\").join("/");
}

/**
 * Shared by both entry points (non-interactive, interactive): detect only for an existing repo with storeLocales unset > write trace > return the result
 * null for new installs (the target is repos already running in several languages)
 */
export function detectStoreLocalesHint({ root, existing, paths, trace = null }) {
  if (!existing) return null;
  const hint = detectMultiLocaleStore({
    root, flutterPath: paths?.get?.("flutter") || ".", storeLocales: existing.options?.storeLocales ?? null,
  });
  trace?.event?.("detect", "store-locales-hint", hint ? "multi-locale" : "none", hint
    ? { locales: hint.locales, signals: hint.signals.map((s) => `${s.source}:${s.path}`) }
    : { storeLocalesSet: existing.options?.storeLocales != null });
  return hint;
}
