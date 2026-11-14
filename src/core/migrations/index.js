// Legacy migration entry point (#470) — signal-based and idempotent.
// Detect (registry × rules) → show plan → confirm safe tier once → apply → notice for the confirm tier.
// Version numbers are not trusted: half of legacy repos have no template metadata in version.yml (measured).
import { MIGRATIONS } from "./registry.js";
import { t } from "../../i18n/index.js";
import * as workflowRule from "./rules/obsolete-workflows.js";
import * as rootFileRule from "./rules/root-files.js";
import * as legacyDirRule from "./rules/legacy-dirs.js";

// Reasons are translated to the screen language (reasonKey); without a key, the original text as is
const reasonOf = (e) => (e.reasonKey ? t(e.reasonKey) : e.reason);

const RULES = {
  workflow: workflowRule,
  "root-file": rootFileRule,
  "legacy-dir": legacyDirRule,
  "util-file": rootFileRule, // #500 — obsolete files inside util modules: exact-path delete (reuses the root-file rule)
};

// Detect legacy leftovers in the target repo. Returns { safe: [entry], confirm: [entry], ask: [entry] }
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

// Batch apply runner for entries (shared by the safe and ask tiers). Continues on failure (partial failure allowed — idempotent, so a re-run recovers).
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

// Wizard wiring entry point.
//   askYesNo - async(msg, defaultYes)→bool. null means non-interactive (--force): safe applied automatically
//   log      - one-line output function (default console.log)
//   removeLegacy - when true, also neutralize the confirm tier (old-generation deploy workflows) as .bak (--remove-legacy, #809)
// Returns { applied: [results], confirmPending: [entry], askPending: [entry] }
// Settings moved from obsolete workflows > lines for the screen and run log (lets the user confirm settings moved, #1060)
export function describeCarriedSettings(results) {
  const lines = [];
  for (const result of results) {
    if (result.carried?.length) lines.push(t("migrate.safe.carried", { file: result.from, keys: result.carried.join(", ") }));
    if (result.carryFailed) lines.push(t("migrate.safe.carryFailed", { file: result.from, error: result.carryFailed }));
  }
  return lines;
}

export async function runMigrations({ targetRoot = ".", askYesNo = null, log = console.log, removeLegacy = false } = {}) {
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
      for (const line of describeCarriedSettings(ok)) log(line);
    } else {
      log(t("migrate.safe.skip"));
    }
  }

  // ask tier (#476) — old-name folders holding user documents: interactive moves after confirmation, non-interactive only notifies
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
    // When old and new generations run together, they react twice to the same event (#809 — two PREVIEWs on every PR close).
    // It may be the live deploy, so it is left alone by default, but moved aside as .bak (restorable) with the explicit flag or interactive confirmation.
    const yes = removeLegacy
      ? true
      : askYesNo ? await askYesNo(t("migrate.confirm.ask", { n: confirm.length }), false) : false;
    if (yes === true) {
      const results = applySafeMigrations(targetRoot, confirm);
      applied = applied.concat(results);
      const failed = results.filter((r) => r.action === "error");
      log(t("migrate.confirm.done", { n: results.length - failed.length }));
      for (const f of failed) log(`   ⚠️ ${f.from}: ${f.error}`);
      const failedIds = new Set(failed.map((f) => f.id));
      return { applied, confirmPending: confirm.filter((e) => failedIds.has(e.id)), askPending };
    }
    log(t(askYesNo ? "migrate.confirm.hint" : "migrate.confirm.hintForce"));
  }

  return { applied, confirmPending: confirm, askPending };
}
