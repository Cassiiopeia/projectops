// migration-guide(#493) — 헤더/append·동적 체크리스트·breaking 임베드·yaml 메타.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { renderGuideEntry, appendGuideEntry, deriveWorkflowLists, deriveEnvApplied, GUIDE_FILE } from "../src/core/migration-guide.js";

const EV = [
  { ts: "t", phase: "copy", action: "copied", target: "PROJECT-COMMON-CI.yaml", detail: { group: "common" } },
  { ts: "t", phase: "copy", action: "replaced-bak", target: "PROJECT-SPRING-SIMPLE-CICD.yaml", detail: { decision: "backup" } },
  { ts: "t", phase: "copy", action: "skipped-conflict", target: "PROJECT-SPRING-PR-PREVIEW.yaml", detail: {} },
  { ts: "t", phase: "env", action: "substituted", target: "PROJECT-SPRING-SIMPLE-CICD.yaml", detail: { type: "spring", key: "JAVA_VERSION", before: "21", after: "17" } },
];

function baseReport(extra = {}) {
  return {
    now: "2026-07-14 00:16:04", mode: "full", types: ["spring"], repoName: "my-repo",
    templateFrom: "2.7.7", templateTo: "4.2.16",
    options: { deploy: "docker-ssh", publish: [], secretBackup: true, coderabbit: true, changelogProvider: "coderabbit", intent: "app" },
    branches: { defaultBranch: "main", deployBranch: "develop", ready: true, created: true },
    breaking: null, migrations: null, orphans: null,
    events: EV, counters: { skipped: 3 },
    traceFile: ".github/.projectops/logs/x.jsonl", logFile: "",
    ...extra,
  };
}

test("deriveWorkflowLists/deriveEnvApplied: 이벤트에서 목록 파생", () => {
  const wf = deriveWorkflowLists(EV);
  assert.deepEqual(wf.added, ["PROJECT-COMMON-CI.yaml"]);
  assert.deepEqual(wf.replacedBak, ["PROJECT-SPRING-SIMPLE-CICD.yaml"]);
  assert.deepEqual(wf.skippedConflict, ["PROJECT-SPRING-PR-PREVIEW.yaml"]);
  const env = deriveEnvApplied(EV);
  assert.equal(env.get("spring").get("JAVA_VERSION"), "17");
});

test("renderGuideEntry: 동적 체크리스트 — 발생한 항목만 출력", () => {
  const md = renderGuideEntry(baseReport());
  assert.match(md, /v2\.7\.7 → v4\.2\.16 \(full\)/);
  assert.match(md, /\.bak 백업 파일 확인 후 정리/);           // replaced-bak 있음
  assert.match(md, /신형과 병합 검토/);                        // skipped-conflict 있음
  assert.match(md, /`JAVA_VERSION` = `17`/);                  // env 검증 항목
  assert.match(md, /- \[x\] 개발\(릴리스 소스\) 브랜치 `develop`: 마법사가 생성 및 확인 완료/);
  assert.doesNotMatch(md, /구세대 배포 워크플로우/);           // leftover 없음 → 항목 자체가 없음
  assert.doesNotMatch(md, /통과한 호환성 변경/);               // breaking 없음 → 섹션 없음
});

test("renderGuideEntry: breaking 임베드 — 조치 방법 전문 + 메타 action_required", () => {
  const md = renderGuideEntry(baseReport({
    breaking: {
      current: "2.7.7", target: "4.2.16",
      critical: [{ version: "3.0.186", title: "브랜치 전략 전면 전환", message: "deploy 브랜치를 폐기하고 develop/main 구조로 전환하세요." }],
      warnings: [{ version: "4.2.0", title: "배포/publish 축 재설계", message: "구 옵션은 deprecated." }],
    },
  }));
  assert.match(md, /### 통과한 호환성 변경 \(v2\.7\.7 → v4\.2\.16\)/);
  assert.match(md, /❗ \[CRITICAL\] 3\.0\.186 - 브랜치 전략 전면 전환/);
  assert.match(md, /deploy 브랜치를 폐기하고 develop\/main 구조로 전환하세요\./); // 전문 임베드
  assert.match(md, /\{ version: "3\.0\.186", severity: critical, title: "브랜치 전략 전면 전환", action_required: true \}/);
  assert.match(md, /\{ version: "4\.2\.0", severity: warning, .* action_required: false \}/);
});

test("renderGuideEntry: leftover_old_gen — 체크리스트 + 메타 + manual_actions_pending", () => {
  const md = renderGuideEntry(baseReport({
    migrations: {
      applied: [{ id: "x", action: "bak", from: "OLD.yaml", to: "OLD.yaml.bak" }],
      confirmPending: [{ file: "PROJECT-SPRING-SYNOLOGY-PR-PREVIEW.yaml", replacedBy: "PROJECT-SPRING-PR-PREVIEW.yaml", reason: "SYNOLOGY 폐기" }],
      askPending: [],
    },
  }));
  assert.match(md, /구세대 배포 워크플로우 1개 전환 후 삭제/);
  assert.match(md, /PROJECT-SPRING-SYNOLOGY-PR-PREVIEW\.yaml/);
  assert.match(md, /legacy_neutralized:/);
  assert.match(md, /leftover_old_gen:/);
  assert.match(md, /manual_actions_pending: \["delete-old-gen-workflows", "review-bak-files", "merge-skipped-conflicts", "register-secrets"\]/);
});

test("renderGuideEntry: yaml 메타 필수 필드", () => {
  const md = renderGuideEntry(baseReport());
  assert.match(md, /# projectops-migration \(machine-readable\)/);
  assert.match(md, /schema: 1/);
  assert.match(md, /template: \{ from: "2\.7\.7", to: "4\.2\.16" \}/);
  assert.match(md, /deploy_branch_created: true/);
  assert.match(md, /trace_file: ".github\/.projectops\/logs\/x\.jsonl"/);
});

test("appendGuideEntry: 최초 생성=헤더 포함, 재실행=append-only (기존 엔트리 불변)", () => {
  const root = mkdtempSync(join(tmpdir(), "guide-"));
  try {
    const r1 = appendGuideEntry(root, baseReport());
    assert.equal(r1.created, true);
    assert.equal(r1.guidePath, GUIDE_FILE);
    const first = readFileSync(join(root, GUIDE_FILE), "utf8");
    assert.match(first, /# ProjectOps 마이그레이션 가이드/);      // 고정 헤더
    assert.match(first, /AI Agent 해석 가이드라인/);

    const r2 = appendGuideEntry(root, baseReport({ now: "2026-07-15 09:00:00", templateFrom: "4.2.16", templateTo: "4.3.0" }));
    assert.equal(r2.created, false);
    const second = readFileSync(join(root, GUIDE_FILE), "utf8");
    assert.ok(second.startsWith(first.trimEnd().slice(0, 200)), "기존 내용 앞부분 불변");
    assert.match(second, /v2\.7\.7 → v4\.2\.16/);                 // 1번째 엔트리 보존
    assert.match(second, /v4\.2\.16 → v4\.3\.0/);                 // 2번째 엔트리 추가
    assert.equal((second.match(/# ProjectOps 마이그레이션 가이드/g) || []).length, 1, "헤더는 1회만");
  } finally { rmSync(root, { recursive: true, force: true }); }
});
