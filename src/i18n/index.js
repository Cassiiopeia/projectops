// Message catalog + language resolution for the CLI.
// English is the source of truth: every key must exist in en.js, ko.js may lag behind
// and falls back to English (never to the raw key unless the key is unknown everywhere).
import en from "./en.js";
import ko from "./ko.js";

export const SUPPORTED_LANGS = ["en", "ko"];
const CATALOGS = { en, ko };

let current = "en";
let source = "default";

// "ko", "ko-KR", "ko_KR.UTF-8" -> "ko". Anything else -> "en". Empty -> null (= not specified).
export function normalizeLang(value) {
  const v = String(value ?? "").trim().toLowerCase();
  if (!v) return null;
  return v.startsWith("ko") ? "ko" : "en";
}

// Language of the OS, as Node sees it. Intl works the same on macOS and Windows,
// whereas LANG/LC_ALL are usually empty on Windows, so they are only a fallback.
export function systemLocale(env = process.env) {
  try {
    const l = Intl.DateTimeFormat().resolvedOptions().locale;
    if (l) return l;
  } catch { /* Intl unavailable: fall through */ }
  return env.LC_ALL || env.LC_MESSAGES || env.LANG || "";
}

// Resolution order: --lang > PROJECTOPS_LANG > (CI / non-interactive => en) > system locale > en.
// CI and --force are pinned to English so logs do not change with the runner's locale.
// Returns { lang, source } where source is "flag" | "env" | "ci" | "system" | "default".
export function resolveLang({ flag = null, env = process.env, pinEnglish = false, locale } = {}) {
  const fromFlag = normalizeLang(flag);
  if (fromFlag) return { lang: fromFlag, source: "flag" };
  const fromEnv = normalizeLang(env.PROJECTOPS_LANG);
  if (fromEnv) return { lang: fromEnv, source: "env" };
  if (pinEnglish || env.CI === "true" || env.CI === "1") return { lang: "en", source: "ci" };
  const fromSystem = normalizeLang(locale ?? systemLocale(env));
  if (fromSystem) return { lang: fromSystem, source: "system" };
  return { lang: "en", source: "default" };
}

export function setLang(lang, src = "flag") {
  current = SUPPORTED_LANGS.includes(lang) ? lang : "en";
  source = src;
}
export const getLang = () => current;
export const getLangSource = () => source;

// t("key", { name: "x" }) -> message in the current language. "{name}" placeholders are replaced.
export function t(key, vars) {
  const raw = CATALOGS[current]?.[key] ?? CATALOGS.en[key] ?? key;
  if (!vars) return raw;
  return raw.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m));
}

// Message in English no matter which language is active. Used for run logs,
// which agents read later and which must not change with the user's locale.
export function tEn(key, vars) {
  const raw = CATALOGS.en[key] ?? key;
  if (!vars) return raw;
  return raw.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m));
}
