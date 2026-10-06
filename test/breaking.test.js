import { test } from "node:test";
import assert from "node:assert/strict";
import { compareVersions, collectBreaking } from "../src/core/breaking.js";

test("compareVersions", () => {
  assert.equal(compareVersions("1.2.3", "1.2.3"), 0);
  assert.equal(compareVersions("v2.0.0", "1.9.9"), 1);
  assert.equal(compareVersions("1.2", "1.2.0"), 0);   // 누락 자리=0
  assert.equal(compareVersions("1.0.0", "1.0.1"), -1);
});

test("collectBreaking range + bug fix (target beyond 1.3.14)", () => {
  const json = {
    _meta: { severity: "critical" },
    "3.0.0": { severity: "critical", title: "x" },   // .sh 버그였다면 1.3.14 초과라 누락됨
    "1.2.0": { severity: "warning", title: "y" },     // current 이하 → 제외
  };
  const { critical, warnings } = collectBreaking(json, "2.9.9", "3.0.5");
  assert.equal(critical.length, 1);   // 3.0.0 잡힘 (버그 수정 효과)
  assert.equal(warnings.length, 0);
});

// ── runBreakingCheck 요약 리스트 표시 (#473) ──
import { runBreakingCheck } from "../src/core/breaking-check.js";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

function captureStderr(fn) {
  const orig = process.stderr.write;
  let out = "";
  process.stderr.write = (chunk) => { out += chunk; return true; };
  return Promise.resolve()
    .then(fn)
    .then((r) => { process.stderr.write = orig; return { out, r }; },
          (err) => { process.stderr.write = orig; throw err; });
}

const BC_JSON = {
  "9.0.0": { severity: "critical", title: "큰 변경", message: "아주 긴 조치 방법 본문입니다." },
  "9.1.0": { severity: "warning", title: "작은 변경", message: "경고 본문." },
};

function bcFixture() {
  const cwd = mkdtempSync(join(tmpdir(), "bc-"));
  writeFileSync(join(cwd, "version.yml"),
    'version: "1.0.0"\nmetadata:\n  template:\n    version: "1.0.0"\n');
  return cwd;
}

test("runBreakingCheck: 비대화형 — 제목 요약만 출력, 전문 미출력 + 참고 안내 (#473)", async () => {
  const cwd = bcFixture();
  try {
    const { out, r } = await captureStderr(() =>
      runBreakingCheck({ cwd, tempDir: cwd, templateVersion: "9.9.9", loader: async () => BC_JSON }));
    assert.equal(r, true);
    assert.match(out, /CRITICAL 1, WARNING 1/);
    assert.match(out, /\[CRITICAL\] 9\.0\.0 - 큰 변경/);
    assert.match(out, /\[WARNING\]\s+9\.1\.0 - 작은 변경/);
    assert.doesNotMatch(out, /아주 긴 조치 방법 본문/);   // 전문 통덤프 제거
    assert.doesNotMatch(out, /╔/);                        // 박스 경계 제거 (래핑 붕괴 방지)
    assert.match(out, /see \.github\/config\/breaking-changes\.json/);      // 상세 참조 안내
  } finally { rmSync(cwd, { recursive: true, force: true }); }
});

test("runBreakingCheck: 대화형 — 상세 보기 선택 시에만 전문 출력 (#473)", async () => {
  const cwd = bcFixture();
  try {
    // 1번째 질문(상세 보기)=yes, 2번째 질문(진행 확인)=yes
    const answers = [true, true];
    const { out, r } = await captureStderr(() =>
      runBreakingCheck({ cwd, tempDir: cwd, templateVersion: "9.9.9", loader: async () => BC_JSON,
        askYesNo: async () => answers.shift() }));
    assert.equal(r, true);
    assert.match(out, /아주 긴 조치 방법 본문/);            // 선택 시 전문 표시
  } finally { rmSync(cwd, { recursive: true, force: true }); }
});

test("runBreakingCheck: 대화형 — 상세 거절해도 CRITICAL 진행 게이트는 동작", async () => {
  const cwd = bcFixture();
  try {
    const answers = [false, false]; // 상세 안 봄, 진행 거부
    const { r } = await captureStderr(() =>
      runBreakingCheck({ cwd, tempDir: cwd, templateVersion: "9.9.9", loader: async () => BC_JSON,
        askYesNo: async () => answers.shift() }));
    assert.equal(r, false); // 진행 거부 → false
  } finally { rmSync(cwd, { recursive: true, force: true }); }
});
