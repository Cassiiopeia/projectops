// Version compare: strip v prefix, compare 3 numeric parts, missing part = 0
export function compareVersions(a, b) {
  const parse = (v) => String(v).replace(/^v/, "").split(".").map((n) => parseInt(n, 10) || 0);
  const pa = parse(a), pb = parse(b);
  for (let i = 0; i < 3; i++) {
    const x = pa[i] ?? 0, y = pb[i] ?? 0;
    if (x > y) return 1;
    if (x < y) return -1;
  }
  return 0;
}

// Collect breaking-changes.json entries in the range current < ver <= target.
// ⚠️ target is the real templateVersion, not a hardcoded 1.3.14 (D2).
// Skip keys starting with _ (meta). severity: critical / anything else (warning).
export function collectBreaking(json, current, target) {
  const critical = [], warnings = [];
  for (const [ver, entry] of Object.entries(json || {})) {
    if (ver.startsWith("_")) continue;
    if (compareVersions(current, ver) < 0 && compareVersions(ver, target) <= 0) {
      const rec = { version: ver, ...entry };
      (entry?.severity === "critical" ? critical : warnings).push(rec);
    }
  }
  return { critical, warnings };
}

// Entry text > screen language: ko uses title_ko/message_ko; missing or other languages use the English original (title/message)
// English keys are the source of truth — old CLIs read only title/message from this file on main (#988)
export function localizeBreakingEntry(entry, lang) {
  const pickField = (field) => {
    const koreanText = lang === "ko" ? entry?.[`${field}_ko`] : null;
    return koreanText || entry?.[field] || "";
  };
  return { title: pickField("title"), message: pickField("message") };
}
