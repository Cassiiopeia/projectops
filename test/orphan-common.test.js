// 선택형 공통 워크플로우를 껐을 때 남는 파일 감지 (#567)
//
// 실사고: common/ 아래 조건부 폴더(secret-backup·deploy/<target>·pr-summary)는
// 켜면 복사되지만 끄면 아무 일도 없었다. 이미 설치된 파일이 그대로 남아 계속 실행됐고,
// 사용자에게는 "껐는데 왜 도나"가 됐다. 고아 감지가 common/을 순회에서 빼고 있었다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, mkdirSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { detectOrphanWorkflows, applyOrphanCleanup } from "../src/core/orphan-workflows.js";

const fresh = (p) => mkdtempSync(join(tmpdir(), p));

const SECRET = "PROJECT-COMMON-SECRET-FILE-UPLOAD.yaml";
const SUMMARY = "PROJECT-COMMON-AI-PR-SUMMARY.yaml";
const VERCEL = "PROJECT-COMMON-VERCEL-DEPLOY.yaml";

function setup({ installed = [SECRET, SUMMARY, VERCEL] } = {}) {
  const tpl = fresh("orc-tpl-"); const tgt = fresh("orc-tgt-");
  const common = join(tpl, ".github/workflows/project-types/common");
  for (const d of ["secret-backup", "pr-summary", "deploy/vercel", "deploy/docker-ssh"]) {
    mkdirSync(join(common, d), { recursive: true });
  }
  writeFileSync(join(common, "secret-backup", SECRET), "name: b\non:\n  push:\n");
  writeFileSync(join(common, "pr-summary", SUMMARY), "name: s\non:\n  push:\n");
  writeFileSync(join(common, "deploy/vercel", VERCEL), "name: v\non:\n  push:\n");
  // 타입 폴더도 하나 둔다 — 기존 타입 고아 감지가 계속 동작하는지 확인용
  mkdirSync(join(tpl, ".github/workflows/project-types/flutter"), { recursive: true });
  writeFileSync(join(tpl, ".github/workflows/project-types/flutter/PROJECT-FLUTTER-CI.yaml"), "name: f\n");

  const wf = join(tgt, ".github/workflows");
  mkdirSync(wf, { recursive: true });
  for (const f of installed) writeFileSync(join(wf, f), "name: installed\n");
  return { tpl, tgt, wf };
}

const names = (orphans) => orphans.map((o) => o.filename).sort();

test("전부 끄면 세 워크플로우가 모두 고아로 잡힌다", () => {
  const { tpl, tgt } = setup();
  try {
    const orphans = detectOrphanWorkflows({
      tempDir: tpl, targetRoot: tgt, selectedTypes: [],
      options: { includeSecretBackup: false, aiPrSummary: false, deployTarget: "none" },
    });
    assert.deepEqual(names(orphans), [SUMMARY, SECRET, VERCEL].sort());
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("켜져 있으면 대상이 아니다", () => {
  const { tpl, tgt } = setup();
  try {
    const orphans = detectOrphanWorkflows({
      tempDir: tpl, targetRoot: tgt, selectedTypes: [],
      options: { includeSecretBackup: true, aiPrSummary: true, deployTarget: "vercel" },
    });
    assert.deepEqual(names(orphans), [], "쓰고 있는 파일을 지우려 들면 안 된다");
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("deploy는 선택한 타겟만 살리고 나머지를 잡는다", () => {
  const { tpl, tgt } = setup();
  try {
    const orphans = detectOrphanWorkflows({
      tempDir: tpl, targetRoot: tgt, selectedTypes: [],
      options: { includeSecretBackup: true, aiPrSummary: true, deployTarget: "docker-ssh" },
    });
    assert.deepEqual(names(orphans), [VERCEL], "docker-ssh를 골랐으면 vercel 파일이 고아");
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("축마다 독립적으로 판정한다", () => {
  const { tpl, tgt } = setup();
  try {
    const orphans = detectOrphanWorkflows({
      tempDir: tpl, targetRoot: tgt, selectedTypes: [],
      options: { includeSecretBackup: false, aiPrSummary: true, deployTarget: "vercel" },
    });
    assert.deepEqual(names(orphans), [SECRET], "끈 축만 잡혀야 한다");
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("설치되지 않은 파일은 잡지 않는다", () => {
  const { tpl, tgt } = setup({ installed: [] });
  try {
    const orphans = detectOrphanWorkflows({
      tempDir: tpl, targetRoot: tgt, selectedTypes: [],
      options: { includeSecretBackup: false, aiPrSummary: false, deployTarget: "none" },
    });
    assert.deepEqual(names(orphans), [], "실재하지 않는 파일을 고아라고 하면 안 된다");
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("options를 주지 않으면 종전 동작 그대로 (구 호출부 하위호환)", () => {
  const { tpl, tgt } = setup();
  try {
    const orphans = detectOrphanWorkflows({ tempDir: tpl, targetRoot: tgt, selectedTypes: [] });
    assert.deepEqual(names(orphans), [], "common은 검사 대상이 아니었다");
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("타입 고아 감지는 그대로 동작한다 (#487 회귀 방지)", () => {
  const { tpl, tgt, wf } = setup({ installed: [] });
  try {
    writeFileSync(join(wf, "PROJECT-FLUTTER-CI.yaml"), "name: installed\n");
    const orphans = detectOrphanWorkflows({
      tempDir: tpl, targetRoot: tgt, selectedTypes: ["node"],
      options: { includeSecretBackup: true, aiPrSummary: true, deployTarget: "vercel" },
    });
    assert.deepEqual(names(orphans), ["PROJECT-FLUTTER-CI.yaml"]);
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("정리하면 .bak으로 무해화된다", () => {
  const { tpl, tgt, wf } = setup();
  try {
    const orphans = detectOrphanWorkflows({
      tempDir: tpl, targetRoot: tgt, selectedTypes: [],
      options: { includeSecretBackup: false, aiPrSummary: false, deployTarget: "none" },
    });
    const results = applyOrphanCleanup(tgt, orphans);
    assert.equal(results.filter((r) => r.action === "bak").length, 3);
    for (const f of [SECRET, SUMMARY, VERCEL]) {
      assert.ok(!existsSync(join(wf, f)), `${f}는 치워져야 한다`);
      assert.ok(existsSync(join(wf, `${f}.bak`)), `${f}.bak으로 남아야 복구할 수 있다`);
    }
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});
