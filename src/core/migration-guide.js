// 마이그레이션 가이드 (#493) — Layer 1 큐레이션 문서.
// 마법사(full/workflows) 실행이 끝나면 대상 레포의 docs/projectops/migration/PROJECTOPS-MIGRATION-GUIDE.md에
// "고정 헤더(최초 1회) + 실행 엔트리(append-only)"를 남긴다. 사람용 동적 체크리스트와
// AI Agent용 yaml 메타데이터를 한 엔트리에 담고, run-trace(#494)의 events를 단일 소스로 소비한다.
import { join } from "node:path";
import { existsSync, readFileSync, appendFileSync } from "node:fs";
import { writeText } from "./fsutil.js";
import { MIGRATION_DIR } from "./run-trace.js";

export const GUIDE_FILE = `${MIGRATION_DIR}/PROJECTOPS-MIGRATION-GUIDE.md`;
export const GUIDE_SCHEMA = 1;

// 고정 헤더 — 문서 목적 + AI Agent 해석 가이드라인. 최초 생성 시 1회만 쓴다 (엔트리와 분리).
const HEADER = `# ProjectOps 마이그레이션 가이드

이 문서는 projectops 마법사(\`npx projectops\`)가 **실행을 마칠 때마다 자동으로 기록**하는
마이그레이션 이력입니다. 실행 엔트리는 아래에 시간순으로 append되며, 기존 엔트리는 수정되지 않습니다.

## 사람이 읽는 법

- 각 엔트리의 **확인 체크리스트**가 그 실행 이후 사람이 마무리해야 하는 수동 작업입니다.
- 체크리스트는 실행에서 실제 발생한 것만 나옵니다. 항목이 없으면 할 일이 없다는 뜻입니다.
- 상세 실행 기록(파일별 결정과 치환 전후값)은 엔트리 메타의 \`trace_file\`(JSONL)과 \`log_file\`(터미널 원문)에 있습니다.

## AI Agent 해석 가이드라인

각 엔트리의 \`\`\`yaml 메타 블록(\`# projectops-migration\`)을 파싱해 아래 규칙으로 판단하고 조치한다.

| 필드 | 의미 | 권장 조치 |
|------|------|----------|
| \`workflows.leftover_old_gen\` | 구세대 워크플로우가 현역 가능성으로 보존됨 | 신형과 트리거 중복 여부 검사 → 전환 확인 후 구 파일 삭제 제안 |
| \`workflows.skipped_conflict\` | 사용자 수정본이 유지됨 (신형 미적용) | 사용자본과 신형 템플릿 diff → 병합 제안 |
| \`workflows.replaced_bak\` | .bak 백업 후 신형으로 교체됨 | .bak과 신형 비교 → 사용자 커스텀 유실분 복원 검토 후 .bak 정리 |
| \`env_applied\` | 워크플로우에 적용된 환경값 | 실제 워크플로우 env와 대조 → 드리프트 발견 시 경고 |
| \`breaking_traversed\` | 이 실행이 통과한 호환성 변경 (조치 방법 전문은 사람용 섹션) | \`action_required: true\` 항목의 조치 완료 여부 확인 |
| \`manual_actions_pending\` | 남은 수동 작업 코드 목록 | 비어 있지 않으면 사용자에게 상기 |
| \`trace_file\` | 파일별 결정과 치환 전후값 JSONL (Layer 2) | "왜 이 파일이 이렇게 됐나"는 파일명으로 grep |
| \`log_file\` | 터미널 출력 원문 (Layer 3) | 실행 재현, 포렌식 디버깅용 |

- 스키마는 \`schema\` 필드로 버저닝된다. 모르는 필드는 무시하고, 아는 필드만 사용한다.
- 여러 엔트리가 있으면 **가장 최근 엔트리**가 현재 상태의 기준이다. 과거 엔트리는 이력 참고용.
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
  L.push(`- 타입: ${(r.types ?? []).join(", ") || "-"} / 배포: ${r.options?.deploy ?? "-"} / publish: ${(r.options?.publish ?? []).join(",") || "없음"}`);
  L.push(`- 워크플로우: 신규/갱신 ${wf.added.length + wf.replacedBak.length}개, 유지(unchanged/충돌스킵) ${(r.counters?.skipped ?? 0)}개`);
  L.push("");

  // ── 확인 체크리스트 (동적 — 실제 발생분만) ──
  const checklist = [];
  if (leftoverOldGen.length) {
    checklist.push(`- [ ] **구세대 배포 워크플로우 ${leftoverOldGen.length}개 전환 후 삭제** (현역 배포일 수 있어 마법사가 건드리지 않았습니다):`);
    for (const o of leftoverOldGen) checklist.push(`  - \`${o.file}\`${o.replacement ? ` → 신형 \`${o.replacement}\`` : ""}`);
  }
  if (wf.replacedBak.length || legacyNeutralized.length) {
    checklist.push(`- [ ] **.bak 백업 파일 확인 후 정리** (커스텀 유실분이 없는지 신형과 비교하세요):`);
    for (const f of wf.replacedBak) checklist.push(`  - \`${f}.bak\` (충돌 교체 백업)`);
    for (const a of legacyNeutralized) if (a.to && String(a.to).endsWith(".bak")) checklist.push(`  - \`${a.to}\` (레거시 무해화)`);
  }
  if (wf.skippedConflict.length) {
    checklist.push(`- [ ] **기존 수정본 유지 ${wf.skippedConflict.length}개, 신형과 병합 검토**: ${wf.skippedConflict.map((f) => `\`${f}\``).join(", ")}`);
  }
  if (wf.added.length || wf.replacedBak.length) {
    checklist.push(`- [ ] **새/갱신 CICD가 요구하는 GitHub Secrets 등록 확인** (Settings → Secrets → Actions, \`_GITHUB_PAT_TOKEN\` 포함)`);
  }
  if (envByType.size) {
    checklist.push(`- [ ] **적용된 배포 환경값 검증** (실제 환경과 다르면 워크플로우 env를 직접 수정):`);
    for (const [t, kv] of envByType) {
      for (const [k, v] of kv) checklist.push(`  - ${t} \`${k}\` = \`${v}\``);
    }
  }
  if (r.branches?.created === true) {
    checklist.push(`- [x] 개발(릴리스 소스) 브랜치 \`${r.branches?.deployBranch ?? "develop"}\`: 마법사가 생성 및 확인 완료`);
  } else if (r.branches?.ready === false) {
    checklist.push(`- [ ] 개발(릴리스 소스) 브랜치 \`${r.branches?.deployBranch ?? "develop"}\` 생성 (릴리스 PR이 동작하려면 필요합니다)`);
  }
  if (checklist.length) {
    L.push("### 확인 체크리스트");
    L.push("");
    L.push(...checklist);
    L.push("");
  }

  // ── 버전 점프에서 통과한 호환성 변경 (조치 방법 전문 — 터미널에서 스킵해도 여기 남는다) ──
  if (breakingAll.length) {
    L.push(`### 통과한 호환성 변경 (v${breaking.current} → v${breaking.target})`);
    L.push("");
    for (const it of breakingAll) {
      const sev = (breaking.critical ?? []).includes(it) ? "CRITICAL" : "WARNING";
      L.push(`#### ${sev === "CRITICAL" ? "❗" : "⚠️"} [${sev}] ${it.version} - ${it.title || ""}`);
      if (it.message) L.push(`${it.message}`);
      L.push("");
    }
  }

  // ── AI 메타데이터 ──
  L.push("### AI 메타데이터");
  L.push("");
  L.push("```yaml");
  L.push("# projectops-migration (machine-readable)");
  L.push(`schema: ${GUIDE_SCHEMA}`);
  L.push(`run_at: ${yq(r.now || "")}`);
  L.push(`template: { from: ${yq(from)}, to: ${yq(to)} }`);
  L.push(`mode: ${r.mode || "full"}`);
  L.push(`types: ${ylist(r.types)}`);
  L.push(`options: { deploy: ${yq(r.options?.deploy ?? "")}, publish: ${ylist(r.options?.publish)}, secret_backup: ${r.options?.secretBackup === true}, coderabbit: ${r.options?.coderabbit === true}, changelog_provider: ${yq(r.options?.changelogProvider ?? "")}, intent: ${yq(r.options?.intent ?? "")}, semver_auto: ${r.options?.semverAuto === true} }`);
  L.push(`branches: { default: ${yq(r.branches?.defaultBranch ?? "main")}, deploy: ${yq(r.branches?.deployBranch ?? "develop")}, deploy_branch_created: ${r.branches?.created === true} }`);
  L.push("workflows:");
  L.push(`  added: ${ylist(wf.added)}`);
  L.push(`  replaced_bak: ${ylist(wf.replacedBak)}`);
  L.push(`  skipped_conflict: ${ylist(wf.skippedConflict)}`);
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
