import { test } from "node:test";
import assert from "node:assert/strict";
import { detectTypes, detectVersion, detectDefaultBranch, detectRepoName } from "../src/core/detect-fs.js";
import { writeText } from "../src/core/fsutil.js";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

function fresh() { return mkdtempSync(join(tmpdir(), "detfs-")); }

test("detectTypes: 마커 스캔 (react)", () => {
  const d = fresh();
  try {
    writeText(join(d, "package.json"), '{"dependencies":{"react":"18"}}');
    assert.deepEqual(detectTypes(d), ["react"]);
  } finally { rmSync(d, { recursive: true, force: true }); }
});

test("detectTypes: version.yml 우선 (source of truth)", () => {
  const d = fresh();
  try {
    // 마커는 react인데 version.yml엔 spring → version.yml 우선
    writeText(join(d, "package.json"), '{"dependencies":{"react":"18"}}');
    writeText(join(d, "version.yml"), 'version: "1.0.0"\nproject_types: ["spring"]\n');
    assert.deepEqual(detectTypes(d), ["spring"]);
  } finally { rmSync(d, { recursive: true, force: true }); }
});

test("detectTypes: 아무것도 없으면 basic", () => {
  const d = fresh();
  try {
    assert.deepEqual(detectTypes(d), ["basic"]);
  } finally { rmSync(d, { recursive: true, force: true }); }
});

test("detectVersion: build.gradle", () => {
  const d = fresh();
  try {
    writeText(join(d, "build.gradle"), 'version = "2.3.4"');
    assert.equal(detectVersion(d, { hasJq: false }), "2.3.4");
  } finally { rmSync(d, { recursive: true, force: true }); }
});

test("detectVersion: 없으면 0.0.1", () => {
  const d = fresh();
  try {
    assert.equal(detectVersion(d, { hasJq: false }), "0.0.1");
  } finally { rmSync(d, { recursive: true, force: true }); }
});

test("detectDefaultBranch: git 없으면 main 폴백", () => {
  const d = fresh();
  try {
    assert.equal(detectDefaultBranch(d), "main");
  } finally { rmSync(d, { recursive: true, force: true }); }
});

test("detectRepoName: git 없으면 폴더명", () => {
  const d = fresh();
  try {
    assert.equal(detectRepoName(d), join(d).split(/[/\\]/).pop());
  } finally { rmSync(d, { recursive: true, force: true }); }
});

test("detectTypes: 마커 없이 구버전 단수 project_type 만 있으면 그 타입으로 복원 (#718)", () => {
  const d = fresh();
  try {
    writeText(join(d, "version.yml"), 'version: "1.0.0"\nproject_type: "spring"\n');
    assert.deepEqual(detectTypes(d), ["spring"]);
    // next 는 4.1.0 에서 react 로 흡수됐다
    writeText(join(d, "version.yml"), 'version: "1.0.0"\nproject_type: next\n');
    assert.deepEqual(detectTypes(d), ["react"]);
    // 배열 키가 있으면 단수 키는 무시한다
    writeText(join(d, "version.yml"), 'version: "1.0.0"\nproject_type: "spring"\nproject_types: ["python"]\n');
    assert.deepEqual(detectTypes(d), ["python"]);
  } finally { rmSync(d, { recursive: true, force: true }); }
});
