import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  sha256, readBaseline, writeBaseline, isUserModified, detectRemoved, BASELINE_PATH,
} from "../src/core/baseline.js";

function tmp() { return mkdtempSync(join(tmpdir(), "baseline-")); }

// ── 기록·조회 ─────────────────────────────────────────────────────────
test("writeBaseline → readBaseline 왕복", () => {
  const root = tmp();
  writeBaseline(root, {
    templateVersion: "4.4.1", installedAt: "2026-09-16",
    entries: new Map([["A.yaml", { installed: sha256("x"), rendered: sha256("x") }]]),
  });
  const b = readBaseline(root);
  assert.equal(b.templateVersion, "4.4.1");
  assert.equal(b.files["A.yaml"].installed, sha256("x"));
});

test("readBaseline: 파일이 없으면 null (빈 객체가 아니다)", () => {
  // 빈 baseline은 '기록 없음'이 아니라 '전부 삭제됨'으로 오해될 수 있다.
  assert.equal(readBaseline(tmp()), null);
});

test("readBaseline: 손상된 JSON은 null — 업데이트를 막지 않는다", () => {
  const root = tmp();
  mkdirSync(join(root, ".github", ".projectops"), { recursive: true });
  writeFileSync(join(root, BASELINE_PATH), "{ broken", "utf8");
  assert.equal(readBaseline(root), null);
});

test("readBaseline: files가 없는 구조도 null", () => {
  const root = tmp();
  mkdirSync(join(root, ".github", ".projectops"), { recursive: true });
  writeFileSync(join(root, BASELINE_PATH), JSON.stringify({ templateVersion: "1" }), "utf8");
  assert.equal(readBaseline(root), null);
});

test("writeBaseline: 이전 기록을 병합한다 (이번에 안 건드린 파일의 기준점 보존)", () => {
  const root = tmp();
  const first = writeBaseline(root, {
    templateVersion: "1", installedAt: "", entries: new Map([
      ["A.yaml", { installed: sha256("a"), rendered: sha256("a") }],
      ["B.yaml", { installed: sha256("b"), rendered: sha256("b") }],
    ]),
  });
  writeBaseline(root, {
    templateVersion: "2", installedAt: "", previous: first,
    entries: new Map([["A.yaml", { installed: sha256("a2"), rendered: sha256("a2") }]]),
  });
  const b = readBaseline(root);
  assert.equal(b.files["A.yaml"].installed, sha256("a2"), "갱신된다");
  assert.equal(b.files["B.yaml"].installed, sha256("b"), "건드리지 않은 파일은 유지된다");
});

test("writeBaseline: installed 미지정이면 이전 값을 지킨다", () => {
  // 유지(skip)한 파일을 '우리가 썼다'고 기록하면 다음 업데이트에서 사용자 수정이 조용히 덮인다.
  const root = tmp();
  const first = writeBaseline(root, {
    templateVersion: "1", installedAt: "",
    entries: new Map([["A.yaml", { installed: sha256("orig"), rendered: sha256("orig") }]]),
  });
  writeBaseline(root, {
    templateVersion: "2", installedAt: "", previous: first,
    entries: new Map([["A.yaml", { rendered: sha256("new") }]]),   // installed 없음
  });
  const b = readBaseline(root);
  assert.equal(b.files["A.yaml"].installed, sha256("orig"));
  assert.equal(b.files["A.yaml"].rendered, sha256("new"));
});

// ── 판정 진리표 ───────────────────────────────────────────────────────
test("isUserModified: 설치 시점과 같으면 false (사용자가 손대지 않음)", () => {
  const b = { files: { "A.yaml": { installed: sha256("content"), rendered: sha256("content") } } };
  assert.equal(isUserModified(b, "A.yaml", "content"), false);
});

test("isUserModified: 내용이 다르면 true (사용자가 수정함)", () => {
  const b = { files: { "A.yaml": { installed: sha256("content"), rendered: sha256("content") } } };
  assert.equal(isUserModified(b, "A.yaml", "content + 내 수정"), true);
});

test("isUserModified: baseline이 없으면 null — '모른다'이지 '안 건드렸다'가 아니다", () => {
  // 호출부가 null을 false로 오해하면 사용자 수정을 말없이 덮어쓴다.
  assert.equal(isUserModified(null, "A.yaml", "x"), null);
});

test("isUserModified: 그 파일 기록이 없으면 null", () => {
  const b = { files: { "OTHER.yaml": { installed: sha256("x"), rendered: sha256("x") } } };
  assert.equal(isUserModified(b, "A.yaml", "x"), null);
});

test("isUserModified: installed가 null인 기록도 null (판정 근거 없음)", () => {
  const b = { files: { "A.yaml": { installed: null, rendered: sha256("x") } } };
  assert.equal(isUserModified(b, "A.yaml", "x"), null);
});

// ── 삭제 감지 ─────────────────────────────────────────────────────────
test("detectRemoved: 기준점에 있는데 디스크에 없으면 사용자가 지운 것", () => {
  const root = tmp();
  const wf = join(root, ".github", "workflows");
  mkdirSync(wf, { recursive: true });
  writeFileSync(join(wf, "A.yaml"), "x", "utf8");
  const b = { files: { "A.yaml": {}, "B.yaml": {} } };
  assert.deepEqual(detectRemoved(b, ["A.yaml", "B.yaml"], wf), ["B.yaml"]);
});

test("detectRemoved: 우리가 설치한 적 없는 파일은 판단하지 않는다", () => {
  const root = tmp();
  const wf = join(root, ".github", "workflows");
  mkdirSync(wf, { recursive: true });
  const b = { files: {} };
  assert.deepEqual(detectRemoved(b, ["NEVER.yaml"], wf), []);
});

test("detectRemoved: baseline이 없으면 빈 배열", () => {
  assert.deepEqual(detectRemoved(null, ["A.yaml"], tmp()), []);
});
