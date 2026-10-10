// 옵션 값을 정하는 곳이 한 곳이고, 대화형·비대화형이 같은 결과를 내는지 (#851).
//
// 예전에는 두 진입점이 같은 옵션을 각자 정했고, 그 사이 대화형이 PR 요약 선택을 버렸다
// (질문 결과를 받지 않아 null 이 복사 게이트에서 "꺼짐"이 됐다). 단위 테스트는 각 부품이
// 맞으니 통과했고, 두 경로를 끝까지 돌려 결과를 맞대는 테스트가 없어 오래 남았다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { run } from "../src/index.js";
import { runInteractive } from "../src/commands/interactive.js";
import { resolveOptions } from "../src/core/resolve-options.js";
import { parseExisting } from "../src/core/version-yml.js";
import { CANCEL } from "../src/ui/prompts.js";

const fresh = (p) => mkdtempSync(join(tmpdir(), p));
const write = (root, rel, content) => {
  mkdirSync(join(root, rel, ".."), { recursive: true });
  writeFileSync(join(root, rel), content);
};
const SUMMARY_WF = "PROJECT-COMMON-AI-PR-SUMMARY.yaml";
const CLOCK = { now: "2026-10-10 00:00:00", today: "2026-10-10" };

function makeTemplate() {
  const tpl = fresh("ro-tpl-");
  write(tpl, ".github/scripts/version_manager.sh", "#!/bin/bash\n");
  write(tpl, ".github/workflows/project-types/common/PROJECT-COMMON-CI.yaml", "name: ci\non:\n  push:\n");
  write(tpl, `.github/workflows/project-types/common/pr-summary/${SUMMARY_WF}`, "name: s\non:\n  push:\n");
  write(tpl, ".github/workflows/project-types/node/PROJECT-NODE-CI.yaml", "name: n\non:\n  push:\n");
  write(tpl, "version.yml", 'version: "4.7.0"\n');
  return tpl;
}

function makeTarget(files = {}) {
  const t = fresh("ro-tgt-");
  for (const [rel, body] of Object.entries(files)) write(t, rel, body);
  return t;
}

// 대화형 io 스텁 — 모든 질문에 기본값으로 답한다 (CI 에는 TTY 가 없어 질문은 폴백 경로를 탄다)
function stubIo(mode) {
  const noop = () => {};
  return {
    intro: noop, outro: noop, note: noop, cancelMessage: noop, log: noop,
    selectMode: async () => mode,
    confirmProjectMenu: async () => "continue",
    editMenu: async () => "done",
    selectTypes: async () => CANCEL,
    askText: async (_m, d) => d,
    askYesNo: async (_m, i) => i,
  };
}

async function quiet(fn) {
  const se = process.stderr.write; const so = console.log;
  process.stderr.write = () => true; console.log = () => {};
  try { return await fn(); } finally { process.stderr.write = se; console.log = so; }
}

const runCli = (argv, cwd, tpl) => quiet(() => run(argv, { cwd, source: { type: "local", path: tpl }, clock: CLOCK }));
const runWizard = (mode, cwd, tpl) => quiet(() => runInteractive({}, { cwd, source: { type: "local", path: tpl }, clock: CLOCK, io: stubIo(mode) }));
const optionsOf = (cwd) => parseExisting(readFileSync(join(cwd, "version.yml"), "utf8")).options;
const cleanup = (...dirs) => dirs.forEach((d) => rmSync(d, { recursive: true, force: true }));

test("우선순위: 플래그 > 저장값 > 기본값", () => {
  const existing = { options: { aiPrSummary: false, deploy: "vercel" }, templateMode: "full" };
  const a = resolveOptions({ flags: {}, existing, types: ["node"] }).values;
  assert.equal(a.aiPrSummary, false, "저장값이 기본값을 이긴다");
  assert.equal(a.deployTarget, "vercel");
  const b = resolveOptions({ flags: { aiPrSummary: true, deployTarget: "none" }, existing, types: ["node"] }).values;
  assert.equal(b.aiPrSummary, true, "플래그가 저장값을 이긴다");
  assert.equal(b.deployTarget, "none");
  const c = resolveOptions({ flags: {}, existing: null, types: ["node"] }).values;
  assert.equal(c.aiPrSummary, true, "아무 말 없으면 기본값");
  assert.equal(c.deployBranch, "", "개발 브랜치는 고르거나 플래그로 준 것만 기록한다");
});

test("모바일 단독 타입에 저장된 docker-ssh 는 질문 없이도 none 으로 정리된다", () => {
  const existing = { options: { deploy: "docker-ssh", publish: ["npm"] } };
  const { values, sources } = resolveOptions({ existing, types: ["flutter"] });
  assert.equal(values.deployTarget, "none");
  assert.deepEqual(values.publishTargets, []);
  assert.equal(values.intent, "none");
  assert.equal(sources.before.deploy, "docker-ssh", "trace 가 정리 전 값을 남길 수 있어야 한다");
});

test("대화형 full 도 PR 요약 워크플로를 설치하고 ai_summary 를 기록한다 (#851)", async () => {
  const tpl = makeTemplate();
  const tgt = makeTarget({ "package.json": '{"name":"app","version":"1.0.0"}\n' });
  try {
    assert.equal(await runWizard("full", tgt, tpl), 0);
    assert.ok(existsSync(join(tgt, ".github/workflows", SUMMARY_WF)), "고른(기본) PR 요약이 설치되지 않았다");
    assert.equal(optionsOf(tgt).aiPrSummary, true);
  } finally { cleanup(tpl, tgt); }
});

test("대화형 version 모드는 모바일 단독 레포에 docker-ssh 를 남기지 않는다 (#851)", async () => {
  const tpl = makeTemplate();
  const tgt = makeTarget({
    "pubspec.yaml": "name: app\nversion: 1.0.0+1\n",
    "version.yml": [
      'version: "1.0.0"', "version_code: 1", 'project_types: ["flutter"]', "metadata:", "  template:",
      '    mode: "version"', "    options:", '      deploy: "docker-ssh"', "",
    ].join("\n"),
  });
  try {
    assert.equal(await runWizard("version", tgt, tpl), 0);
    assert.equal(optionsOf(tgt).deploy, "none");
  } finally { cleanup(tpl, tgt); }
});

test("같은 레포에서 대화형과 비대화형이 같은 옵션을 기록한다 (#851)", async () => {
  const tpl = makeTemplate();
  const pkg = { "package.json": '{"name":"app","version":"1.0.0"}\n' };
  const a = makeTarget(pkg); const b = makeTarget(pkg);
  try {
    assert.equal(await runCli(["--mode", "full", "--type", "node", "--force"], a, tpl), 0);
    assert.equal(await runWizard("full", b, tpl), 0);
    const oa = optionsOf(a); const ob = optionsOf(b);
    for (const k of ["deploy", "publish", "intent", "secretBackup", "aiPrSummary", "codeReviewCoderabbit",
      "changelogProvider", "semverAuto", "closeOnRelease", "projectsSync", "language", "labelStyle", "deployBranch"]) {
      assert.deepEqual(ob[k], oa[k], `${k}: 대화형 ${JSON.stringify(ob[k])} / 비대화형 ${JSON.stringify(oa[k])}`);
    }
  } finally { cleanup(tpl, a, b); }
});
