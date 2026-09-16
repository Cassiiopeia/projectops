// run-trace(#494) — 이벤트 스키마·민감값 스크럽·미러·파일 기록.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRunTrace, scrubDetail, stampFromNow, MIGRATION_DIR } from "../src/core/run-trace.js";

test("event: ts/phase/action/target 스키마 + detail 보존", () => {
  const t = createRunTrace({ clockIso: "2026-07-14T00:00:00Z" });
  t.event("copy", "copied", "A.yaml", { group: "common" });
  assert.equal(t.events.length, 1);
  assert.deepEqual(t.events[0], { ts: "2026-07-14T00:00:00Z", phase: "copy", action: "copied", target: "A.yaml", detail: { group: "common" } });
});

test("scrubDetail: PAT/token/secret/password 키는 어떤 깊이에서도 제거", () => {
  const d = scrubDetail({ key: "K", github_pat: "ghp_x", nested: { API_TOKEN: "t", ok: 1 }, PASSWORD: "p", value: "v" });
  assert.deepEqual(d, { key: "K", nested: { ok: 1 }, value: "v" });
});

test("event: 민감키만 있던 detail은 통째로 생략", () => {
  const t = createRunTrace({ clockIso: "x" });
  t.event("a", "b", "c", { SECRET_VALUE: "s" });
  assert.equal("detail" in t.events[0], false);
});

test("stampFromNow: 표준 now → YYYYMMDD_HHMMSS, 비표준 → run 폴백", () => {
  assert.equal(stampFromNow("2026-07-14 00:16:04"), "20260714_001604");
  assert.equal(stampFromNow("n"), "run"); // 테스트 주입 clock 안전
  assert.equal(stampFromNow(""), "run");
});

test("write: JSONL 헤더+이벤트 기록, 이벤트 0건이면 null (no-op 오염 방지)", () => {
  const root = mkdtempSync(join(tmpdir(), "trace-"));
  try {
    const empty = createRunTrace();
    assert.equal(empty.write({ targetRoot: root, now: "2026-07-14 00:00:00" }), null);

    const t = createRunTrace({ clockIso: "2026-07-14T00:00:00Z" });
    t.event("copy", "copied", "A.yaml");
    const files = t.write({ targetRoot: root, fromVersion: "2.7.7", toVersion: "4.2.16", now: "2026-07-14 00:16:04" });
    assert.equal(files.traceFile, `${MIGRATION_DIR}/20260714_001604_v2.7.7_to_v4.2.16.jsonl`);
    const lines = readFileSync(join(root, files.traceFile), "utf8").trim().split("\n").map((l) => JSON.parse(l));
    assert.equal(lines[0].schema, 1);
    assert.equal(lines[0].kind, "projectops-migration-trace");
    assert.equal(lines[1].target, "A.yaml");
    // #561 — 이벤트는 사람이 읽는 로그 라인으로도 남는다. 터미널 미러를 안 켜도
    // .log가 생긴다(서버 로그처럼 내부 동작이 항상 기록되어야 사후 대응이 된다).
    assert.equal(files.logFile, `${MIGRATION_DIR}/20260714_001604_v2.7.7_to_v4.2.16.log`);
    const logBody = readFileSync(join(root, files.logFile), "utf8");
    assert.match(logBody, /INFO\s+copy\/copied\s+A\.yaml/);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("mirror: stdout/stderr 사본 수집 + write 시 .log 기록, stop 후 복원", () => {
  const root = mkdtempSync(join(tmpdir(), "trace-m-"));
  const so = process.stdout.write, se = process.stderr.write;
  try {
    const t = createRunTrace({ clockIso: "x" });
    t.mirrorStart();
    process.stderr.write("헬로 마법사\n");
    t.mirrorStop();
    assert.equal(process.stdout.write, so, "stdout 복원");
    assert.equal(process.stderr.write, se, "stderr 복원");
    assert.ok(t.lines.join("").includes("헬로 마법사"));
    t.event("copy", "copied", "A.yaml");
    const files = t.write({ targetRoot: root, fromVersion: "1.0.0", toVersion: "2.0.0", now: "2026-07-14 01:02:03" });
    assert.ok(existsSync(join(root, files.logFile)));
    assert.ok(readFileSync(join(root, files.logFile), "utf8").includes("헬로 마법사"));
  } finally {
    process.stdout.write = so; process.stderr.write = se; // 실패해도 복원 보장
    rmSync(root, { recursive: true, force: true });
  }
});
