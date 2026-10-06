// 마이그레이션 가이드 (#493) — Layer 1 큐레이션 문서.
// 마법사(full/workflows) 실행이 끝나면 대상 레포의 .github/.projectops/logs/PROJECTOPS-MIGRATION-GUIDE.md에
// "고정 헤더(최초 1회) + 실행 엔트리(append-only)"를 남긴다. 사람용 동적 체크리스트와
// AI Agent용 yaml 메타데이터를 한 엔트리에 담고, run-trace(#494)의 events를 단일 소스로 소비한다.
import { join } from "node:path";
import { existsSync, readFileSync, appendFileSync } from "node:fs";
import { writeText } from "./fsutil.js";
import { MIGRATION_DIR } from "./run-trace.js";

export const GUIDE_FILE = `${MIGRATION_DIR}/PROJECTOPS-MIGRATION-GUIDE.md`;
export const GUIDE_SCHEMA = 1;

// 고정 헤더 — 문서 목적 + AI Agent 해석 가이드라인. 최초 생성 시 1회만 쓴다 (엔트리와 분리).
const HEADER = `# ProjectOps Migration Guide

This document is **written automatically every time a run finishes** by the projectops wizard (\`npx projectops\`).
Run entries are appended below in chronological order, and existing entries are never modified.

## How humans read it

- The **checklist** in each entry lists the manual work a person still has to finish after that run.
- The checklist only contains things that actually happened in the run. No items means nothing to do.
- Detailed run records (per-file decisions and before/after values) are in the entry metadata: \`trace_file\` (JSONL) and \`log_file\` (raw terminal output).

## Guidelines for AI agents

Parse the \`\`\`yaml metadata block (\`# projectops-migration\`) of each entry and decide and act with the rules below.

| Field | Meaning | Recommended action |
|-------|---------|--------------------|
| \`workflows.leftover_old_gen\` | Old-generation workflows kept because they may be live | Check for trigger overlap with the new ones, then suggest deleting the old file once the switch is confirmed |
| \`workflows.skipped_conflict\` | The user's modified file was kept (new template not applied) | Diff the user's file against the new template and suggest a merge |
| \`workflows.replaced_bak\` | Replaced by the new one after a .bak backup | Compare .bak with the new file, review any lost customizations, then clean up the .bak |
| \`env_applied\` | Environment values applied to workflows | Compare with the real workflow env and warn on drift |
| \`breaking_traversed\` | Breaking changes this run passed through (full action steps are in the human section) | Check that items with \`action_required: true\` were handled |
| \`manual_actions_pending\` | Codes of the remaining manual work | If not empty, remind the user |
| \`trace_file\` | JSONL of per-file decisions and before/after values (Layer 2) | To learn why a file ended up this way, grep by file name |
| \`log_file\` | Raw terminal output (Layer 3) | For reproducing the run and forensic debugging |

- The schema is versioned by the \`schema\` field. Ignore unknown fields and use only the ones you know.
- When there are several entries, the **latest entry** is the reference for the current state. Older entries are history.
`;

// ── yaml 렌더 헬퍼 (외부 의존성 없이 수동 직렬화 — version-yml.js와 동일 원칙) ──
const yq = (s) => `"${String(s ?? "").replaceAll('"', '\\"')}"`;
const ylist = (arr) => (arr && arr.length ? `[${arr.map(yq).join(", ")}]` : "[]");

// trace events → 가이드용 파일 목록 파생 (단일 소스 — 이벤트에서 유도).
export function deriveWorkflowLists(events = []) {
  const pick = (action) => events.filter((e) => e.phase === "copy" && e.action === action).map((e) => e.target);
  return {
    added: pick("copied"),
    replacedBak: pick("replaced-bak"),
    skippedConflict: pick("skipped-conflict"),
    // #654 — 건너뛴 파일별 새 템플릿 사본 경로와 diff 줄 수 (이벤트 detail에서 파생)
    skippedConflictDetails: events.filter((e) => e.phase === "copy" && e.action === "skipped-conflict")
      .map((e) => ({ file: e.target, incoming: e.detail?.incoming ?? "", added: e.detail?.added ?? null, removed: e.detail?.removed ?? null })),
    templateAdded: pick("template-added"),
    excluded: pick("excluded"),
  };
}

// trace events → 타입별 적용 env 값 파생.
export function deriveEnvApplied(events = []) {
  const byType = new Map();
  for (const e of events) {
    if (e.phase !== "env" || e.action !== "substituted") continue;
    const t = e.detail?.type ?? "";
    if (!byType.has(t)) byType.set(t, new Map());
    byType.get(t).set(e.detail?.key ?? "", e.detail?.after ?? "");
  }
  return byType;
}

// 실행 엔트리 렌더링. report:
//   { now, mode, types, repoName, templateFrom, templateTo,
//     options: {deploy, publish, secretBackup, coderabbit, changelogProvider, intent},
//     branches: {defaultBranch, deployBranch, ready, created},
//     breaking: {current, target, critical:[], warnings:[]} | null,
//     migrations: {applied:[], confirmPending:[], askPending:[]} | null,
//     orphans: {cleaned:[], pending:[]} | null,
//     events: [], counters: {}, traceFile, logFile }
export function renderGuideEntry(report) {
  const r = report ?? {};
  const from = r.templateFrom || "new";
  const to = r.templateTo || "unknown";
  const wf = deriveWorkflowLists(r.events);
  const envByType = deriveEnvApplied(r.events);
  const breaking = r.breaking ?? null;
  const breakingAll = breaking ? [...(breaking.critical ?? []), ...(breaking.warnings ?? [])] : [];
  const mig = r.migrations ?? null;
  const leftoverOldGen = (mig?.confirmPending ?? []).map((e) => ({ file: e.file, replacement: e.replacedBy || "", reason: e.reason || "" }));
  const legacyNeutralized = (mig?.applied ?? []).filter((a) => a.action !== "error");
  const orphanCleaned = (r.orphans?.cleaned ?? []);

  const L = [];
  L.push("---");
  L.push("");
  L.push(`## ${r.now || ""} - v${from} → v${to} (${r.mode || "full"})`);
  L.push("");
  L.push(`- Types: ${(r.types ?? []).join(", ") || "-"} / deploy: ${r.options?.deploy ?? "-"} / publish: ${(r.options?.publish ?? []).join(",") || "none"}`);
  L.push(`- Workflows: ${wf.added.length + wf.replacedBak.length} new/updated, ${(r.counters?.skipped ?? 0)} kept (unchanged or skipped on conflict)`);
  L.push("");

  // ── 확인 체크리스트 (동적 — 실제 발생분만) ──
  const checklist = [];
  if (leftoverOldGen.length) {
    checklist.push(`- [ ] **Switch to the new workflow, then delete ${leftoverOldGen.length} old-generation deploy workflow(s)** (they may be live deployments, so the wizard left them alone):`);
    for (const o of leftoverOldGen) checklist.push(`  - \`${o.file}\`${o.replacement ? ` → new \`${o.replacement}\`` : ""}`);
  }
  if (wf.replacedBak.length || legacyNeutralized.length) {
    checklist.push(`- [ ] **Review the .bak backup files, then clean them up** (compare with the new file to be sure no customization was lost):`);
    for (const f of wf.replacedBak) checklist.push(`  - \`${f}.bak\` (backup from conflict replacement)`);
    for (const a of legacyNeutralized) if (a.to && String(a.to).endsWith(".bak")) checklist.push(`  - \`${a.to}\` (legacy neutralized)`);
  }
  if (wf.skippedConflict.length) {
    checklist.push(`- [ ] **Kept ${wf.skippedConflict.length} modified file(s), review a merge with the new template**: ${wf.skippedConflict.map((f) => `\`${f}\``).join(", ")}`);
    // #654 — 새 템플릿 사본이 있으면 비교 방법까지 적는다
    for (const d of wf.skippedConflictDetails.filter((x) => x.incoming)) {
      const cnt = d.added != null && d.removed != null ? ` (+${d.added} / -${d.removed} lines)` : "";
      checklist.push(`  - \`${d.file}\`${cnt}: \`diff -u .github/workflows/${d.file} ${d.incoming}\``);
    }
  }
  if (wf.added.length || wf.replacedBak.length) {
    checklist.push(`- [ ] **Check that the GitHub Secrets required by the new/updated CICD are registered** (Settings → Secrets → Actions, including \`_GITHUB_PAT_TOKEN\`)`);
  }
  if (envByType.size) {
    checklist.push(`- [ ] **Verify the applied deploy environment values** (edit the workflow env directly if they differ from your real environment):`);
    for (const [t, kv] of envByType) {
      for (const [k, v] of kv) checklist.push(`  - ${t} \`${k}\` = \`${v}\``);
    }
  }
  if (r.branches?.created === true) {
    checklist.push(`- [x] Development (release source) branch \`${r.branches?.deployBranch ?? "develop"}\`: created and verified by the wizard`);
  } else if (r.branches?.ready === false) {
    checklist.push(`- [ ] Create the development (release source) branch \`${r.branches?.deployBranch ?? "develop"}\` (required for the release PR to work)`);
  }
  if (checklist.length) {
    L.push("### Checklist");
    L.push("");
    L.push(...checklist);
    L.push("");
  }

  // ── 버전 점프에서 통과한 호환성 변경 (조치 방법 전문 — 터미널에서 스킵해도 여기 남는다) ──
  if (breakingAll.length) {
    L.push(`### Breaking changes passed through (v${breaking.current} → v${breaking.target})`);
    L.push("");
    for (const it of breakingAll) {
      const sev = (breaking.critical ?? []).includes(it) ? "CRITICAL" : "WARNING";
      L.push(`#### ${sev === "CRITICAL" ? "❗" : "⚠️"} [${sev}] ${it.version} - ${it.title || ""}`);
      if (it.message) L.push(`${it.message}`);
      L.push("");
    }
  }

  // ── AI 메타데이터 ──
  L.push("### AI metadata");
  L.push("");
  L.push("```yaml");
  L.push("# projectops-migration (machine-readable)");
  L.push(`schema: ${GUIDE_SCHEMA}`);
  L.push(`run_at: ${yq(r.now || "")}`);
  L.push(`template: { from: ${yq(from)}, to: ${yq(to)} }`);
  L.push(`mode: ${r.mode || "full"}`);
  L.push(`types: ${ylist(r.types)}`);
  L.push(`options: { deploy: ${yq(r.options?.deploy ?? "")}, publish: ${ylist(r.options?.publish)}, secret_backup: ${r.options?.secretBackup === true}, coderabbit: ${r.options?.coderabbit === true}, changelog_provider: ${yq(r.options?.changelogProvider ?? "")}, intent: ${yq(r.options?.intent ?? "")}, semver_auto: ${r.options?.semverAuto === true}, language: ${yq(r.options?.language ?? "")}, label_style: ${yq(r.options?.labelStyle ?? "")}, close_on_release: ${r.options?.closeOnRelease === true}, app_release: ${r.options?.appRelease === true} }`);
  L.push(`branches: { default: ${yq(r.branches?.defaultBranch ?? "main")}, deploy: ${yq(r.branches?.deployBranch ?? "develop")}, deploy_branch_created: ${r.branches?.created === true} }`);
  L.push("workflows:");
  L.push(`  added: ${ylist(wf.added)}`);
  L.push(`  replaced_bak: ${ylist(wf.replacedBak)}`);
  L.push(`  skipped_conflict: ${ylist(wf.skippedConflict)}`);
  const inc = wf.skippedConflictDetails.filter((d) => d.incoming);
  if (inc.length) {
    L.push("  skipped_conflict_incoming:");
    for (const d of inc) L.push(`    - { file: ${yq(d.file)}, incoming: ${yq(d.incoming)}, added: ${d.added ?? "null"}, removed: ${d.removed ?? "null"} }`);
  }
  L.push(`  template_added: ${ylist(wf.templateAdded)}`);
  if (legacyNeutralized.length) {
    L.push("  legacy_neutralized:");
    for (const a of legacyNeutralized) L.push(`    - { file: ${yq(a.from ?? a.id ?? "")}, to: ${yq(a.to ?? "")}, action: ${yq(a.action ?? "")} }`);
  } else {
    L.push("  legacy_neutralized: []");
  }
  if (leftoverOldGen.length) {
    L.push("  leftover_old_gen:");
    for (const o of leftoverOldGen) L.push(`    - { file: ${yq(o.file)}, replacement: ${yq(o.replacement)} }`);
  } else {
    L.push("  leftover_old_gen: []");
  }
  if (orphanCleaned.length) L.push(`  orphan_neutralized: ${ylist(orphanCleaned)}`);
  if (envByType.size) {
    L.push("env_applied:");
    for (const [t, kv] of envByType) {
      L.push(`  ${t}:`);
      for (const [k, v] of kv) L.push(`    ${k}: ${yq(v)}`);
    }
  } else {
    L.push("env_applied: {}");
  }
  if (breakingAll.length) {
    L.push("breaking_traversed:");
    for (const it of breakingAll) {
      const sev = (breaking.critical ?? []).includes(it) ? "critical" : "warning";
      L.push(`  - { version: ${yq(it.version)}, severity: ${sev}, title: ${yq(it.title ?? "")}, action_required: ${sev === "critical"} }`);
    }
  } else {
    L.push("breaking_traversed: []");
  }
  const pending = [];
  if (leftoverOldGen.length) pending.push("delete-old-gen-workflows");
  if (wf.replacedBak.length || legacyNeutralized.some((a) => a.to && String(a.to).endsWith(".bak"))) pending.push("review-bak-files");
  if (wf.skippedConflict.length) pending.push("merge-skipped-conflicts");
  if (wf.added.length || wf.replacedBak.length) pending.push("register-secrets");
  if (r.branches?.ready === false) pending.push("create-deploy-branch");
  L.push(`manual_actions_pending: ${ylist(pending)}`);
  L.push(`trace_file: ${yq(r.traceFile ?? "")}`);
  L.push(`log_file: ${yq(r.logFile ?? "")}`);
  L.push("```");
  L.push("");
  return L.join("\n");
}

// 가이드 파일에 엔트리 append (파일 없으면 헤더부터 생성). 반환: { guidePath, created }.
export function appendGuideEntry(targetRoot, report) {
  const guidePath = join(targetRoot, GUIDE_FILE);
  const entry = renderGuideEntry(report);
  const created = !existsSync(guidePath);
  if (created) {
    writeText(guidePath, HEADER + "\n" + entry);
  } else {
    // append-only — 기존 엔트리 불변 (이력 보존 계약)
    const prev = readFileSync(guidePath, "utf8");
    appendFileSync(guidePath, (prev.endsWith("\n") ? "" : "\n") + entry);
  }
  return { guidePath: GUIDE_FILE, created };
}
