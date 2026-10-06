// 레거시 마이그레이션 진입점 (#470) — 신호 기반·멱등.
// 감지(registry × rules) → 계획 표시 → safe 티어 확인 1회 → 적용 → confirm 티어 안내.
// 버전 번호를 믿지 않는다: 절반의 레거시 레포는 version.yml에 template 메타가 없다(실측).
import { MIGRATIONS } from "./registry.js";
import { t } from "../../i18n/index.js";
import * as workflowRule from "./rules/obsolete-workflows.js";
import * as rootFileRule from "./rules/root-files.js";
import * as legacyDirRule from "./rules/legacy-dirs.js";

// 사유는 화면 언어로 번역(reasonKey), 키가 없으면 원문 그대로
const reasonOf = (e) => (e.reasonKey ? t(e.reasonKey) : e.reason);

const RULES = {
  workflow: workflowRule,
  "root-file": rootFileRule,
  "legacy-dir": legacyDirRule,
  "util-file": rootFileRule, // #500 — util 모듈 내 폐기 파일: 정확 경로 삭제 (root-file rule 재사용)
};

// 대상 레포에서 레거시 잔재 감지. 반환: { safe: [entry], confirm: [entry], ask: [entry] }
export function detectMigrations(targetRoot = ".") {
  const safe = [];
  const confirm = [];
  const ask = [];
  for (const entry of MIGRATIONS) {
    const rule = RULES[entry.category];
    if (!rule || !rule.detect(targetRoot, entry)) continue;
    if (entry.tier === "safe") safe.push(entry);
    else if (entry.tier === "ask") ask.push(entry);
    else confirm.push(entry);
  }
  return { safe, confirm, ask };
}

// 항목 일괄 적용 실행기 (safe·ask 티어 공용). 실패해도 나머지는 계속(부분 실패 허용 — 멱등이라 재실행으로 복구).
export function applySafeMigrations(targetRoot, entries) {
  const results = [];
  for (const entry of entries) {
    try {
      results.push({ id: entry.id, ...RULES[entry.category].apply(targetRoot, entry) });
    } catch (e) {
      results.push({ id: entry.id, action: "error", from: entry.file, error: e.message });
    }
  }
  return results;
}

// 마법사 배선 진입점.
//   askYesNo - async(msg, defaultYes)→bool. null이면 비대화형(--force): safe 자동 적용
//   log      - 한 줄 출력 함수 (기본 console.log)
// 반환: { applied: [결과], confirmPending: [entry], askPending: [entry] }
export async function runMigrations({ targetRoot = ".", askYesNo = null, log = console.log } = {}) {
  const { safe, confirm, ask } = detectMigrations(targetRoot);
  if (safe.length === 0 && confirm.length === 0 && ask.length === 0) {
    return { applied: [], confirmPending: [], askPending: [] };
  }

  let applied = [];
  if (safe.length > 0) {
    log(t("migrate.safe.found", { n: safe.length }));
    for (const e of safe) {
      const arrow = e.replacedBy ? ` → ${e.replacedBy}` : "";
      log(`   • ${e.file}${arrow}`);
      log(t("migrate.safe.reason", { reason: reasonOf(e), since: e.since }));
    }
    const yes = askYesNo
      ? await askYesNo(t("migrate.safe.ask", { n: safe.length }), true)
      : true;
    if (yes) {
      applied = applySafeMigrations(targetRoot, safe);
      const ok = applied.filter((r) => r.action !== "error");
      const failed = applied.filter((r) => r.action === "error");
      log(t("migrate.safe.done", { n: ok.length, failed: failed.length ? t("migrate.safe.failed", { n: failed.length }) : "" }));
      for (const f of failed) log(`   ⚠️ ${f.from}: ${f.error}`);
    } else {
      log(t("migrate.safe.skip"));
    }
  }

  // ask 티어 (#476) — 사용자 문서가 담긴 구명칭 폴더: 대화형은 확인 후 이동, 비대화형은 안내만
  let askPending = [];
  if (ask.length > 0) {
    log(t("migrate.dir.found", { n: ask.length }));
    for (const e of ask) {
      log(`   • ${e.file}/ → ${e.replacedBy}/`);
      log(`     (${reasonOf(e)})`);
    }
    if (askYesNo) {
      const yes = await askYesNo(t("migrate.dir.ask"), true);
      if (yes === true) {
        const results = applySafeMigrations(targetRoot, ask);
        applied = applied.concat(results);
        for (const r of results) {
          if (r.action === "error") log(`   ⚠️ ${r.from}: ${r.error}`);
          else log(t("migrate.dir.moved", { from: r.from, to: r.to, moved: r.moved ?? 0, kept: r.skipped ? t("migrate.dir.kept", { n: r.skipped }) : "" }));
        }
      } else {
        askPending = ask;
        log(t("migrate.dir.skip"));
      }
    } else {
      askPending = ask;
      log(t("migrate.dir.nonInteractive"));
    }
  }

  if (confirm.length > 0) {
    log(t("migrate.confirm.found", { n: confirm.length }));
    for (const e of confirm) {
      const arrow = e.replacedBy ? t("migrate.confirm.newer", { name: e.replacedBy }) : "";
      log(`   • ${e.file}${arrow}: ${reasonOf(e)}`);
    }
    log(t("migrate.confirm.hint"));
  }

  return { applied, confirmPending: confirm, askPending };
}
