import { test } from "node:test";
import assert from "node:assert/strict";
import { classifyPackageText, classifyPackageJson, detectTypesFromMarkers, detectVersionFromFiles, suggestTypesByExtScan } from "../src/core/detect.js";

test("classifyPackageText (raw grep 등가)", () => {
  assert.equal(classifyPackageText('{"dependencies":{"react-native":"1","expo":"1"}}'), "react-native-expo");
  assert.equal(classifyPackageText('{"dependencies":{"react-native":"1"}}'), "react-native");
  assert.equal(classifyPackageText('{"dependencies":{"next":"1","react":"1"}}'), "react"); // next는 react로 흡수 (v4.1.0)
  assert.equal(classifyPackageText('{"dependencies":{"next":"1"}}'), "react"); // next 단독도 react
  assert.equal(classifyPackageText('{"dependencies":{"react":"1"}}'), "react");
  assert.equal(classifyPackageText('{"dependencies":{"express":"1"}}'), "node");
});

test("classifyPackageText: react-scripts triggers react via substring (matches .sh)", () => {
  // .sh grep '"react"' 는 "react-scripts" 안의 따옴표 있는 '"react"'만 매칭 —
  // scripts 값 "react-scripts start" 에는 따옴표+react+따옴표 조합이 없으므로 node.
  assert.equal(classifyPackageText('{"scripts":{"start":"react-scripts start"}}'), "node");
  // 하지만 dependencies에 "react" 키가 있으면 react.
  assert.equal(classifyPackageText('{"dependencies":{"react":"18"}}'), "react");
});

test("classifyPackageJson accepts object or raw string", () => {
  assert.equal(classifyPackageJson({ dependencies: { react: "1" } }), "react");
  assert.equal(classifyPackageJson('{"dependencies":{"react":"1"}}'), "react");
});

test("detectTypesFromMarkers suppresses node when other type present", () => {
  const has = (p) => ["build.gradle", "package.json"].includes(p);
  const read = () => '{"dependencies":{"express":"1"}}';
  assert.deepEqual(detectTypesFromMarkers({ has, read }), ["spring"]); // node 억제
});

test("detectTypesFromMarkers basic fallback", () => {
  assert.deepEqual(detectTypesFromMarkers({ has: () => false, read: () => null }), ["basic"]);
});

test("detectVersion order: gradle before pubspec", () => {
  const read = (p) => (p === "build.gradle" ? 'version = "1.2.3"' : p === "pubspec.yaml" ? "version: 9.9.9" : null);
  assert.equal(detectVersionFromFiles({ read, readJson: () => null, hasJq: false }), "1.2.3");
});

test("detectVersion fallback 0.0.1", () => {
  assert.equal(detectVersionFromFiles({ read: () => null, readJson: () => null, hasJq: false }), "0.0.1");
});

// ── 확장자 빈도 스캔 추천 (.sh suggest_types_by_scan 등가 — #458 npx 이식) ──
// 구 test_integrator_suggest.sh 케이스 (1)~(6)을 승계한다.

test("extScan: .py 4개 → python 추천", () => {
  assert.deepEqual(suggestTypesByExtScan(["m1.py", "m2.py", "m3.py", "m4.py"]), ["python"]);
});

test("extScan: .py 2개(임계 미만) → 추천 없음", () => {
  assert.deepEqual(suggestTypesByExtScan(["a.py", "b.py"]), []);
});

test("extScan: .dart 1개 → flutter 추천 (임계 1)", () => {
  assert.deepEqual(suggestTypesByExtScan(["main.dart"]), ["flutter"]);
});

test("extScan: .tsx 3개 → react 추천", () => {
  assert.deepEqual(suggestTypesByExtScan(["c1.tsx", "c2.tsx", "c3.tsx"]), ["react"]);
});

test("extScan: .js 3개(다른 타입 없음) → node fallback", () => {
  assert.deepEqual(suggestTypesByExtScan(["s1.js", "s2.js", "s3.js"]), ["node"]);
});

test("extScan: 다른 타입 있으면 node 미추천 + 메뉴 순서 정렬", () => {
  assert.deepEqual(
    suggestTypesByExtScan(["a.py", "b.py", "c.py", "x.js", "y.js", "z.js", "A.java", "B.kt", "b.gradle"]),
    ["spring", "python"],
  );
});

test("listScanFiles: node_modules 등 vendor 폴더 프루닝 (.sh 케이스 6 승계)", async () => {
  const { mkdtempSync, mkdirSync, writeFileSync, rmSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const { listScanFiles } = await import("../src/core/detect-fs.js");
  const tmp = mkdtempSync(join(tmpdir(), "scan-"));
  try {
    mkdirSync(join(tmp, "node_modules/pkg"), { recursive: true });
    for (const i of [1, 2, 3, 4]) writeFileSync(join(tmp, `node_modules/pkg/m${i}.py`), "x");
    writeFileSync(join(tmp, "app.py"), "x");
    const files = listScanFiles(tmp);
    assert.deepEqual(files, ["app.py"]); // vendor 안 .py는 목록에 없음 → 추천 임계 미달
    assert.deepEqual(suggestTypesByExtScan(files), []);
  } finally { rmSync(tmp, { recursive: true, force: true }); }
});

test("detectTypes: .github 의 스크립트(.py)만으로 python 오탐하지 않는다 (#671)", async () => {
  const { mkdtempSync, mkdirSync, writeFileSync, rmSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const { detectTypes } = await import("../src/core/detect-fs.js");
  const tmp = mkdtempSync(join(tmpdir(), "scan-gh-"));
  try {
    mkdirSync(join(tmp, ".github/scripts"), { recursive: true });
    for (const n of ["a", "b", "c"]) writeFileSync(join(tmp, `.github/scripts/${n}.py`), "x");
    assert.deepEqual(detectTypes(tmp), ["basic"]);
    // 실제 소스가 .github 밖에 있으면 여전히 추천된다
    for (const n of ["a", "b", "c"]) writeFileSync(join(tmp, `${n}.py`), "x");
    assert.deepEqual(detectTypes(tmp), ["python"]);
  } finally { rmSync(tmp, { recursive: true, force: true }); }
});
