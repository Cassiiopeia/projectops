// 자동 트리거 + 예시 값 감지 (#662) — doctor 가 "문제 없음"으로 통과시키던 경우
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { parseTriggerEvents, findPlaceholderValues, scanPlaceholderTriggers } from "../src/core/placeholder-triggers.js";
import { localChecks } from "../src/commands/doctor.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");

function workflowsDir(workflows) {
  const root = mkdtempSync(join(tmpdir(), "ph-trig-"));
  const dir = join(root, ".github", "workflows");
  mkdirSync(dir, { recursive: true });
  for (const [name, body] of Object.entries(workflows)) writeFileSync(join(dir, name), body, "utf8");
  return { root, dir };
}

const AUTO_WITH_EXAMPLE = `name: S
on:
  push:
    branches: ["main"]
  workflow_dispatch:
env:
  SMB_PATH_IOS: "/your-project/ios/download"
  FLUTTER_VERSION: "3.38.9"
jobs: {}
`;

test("트리거 파싱: 블록·인라인·배열 형식", () => {
  assert.deepEqual(parseTriggerEvents(AUTO_WITH_EXAMPLE), ["push", "workflow_dispatch"]);
  assert.deepEqual(parseTriggerEvents("on: push\njobs: {}\n"), ["push"]);
  assert.deepEqual(parseTriggerEvents("on: [push, workflow_dispatch]\n"), ["push", "workflow_dispatch"]);
  // 하위 키(branches, types)는 이벤트가 아니다
  assert.deepEqual(parseTriggerEvents("on:\n  issues:\n    types: [labeled]\n"), ["issues"]);
});

test("예시 값 판정: your-*, example.com, 미치환 토큰만 잡고 실값·주석·heredoc 구분자는 무시", () => {
  const body = [
    '  A: "/your-project/x"',
    '  B: "api.example.com"',
    '  C: "__DEPLOY_PORT__"',
    '  D: "3.38.9"',
    '  # E: "your-project"',
    '  F: "__SUH_FILE_CONTENT_EOF__"',
    '  G: "__REAL__"  # @wizard ask:example.com',
    "  H: ${{ secrets.SERVER_HOST }}",
  ].join("\n");
  assert.deepEqual(findPlaceholderValues(body).map((p) => p.key), ["A", "B", "C", "G"]);
});

test("수동 트리거만 있는 워크플로우는 예시 값이 있어도 보고하지 않는다", () => {
  const { dir } = workflowsDir({
    "MANUAL.yaml": 'on:\n  workflow_dispatch:\nenv:\n  A: "your-app-id"\n',
    "AUTO.yaml": AUTO_WITH_EXAMPLE,
    "CLEAN.yml": 'on:\n  push:\nenv:\n  A: "real"\n',
  });
  const found = scanPlaceholderTriggers(dir);
  assert.deepEqual(found.map((f) => f.file), ["AUTO.yaml"]);
  assert.deepEqual(found[0].triggers, ["push"]);
  assert.equal(found[0].values[0].key, "SMB_PATH_IOS");
});

test("doctor 가 자동 트리거 + 예시 값 워크플로우를 경고한다 (#662)", () => {
  const { root } = workflowsDir({ "SELF.yaml": AUTO_WITH_EXAMPLE });
  writeFileSync(join(root, "version.yml"), 'version: "1.0.0"\nproject_types: ["flutter"]\n', "utf8");
  const row = localChecks(root).find((r) => r.name === "Example values with automatic triggers");
  assert.equal(row.status, "WARN");
  const detail = row.detail.join("\n");
  assert.match(detail, /SELF\.yaml\s+\(push\)/);
  assert.match(detail, /SMB_PATH_IOS: "\/your-project\/ios\/download"/);
});

test("doctor: 해당 워크플로우가 없으면 OK", () => {
  const { root } = workflowsDir({ "CLEAN.yaml": 'on:\n  push:\nenv:\n  A: "real"\n' });
  writeFileSync(join(root, "version.yml"), 'version: "1.0.0"\nproject_types: ["node"]\n', "utf8");
  const row = localChecks(root).find((r) => r.name === "Example values with automatic triggers");
  assert.equal(row.status, "OK");
});

test("셀프호스트 템플릿에는 자동 트리거와 함께 남는 예시 값이 없다 (#662)", () => {
  const dir = join(ROOT, ".github/workflows/project-types/flutter");
  const text = readFileSync(join(dir, "PROJECT-FLUTTER-ANDROID-SELFHOSTED-CICD.yaml"), "utf8");
  // 마법사가 채우는 미치환 토큰(__X__)은 설치 시 치환되므로 예시 문구만 본다
  const examples = findPlaceholderValues(text).filter((p) => !/^__.*__$/.test(p.value));
  assert.deepEqual(examples, []);
});
