import { test } from "node:test";
import assert from "node:assert/strict";
import { parseArgs, parsePathsCsv, normalizePath, CliError } from "../src/cli/args.js";

test("기본값", () => {
  const r = parseArgs([]);
  assert.equal(r.mode, "interactive");
  assert.equal(r.force, false);
  assert.equal(r.deployTarget, null);
  assert.equal(r.publishTargets, null);
  assert.deepEqual(r.types, []);
});

test("mode/project-version/force/type csv dedup", () => {
  const r = parseArgs(["--mode", "full", "--project-version", "1.2.3", "--force", "--type", "spring,react,spring"]);
  assert.equal(r.mode, "full");
  assert.equal(r.version, "1.2.3");
  assert.equal(r.force, true);
  assert.deepEqual(r.types, ["spring", "react"]); // dedup
  assert.equal(r.primaryType, "spring");
});

test("-v/--version 은 패키지 버전 출력 플래그 (초기버전 아님)", () => {
  assert.equal(parseArgs(["-v"]).showVersion, true);
  assert.equal(parseArgs(["--version"]).showVersion, true);
  // 초기 버전으로 오염되지 않아야 함
  assert.equal(parseArgs(["-v"]).version, "");
  // 기본값은 false
  assert.equal(parseArgs([]).showVersion, false);
});

test("무효 타입 throw", () => {
  assert.throws(() => parseArgs(["--type", "spring,bogus"]), CliError);
});

test("빈 타입 throw", () => {
  assert.throws(() => parseArgs(["--type", " , "]), CliError);
});

test("deploy/publish 축 플래그 (#439)", () => {
  assert.equal(parseArgs(["--deploy", "vercel"]).deployTarget, "vercel");
  assert.deepEqual(parseArgs(["--publish", "nexus,npm"]).publishTargets, ["nexus", "npm"]);
  assert.throws(() => parseArgs(["--deploy", "bogus"]), CliError);
  assert.throws(() => parseArgs(["--publish", "bogus"]), CliError);
  assert.equal(parseArgs(["--secret-backup"]).includeSecretBackup, true);
});

test("--intent 플래그 (#485)", () => {
  assert.equal(parseArgs(["--intent", "library"]).intent, "library");
  assert.equal(parseArgs(["--intent", "app"]).intent, "app");
  assert.equal(parseArgs(["--intent", "both"]).intent, "both");
  assert.equal(parseArgs(["--intent", "manual"]).intent, "manual");
  assert.equal(parseArgs([]).intent, null); // 미지정 → null(역추론)
  assert.throws(() => parseArgs(["--intent", "bogus"]), CliError);
});

test("deprecated alias — --nexus/--npm-publish는 신 축으로 해석 (#439)", () => {
  const r1 = parseArgs(["--nexus"]);
  assert.deepEqual(r1.publishTargets, ["nexus"]);
  assert.equal(r1.deployTarget, "none"); // 구 동작: nexus면 서버 배포 제외
  const r2 = parseArgs(["--npm-publish"]);
  assert.deepEqual(r2.publishTargets, ["npm"]);
  assert.equal(r2.deployTarget, null);
  const r3 = parseArgs(["--nexus", "--no-nexus"]);
  assert.deepEqual(r3.publishTargets, []);
});

test("알 수 없는 옵션 throw", () => {
  assert.throws(() => parseArgs(["--no-backup"]), CliError); // 도움말 전용 허구 → exit 1
  assert.throws(() => parseArgs(["--bogus"]), CliError);
});

test("help 플래그", () => {
  assert.equal(parseArgs(["-h"]).help, true);
  assert.equal(parseArgs(["--help"]).help, true);
});

test("normalizePath 정규화", () => {
  assert.equal(normalizePath("  app/  "), "app");
  assert.equal(normalizePath("./client"), "client");
  assert.equal(normalizePath("a\\b\\"), "a/b");
  assert.equal(normalizePath(""), ".");
  assert.equal(normalizePath("."), ".");
});

test("parsePathsCsv → Map, 무효 타입 throw", () => {
  const m = parsePathsCsv("flutter=app,react=./client");
  assert.equal(m.get("flutter"), "app");
  assert.equal(m.get("react"), "client");
  assert.throws(() => parsePathsCsv("bogus=x"), CliError);
});

test("--mode 허용 값 외에는 CliError (#665)", () => {
  for (const m of ["full", "version", "workflows", "issues", "skills", "doctor", "interactive"]) {
    assert.equal(parseArgs(["--mode", m]).mode, m);
  }
  assert.throws(() => parseArgs(["--mode", "nope"]), CliError);
  assert.throws(() => parseArgs(["-m", "ful"]), CliError);
  assert.throws(() => parseArgs(["--mode"]), CliError);   // 값 누락
});
