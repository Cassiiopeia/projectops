// 버전 비교: v 접두 제거, 3자리 숫자 비교, 누락 자리=0
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

// breaking-changes.json에서 current < ver <= target 범위 항목 수집.
// ⚠️ target은 하드코딩 1.3.14가 아니라 실제 templateVersion을 넘긴다 (D2).
// _ 로 시작하는 키(메타) 제외. severity critical / 그 외(warning).
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

// 항목 문구 > 화면 언어: ko면 title_ko/message_ko, 없거나 그 외 언어면 영어 원문(title/message)
// 영어 키가 정본 — 구버전 CLI는 main의 이 파일에서 title/message만 읽음 (#988)
export function localizeBreakingEntry(entry, lang) {
  const pickField = (field) => {
    const koreanText = lang === "ko" ? entry?.[`${field}_ko`] : null;
    return koreanText || entry?.[field] || "";
  };
  return { title: pickField("title"), message: pickField("message") };
}
