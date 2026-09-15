import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, mkdirSync, writeFileSync, existsSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import {
  parseTemplateOptions, askAllOptionalWorkflows,
  applicableTargets, TYPE_DEPLOY_TARGETS, TYPE_PUBLISH_TARGETS,
} from "../src/core/options-ask.js";
import { parseExisting, buildVersionYml } from "../src/core/version-yml.js";
import { VALID_TYPES } from "../src/context.js";

function touch(root, rel, content = "") {
  const p = join(root, rel);
  mkdirSync(dirname(p), { recursive: true });
  writeFileSync(p, content);
}
function makeTmp() { return mkdtempSync(join(tmpdir(), "optask-")); }

// #455에서 추가된 changelog/code_review 필드의 기본값(미기재 → null).
// #546 semverAuto도 동일하게 미기재 → null (호출부가 "기존 통합 레포"로 해석해 OFF 처리).
// 기존 deepEqual 기대값에 spread해 필드 추가로 인한 회귀를 막는다.
const CL_NULL = { changelogProvider: null, changelogBaseUrl: null, codeReviewCoderabbit: null, deployBranch: null, intent: null, semverAuto: null };

// 실제 temp 레이아웃({tempDir}/.github/workflows/project-types)으로 픽스처 구성
function makeTemplateFixture({ secretBackup = true } = {}) {
  const dir = makeTmp();
  const pt = ".github/workflows/project-types";
  touch(dir, `${pt}/common/PROJECT-COMMON-CI.yaml`);
  if (secretBackup) touch(dir, `${pt}/common/secret-backup/PROJECT-COMMON-SECRET-FILE-UPLOAD.yaml`);
  return dir;
}

// version.yml — 신 축(deploy/publish) 형식
const VY_NEW = (deploy, publish, secret) => `version: "1.0.0"
project_types: ["spring"]
metadata:
  last_updated: "2026-07-08"
  template:
    source: "projectops"
    version: "4.2.0"
    options:
      deploy: "${deploy}"
      publish: [${publish.map((t) => `"${t}"`).join(",")}]
      secret_backup: ${secret}
`;

// version.yml — 구 축(nexus/npm_publish) 형식 (v4.2.0 이전 — 마이그레이션 확인용)
const VY_LEGACY = (nexus, secret) => `version: "1.0.0"
project_types: ["spring"]
metadata:
  last_updated: "2026-07-08"
  template:
    source: "projectops"
    version: "3.0.0"
    options:
      nexus: ${nexus}
      secret_backup: ${secret}
`;

// version.yml — changelog/code_review 옵션 포함 (#455)
const VY_CHANGELOG = (provider, baseUrl, coderabbit) => `version: "1.0.0"
project_types: ["basic"]
metadata:
  last_updated: "2026-07-09"
  template:
    source: "projectops"
    version: "4.3.0"
    options:
      deploy: "none"
      publish: []
      secret_backup: false
      code_review:
        coderabbit: ${coderabbit}
      changelog:
        provider: "${provider}"
        base_url: "${baseUrl}"
`;

// io 스텁 — confirm(Secret/CodeRabbit) + select(deploy/changelog) + multiselect(publish) + text(ollama base_url) 응답 시퀀스
function stubIo({ confirms = [], selects = [], multiselects = [], texts = [] } = {}) {
  const calls = { confirm: [], select: [], multiselect: [], text: [], logs: [] };
  return {
    calls,
    log: (m) => calls.logs.push(m),
    confirm: async (a) => { calls.confirm.push(a.message); return confirms.shift(); },
    select: async (a) => { calls.select.push(a.message); return selects.shift(); },
    multiselect: async (a) => { calls.multiselect.push(a.message); return multiselects.shift(); },
    text: async (a) => { calls.text.push(a.message); return texts.shift(); },
  };
}

test("parseTemplateOptions: 신 축 deploy/publish 파싱", () => {
  assert.deepEqual(parseTemplateOptions(VY_NEW("vercel", ["npm", "nexus"], false)),
    { deploy: "vercel", publish: ["npm", "nexus"], secretBackup: false, ...CL_NULL });
  assert.deepEqual(parseTemplateOptions(VY_NEW("docker-ssh", [], true)),
    { deploy: "docker-ssh", publish: [], secretBackup: true, ...CL_NULL });
  assert.deepEqual(parseTemplateOptions('version: "1.0.0"\nproject_types: ["spring"]\n'),
    { deploy: null, publish: null, secretBackup: null, ...CL_NULL }); // options 블록 없음 → null
});

test("parseTemplateOptions: 구 키 자동 마이그레이션 (nexus:true → publish:[nexus] + deploy:none)", () => {
  assert.deepEqual(parseTemplateOptions(VY_LEGACY("true", "false")),
    { deploy: "none", publish: ["nexus"], secretBackup: false, ...CL_NULL });
  assert.deepEqual(parseTemplateOptions(VY_LEGACY("false", "true")),
    { deploy: null, publish: [], secretBackup: true, ...CL_NULL }); // nexus:false → publish 빈배열, deploy 미변경
});

test("parseTemplateOptions: 신 publish 키가 있으면 구 키 마이그레이션 안 함", () => {
  const y = VY_NEW("vercel", ["npm"], false) + "      nexus: true\n";
  const r = parseTemplateOptions(y);
  assert.equal(r.deploy, "vercel");
  assert.deepEqual(r.publish, ["npm"]); // 신 publish 우선 — 구 nexus 무시
});

test("parseTemplateOptions: changelog/code_review 파싱 (#455)", () => {
  const r = parseTemplateOptions(VY_CHANGELOG("github-ai", "", "true"));
  assert.equal(r.changelogProvider, "github-ai");
  assert.equal(r.changelogBaseUrl, "");
  assert.equal(r.codeReviewCoderabbit, true);

  const r2 = parseTemplateOptions(VY_CHANGELOG("ollama", "https://ai.suhsaechan.kr/v1", "false"));
  assert.equal(r2.changelogProvider, "ollama");
  assert.equal(r2.changelogBaseUrl, "https://ai.suhsaechan.kr/v1");
  assert.equal(r2.codeReviewCoderabbit, false);

  // 필드 없으면 null (기존 형식 하위호환)
  const r3 = parseTemplateOptions(VY_NEW("vercel", ["npm"], false));
  assert.equal(r3.changelogProvider, null);
  assert.equal(r3.changelogBaseUrl, null);
  assert.equal(r3.codeReviewCoderabbit, null);
});

test("buildVersionYml: changelog/code_review 블록 생성 + round-trip (#455)", () => {
  const yml = buildVersionYml({
    version: "1.0.0", types: ["basic"], branch: "main", versionCode: 1,
    now: "2026-07-09 00:00:00", today: "2026-07-09",
    templateOptions: {
      templateVersion: "4.3.0", deployTarget: "none", publishTargets: [], includeSecretBackup: false,
      changelogProvider: "github-ai", changelogBaseUrl: "", codeReviewCoderabbit: true,
    },
  });
  assert.match(yml, /changelog:/);
  assert.match(yml, /provider: "github-ai"/);
  assert.match(yml, /coderabbit: true/);
  // round-trip: 생성 → 파싱 동일
  const parsed = parseTemplateOptions(yml);
  assert.equal(parsed.changelogProvider, "github-ai");
  assert.equal(parsed.codeReviewCoderabbit, true);
  assert.equal(parsed.changelogBaseUrl, "");
});

test("buildVersionYml: ollama base_url round-trip (#455)", () => {
  const yml = buildVersionYml({
    version: "1.0.0", types: ["basic"], branch: "main", versionCode: 1,
    now: "2026-07-09 00:00:00", today: "2026-07-09",
    templateOptions: {
      templateVersion: "4.3.0", deployTarget: "none", publishTargets: [], includeSecretBackup: false,
      changelogProvider: "ollama", changelogBaseUrl: "https://ai.suhsaechan.kr/v1", codeReviewCoderabbit: false,
    },
  });
  const parsed = parseTemplateOptions(yml);
  assert.equal(parsed.changelogProvider, "ollama");
  assert.equal(parsed.changelogBaseUrl, "https://ai.suhsaechan.kr/v1");
  assert.equal(parsed.codeReviewCoderabbit, false);
});

test("parseTemplateOptions: template 섹션 밖의 nexus 키는 무시", () => {
  const y = 'nexus: true\nmetadata:\n  foo: "bar"\n';
  assert.deepEqual(parseTemplateOptions(y), { deploy: null, publish: null, secretBackup: null, ...CL_NULL });
});

test("parseExisting: options 필드 포함 반환 (신 축)", () => {
  const r = parseExisting(VY_NEW("vercel", ["npm"], false));
  assert.deepEqual(r.options, { deploy: "vercel", publish: ["npm"], secretBackup: false, ...CL_NULL });
  assert.equal(r.version, "1.0.0");
});

test("askAllOptionalWorkflows: changelog provider + coderabbit 질문 (#455)", async () => {
  const tempDir = makeTemplateFixture({ secretBackup: false });
  const target = makeTmp();
  try {
    // basic 단독이라 deploy/publish select 스킵 → select는 changelog provider 하나만
    // confirm: code_review coderabbit / text: deploy_branch(#456)
    const io = stubIo({ confirms: [true], selects: ["github-ai"], texts: ["develop"] });
    const r = await askAllOptionalWorkflows({
      tempDir, types: ["basic"], targetRoot: target, tty: true, io,
    });
    assert.equal(r.codeReviewCoderabbit, true);
    assert.equal(r.changelogProvider, "github-ai");
    assert.equal(r.changelogBaseUrl, "");
    assert.equal(r.deployBranch, "develop");
    assert.equal(io.calls.text.length, 1, "github-ai면 base_url 질문은 없고 deploy_branch만 1회");
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

test("parseTemplateOptions: deploy_branch(metadata 직속) 파싱 (#456)", () => {
  const yml = 'version: "1.0.0"\nmetadata:\n  default_branch: "main"\n  deploy_branch: "release"\n';
  assert.equal(parseTemplateOptions(yml).deployBranch, "release");
  const noBranch = 'version: "1.0.0"\nmetadata:\n  default_branch: "main"\n';
  assert.equal(parseTemplateOptions(noBranch).deployBranch, null);
});

test("askAllOptionalWorkflows: deploy_branch 기본값 develop (#456)", async () => {
  const tempDir = makeTemplateFixture({ secretBackup: false });
  const target = makeTmp();
  try {
    // deploy_branch 질문에 빈 응답이면 기본 develop 유지
    const io = stubIo({ confirms: [false], selects: ["github-ai"], texts: [""] });
    const r = await askAllOptionalWorkflows({
      tempDir, types: ["basic"], targetRoot: target, tty: true, io,
    });
    assert.equal(r.deployBranch, "develop");
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

test("askAllOptionalWorkflows: changelog=ollama면 base_url 질문 (#455)", async () => {
  const tempDir = makeTemplateFixture({ secretBackup: false });
  const target = makeTmp();
  try {
    // text 순서: base_url(ollama) → deploy_branch(#456)
    const io = stubIo({ confirms: [false], selects: ["ollama"], texts: ["https://ai.suhsaechan.kr/v1", "release"] });
    const r = await askAllOptionalWorkflows({
      tempDir, types: ["basic"], targetRoot: target, tty: true, io,
    });
    assert.equal(r.changelogProvider, "ollama");
    assert.equal(r.changelogBaseUrl, "https://ai.suhsaechan.kr/v1");
    assert.equal(r.deployBranch, "release");
    assert.equal(io.calls.text.length, 2, "ollama면 base_url + deploy_branch 2회");
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

test("askAllOptionalWorkflows: 대화형 — intent=both → deploy=vercel / publish=[npm] / secret=아니오", async () => {
  const tempDir = makeTemplateFixture();
  const target = makeTmp();
  try {
    // select 순서: intent(both) → deploy(vercel) → changelog(github-ai). confirm: code_review(false) → secret(false)
    const io = stubIo({ selects: ["both", "vercel", "github-ai"], multiselects: [["npm"]], confirms: [false, false] });
    const r = await askAllOptionalWorkflows({
      tempDir, types: ["spring"], targetRoot: target, tty: true, io,
    });
    assert.equal(r.deploy, "vercel");
    assert.deepEqual(r.publish, ["npm"]);
    assert.equal(r.intent, "both");
    assert.equal(r.secretBackup, false);
    assert.equal(r.changelogProvider, "github-ai");
    assert.equal(io.calls.select.length, 3, "intent + deploy + changelog");
    assert.equal(io.calls.multiselect.length, 1);
    assert.equal(io.calls.confirm.length, 2, "code_review + secret");
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

test("askAllOptionalWorkflows: intent=app → deploy만 물음, publish 스킵([])", async () => {
  const tempDir = makeTemplateFixture();
  const target = makeTmp();
  try {
    // select: intent(app) → deploy(docker-ssh) → changelog(github-ai). multiselect 없음(publish 스킵)
    const io = stubIo({ selects: ["app", "docker-ssh", "github-ai"], confirms: [false, false] });
    const r = await askAllOptionalWorkflows({ tempDir, types: ["spring"], targetRoot: target, tty: true, io });
    assert.equal(r.intent, "app");
    assert.equal(r.deploy, "docker-ssh");
    assert.deepEqual(r.publish, [], "publish 안 물어 빈 배열");
    assert.equal(io.calls.multiselect.length, 0, "publish 질문 안 함");
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

test("askAllOptionalWorkflows: intent=library → publish만 물음, deploy=none 자동", async () => {
  const tempDir = makeTemplateFixture();
  const target = makeTmp();
  try {
    // select: intent(library) → changelog(github-ai). deploy select 없음. multiselect: publish
    const io = stubIo({ selects: ["library", "github-ai"], multiselects: [["nexus"]], confirms: [false, false] });
    const r = await askAllOptionalWorkflows({ tempDir, types: ["spring"], targetRoot: target, tty: true, io });
    assert.equal(r.intent, "library");
    assert.equal(r.deploy, "none", "deploy 안 물어 none");
    assert.deepEqual(r.publish, ["nexus"]);
    assert.equal(io.calls.select.length, 2, "intent + changelog (deploy 스킵)");
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

test("askAllOptionalWorkflows: intent=none → deploy/publish 둘 다 스킵, none·[]", async () => {
  const tempDir = makeTemplateFixture();
  const target = makeTmp();
  try {
    const io = stubIo({ selects: ["none", "github-ai"], confirms: [false, false] });
    const r = await askAllOptionalWorkflows({ tempDir, types: ["spring"], targetRoot: target, tty: true, io });
    assert.equal(r.intent, "none");
    assert.equal(r.deploy, "none");
    assert.deepEqual(r.publish, []);
    assert.equal(io.calls.multiselect.length, 0);
    assert.equal(io.calls.select.length, 2, "intent + changelog만");
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

test("askAllOptionalWorkflows: basic 단독 타입은 배포/publish 질문 스킵 → none·[] (UX 개선)", async () => {
  const tempDir = makeTemplateFixture({ secretBackup: false }); // Secret 폴더 없음 → 질문 0
  const target = makeTmp();
  try {
    // deploy select은 스킵돼야 함. 단 changelog select는 물어봄(github-ai). code_review confirm(false).
    const io = stubIo({ selects: ["github-ai"], confirms: [false], multiselects: [["npm"]] });
    const r = await askAllOptionalWorkflows({
      tempDir, types: ["basic"], targetRoot: target, tty: true, io,
    });
    assert.equal(r.deploy, "none");
    assert.deepEqual(r.publish, []);
    assert.equal(r.secretBackup, false);
    assert.equal(io.calls.multiselect.length, 0, "publish 질문 안 함");
    // select은 changelog 하나만(배포 스킵), multiselect의 npm은 소비 안 됨
    assert.equal(io.calls.select.length, 1, "배포 스킵, changelog만");
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

test("askAllOptionalWorkflows: basic이어도 Secret 백업 폴더가 있으면 그 질문은 유지", async () => {
  const tempDir = makeTemplateFixture({ secretBackup: true });
  const target = makeTmp();
  try {
    // confirm 순서: code_review(false) → secret(false). select: changelog(github-ai)
    const io = stubIo({ confirms: [false, false], selects: ["github-ai"] });
    const r = await askAllOptionalWorkflows({
      tempDir, types: ["basic"], targetRoot: target, tty: true, io,
    });
    assert.equal(r.deploy, "none");
    assert.deepEqual(r.publish, []);
    assert.equal(r.secretBackup, false);
    assert.equal(io.calls.multiselect.length, 0);
    assert.equal(io.calls.confirm.length, 2, "code_review + Secret 백업");
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

test("askAllOptionalWorkflows: 비대화형 — current 유지, 미설정은 기본값", async () => {
  const tempDir = makeTemplateFixture();
  const target = makeTmp();
  try {
    const io = stubIo(); // 호출 자체가 없어야 함
    const r = await askAllOptionalWorkflows({
      tempDir, types: ["spring"], current: { deploy: "vercel", publish: null, secretBackup: null },
      targetRoot: target, force: true, tty: false, io,
    });
    assert.deepEqual(r, { deploy: "vercel", publish: [], secretBackup: false,
      codeReviewCoderabbit: false, changelogProvider: "github-ai", changelogBaseUrl: "", deployBranch: "develop",
      deployBranchReady: null, // #490 — 비대화형은 브랜치 확인 안 함
      deployBranchCreated: null, // #493 — 비대화형은 생성 안 함
      intent: "app" }); // deploy≠none & publish=[] → app 역추론 (#485)
    assert.equal(io.calls.select.length, 0);
    assert.equal(io.calls.multiselect.length, 0);
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

test("askAllOptionalWorkflows: version.yml 저장값 있으면 재질문 생략", async () => {
  const tempDir = makeTemplateFixture();
  const target = makeTmp();
  try {
    touch(target, "version.yml", VY_NEW("vercel", ["nexus"], false));
    // deploy/publish/secret은 저장값 유지 → 질문 없음. changelog는 저장값에 없어 질문 나옴.
    // deploy multiselect가 호출되면 반대값이지만, 저장값 유지로 select은 changelog만.
    const io = stubIo({ selects: ["github-ai"], confirms: [false] });
    const r = await askAllOptionalWorkflows({
      tempDir, types: ["spring"], targetRoot: target, tty: true, io,
    });
    assert.equal(r.deploy, "vercel");
    assert.deepEqual(r.publish, ["nexus"]);
    assert.equal(r.secretBackup, false);
    assert.equal(r.changelogProvider, "github-ai");
    assert.equal(io.calls.select.length, 1, "deploy 저장값 유지, changelog만 질문");
    assert.equal(io.calls.multiselect.length, 0);
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

test("askAllOptionalWorkflows: 구 키 저장 파일 → 신 축으로 마이그레이션해 읽음", async () => {
  const tempDir = makeTemplateFixture({ secretBackup: false });
  const target = makeTmp();
  try {
    touch(target, "version.yml", VY_LEGACY("true", "false"));
    // deploy/publish는 구 키 마이그레이션으로 채워짐 → 질문 없음. changelog는 없어 질문 나옴.
    const io = stubIo({ selects: ["github-ai"], confirms: [false] });
    const r = await askAllOptionalWorkflows({
      tempDir, types: ["spring"], targetRoot: target, tty: true, io,
    });
    assert.equal(r.deploy, "none");
    assert.deepEqual(r.publish, ["nexus"]);
    assert.equal(r.secretBackup, false);
    assert.equal(io.calls.select.length, 1, "deploy 마이그레이션 유지, changelog만 질문");
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

test("askAllOptionalWorkflows: forceAsk=true(scope=null) — intent 포함 전부 재질문", async () => {
  const tempDir = makeTemplateFixture();
  const target = makeTmp();
  try {
    touch(target, "version.yml", VY_NEW("docker-ssh", [], false));
    // forceAsk → intent부터 재질문. select: intent(both) → deploy(none) → changelog(github-ai).
    // confirm: code_review(false) → secret(true). intent=both라 deploy·publish 둘 다 물음.
    const io = stubIo({ selects: ["both", "none", "github-ai"], multiselects: [["nexus", "github-packages"]], confirms: [false, true] });
    const r = await askAllOptionalWorkflows({
      tempDir, types: ["spring"], targetRoot: target, tty: true, io, forceAsk: true,
    });
    assert.equal(r.intent, "both");
    assert.equal(r.deploy, "none");
    assert.deepEqual(r.publish, ["nexus", "github-packages"]);
    assert.equal(r.secretBackup, true);
    assert.equal(r.changelogProvider, "github-ai");
    assert.equal(io.calls.select.length, 3, "intent + deploy + changelog");
    assert.equal(io.calls.multiselect.length, 1);
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

test("askAllOptionalWorkflows: multiselect ESC(cancel) → publish 빈 배열", async () => {
  const tempDir = makeTemplateFixture({ secretBackup: false });
  const target = makeTmp();
  try {
    // select: deploy(docker-ssh) → changelog(github-ai). confirm: code_review(false).
    const io = stubIo({ selects: ["docker-ssh", "github-ai"], multiselects: [Symbol("cancel")], confirms: [false] });
    const r = await askAllOptionalWorkflows({
      tempDir, types: ["spring"], targetRoot: target, tty: true, io,
    });
    assert.equal(r.deploy, "docker-ssh");
    assert.deepEqual(r.publish, []);
    assert.equal(r.secretBackup, false);
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

// ── 구 synology 키 → secret_backup 승계 (#473) ──

test("parseTemplateOptions: synology:true → secret_backup 미기재면 true 승계", () => {
  const y = 'metadata:\n  template:\n    options:\n      synology: true\n';
  assert.equal(parseTemplateOptions(y).secretBackup, true);
});

test("parseTemplateOptions: 신 secret_backup 키가 있으면 synology 무시 (신 키 우선)", () => {
  const y = 'metadata:\n  template:\n    options:\n      synology: true\n      secret_backup: false\n';
  assert.equal(parseTemplateOptions(y).secretBackup, false);
});

test("parseTemplateOptions: synology:false는 승계 안 함 (null 유지)", () => {
  const y = 'metadata:\n  template:\n    options:\n      synology: false\n';
  assert.equal(parseTemplateOptions(y).secretBackup, null);
});

// ── #483: scope로 한 축만 재질문 (수정 메뉴 격리) ──────────────────────────

test("askAllOptionalWorkflows: scope=[deploy]면 deploy만 재질문, 나머지는 current 유지", async () => {
  const tempDir = makeTemplateFixture();
  const target = makeTmp();
  try {
    // deploy select 1회만 응답 — 다른 축은 물으면 안 됨(스텁이 빈 응답이면 undefined로 깨질 것)
    const io = stubIo({ selects: ["vercel"] });
    const r = await askAllOptionalWorkflows({
      tempDir, types: ["spring"], targetRoot: target, tty: true, io,
      forceAsk: true, scope: ["deploy"],
      current: {
        deploy: "docker-ssh", publish: ["nexus"], secretBackup: true,
        codeReviewCoderabbit: true, changelogProvider: "commit", changelogBaseUrl: "", deployBranch: "release",
      },
    });
    assert.equal(r.deploy, "vercel", "deploy만 새 값");
    assert.deepEqual(r.publish, ["nexus"], "publish 유지");
    assert.equal(r.secretBackup, true, "secret 유지");
    assert.equal(r.codeReviewCoderabbit, true, "code-review 유지");
    assert.equal(r.changelogProvider, "commit", "changelog 유지");
    assert.equal(r.deployBranch, "release", "브랜치 유지");
    assert.equal(io.calls.select.length, 1, "deploy select 한 번만");
    assert.equal(io.calls.multiselect.length, 0, "publish 안 물음");
    assert.equal(io.calls.confirm.length, 0, "code-review/secret 안 물음");
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

test("askAllOptionalWorkflows: scope=[code-review]면 CodeRabbit만 재질문", async () => {
  const tempDir = makeTemplateFixture();
  const target = makeTmp();
  try {
    const io = stubIo({ confirms: [true] }); // code-review confirm 1회
    const r = await askAllOptionalWorkflows({
      tempDir, types: ["spring"], targetRoot: target, tty: true, io,
      forceAsk: true, scope: ["code-review"],
      current: {
        deploy: "docker-ssh", publish: [], secretBackup: false,
        codeReviewCoderabbit: false, changelogProvider: "github-ai", changelogBaseUrl: "", deployBranch: "develop",
      },
    });
    assert.equal(r.codeReviewCoderabbit, true, "code-review 새 값");
    assert.equal(r.deploy, "docker-ssh", "deploy 유지");
    assert.equal(io.calls.select.length, 0, "deploy/changelog 안 물음");
    assert.equal(io.calls.confirm.length, 1, "code-review confirm 한 번만");
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

test("askAllOptionalWorkflows: scope=null이면 forceAsk 시 intent+전 축 재질문", async () => {
  const tempDir = makeTemplateFixture();
  const target = makeTmp();
  try {
    // intent(both) → deploy(none) → changelog. multiselect: publish. confirm: code_review, secret
    const io = stubIo({ selects: ["both", "none", "github-ai"], multiselects: [[]], confirms: [false, false] });
    await askAllOptionalWorkflows({
      tempDir, types: ["spring"], targetRoot: target, tty: true, io, forceAsk: true,
      current: { deploy: "docker-ssh", publish: [], secretBackup: false, codeReviewCoderabbit: false, changelogProvider: "github-ai", changelogBaseUrl: "", deployBranch: "develop", intent: "both" },
    });
    assert.equal(io.calls.select.length, 3, "intent+deploy+changelog 물음(전 축)");
    assert.equal(io.calls.multiselect.length, 1, "publish도 물음");
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

// ── #481: 질문 안내 문구 (publish 명시 스킵 · CodeRabbit grant access · changelog 폴백) ──

test("askAllOptionalWorkflows: CodeRabbit '사용' 시 grant access 후속 안내 출력 (#481)", async () => {
  const tempDir = makeTemplateFixture();
  const target = makeTmp();
  try {
    const io = stubIo({ confirms: [true] }); // code-review only
    await askAllOptionalWorkflows({
      tempDir, types: ["spring"], targetRoot: target, tty: true, io,
      forceAsk: true, scope: ["code-review"],
      current: { deploy: "docker-ssh", publish: [], secretBackup: false, codeReviewCoderabbit: false, changelogProvider: "github-ai", changelogBaseUrl: "", deployBranch: "develop" },
    });
    assert.ok(io.calls.logs.some((l) => l.includes("coderabbit.ai")), "coderabbit.ai 안내 없음");
    assert.ok(io.calls.logs.some((l) => l.includes("grant access") || l.includes("접근 권한")), "grant access 안내 없음");
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

test("askAllOptionalWorkflows: CodeRabbit '미사용' 시 후속 안내 없음 (#481)", async () => {
  const tempDir = makeTemplateFixture();
  const target = makeTmp();
  try {
    const io = stubIo({ confirms: [false] });
    await askAllOptionalWorkflows({
      tempDir, types: ["spring"], targetRoot: target, tty: true, io,
      forceAsk: true, scope: ["code-review"],
      current: { deploy: "docker-ssh", publish: [], secretBackup: false, codeReviewCoderabbit: true, changelogProvider: "github-ai", changelogBaseUrl: "", deployBranch: "develop" },
    });
    assert.ok(!io.calls.logs.some((l) => l.includes("grant access") || l.includes("접근 권한")), "미사용인데 안내가 나옴");
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

test("askAllOptionalWorkflows: changelog 질문에 자동 폴백 안내 출력 (#481)", async () => {
  const tempDir = makeTemplateFixture();
  const target = makeTmp();
  try {
    const io = stubIo({ selects: ["openai"] });
    await askAllOptionalWorkflows({
      tempDir, types: ["spring"], targetRoot: target, tty: true, io,
      forceAsk: true, scope: ["changelog"],
      current: { deploy: "docker-ssh", publish: [], secretBackup: false, codeReviewCoderabbit: false, changelogProvider: "github-ai", changelogBaseUrl: "", deployBranch: "develop" },
    });
    assert.ok(io.calls.logs.some((l) => l.includes("폴백")), "폴백 안내 없음");
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

test("askAllOptionalWorkflows: publish 선택 없음 → '배포 안 함' 명시 로그 (#481)", async () => {
  const tempDir = makeTemplateFixture();
  const target = makeTmp();
  try {
    const io = stubIo({ multiselects: [[]] });
    const r = await askAllOptionalWorkflows({
      tempDir, types: ["spring"], targetRoot: target, tty: true, io,
      forceAsk: true, scope: ["publish"],
      current: { deploy: "docker-ssh", publish: null, secretBackup: false, codeReviewCoderabbit: false, changelogProvider: "github-ai", changelogBaseUrl: "", deployBranch: "develop" },
    });
    assert.deepEqual(r.publish, []);
    assert.ok(io.calls.logs.some((l) => l.includes("라이브러리 배포") && l.includes("안 함")), "배포 안 함 명시 없음");
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

// ── #480: deploy/publish 두 축 먼저 갈라 묻기 ──────────────────────────────

test("askAllOptionalWorkflows: intent=manual → 두 축 큰 그림 안내 + deploy 선택지에 라이브러리/CI 문구 없음 (#480)", async () => {
  const tempDir = makeTemplateFixture({ secretBackup: false });
  const target = makeTmp();
  try {
    // intent(manual) → deploy(docker-ssh) → changelog. manual이라 두 축 안내 + 둘 다 물음.
    const io = stubIo({ selects: ["manual", "docker-ssh", "github-ai"], multiselects: [[]], confirms: [false], texts: ["develop"] });
    await askAllOptionalWorkflows({ tempDir, types: ["spring"], targetRoot: target, tty: true, io });
    assert.ok(io.calls.logs.some((l) => l.includes("두 가지") && l.includes("독립")), "두 축 안내 없음");
    assert.ok(io.calls.logs.some((l) => l.includes("실행물")), "실행물 표현 없음");
    assert.ok(io.calls.select.some((m) => m.includes("실행물 배포 방식")), "deploy 질문 문구 미갱신");
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

test("askAllOptionalWorkflows: 한 축만 수정(scope)이면 큰 그림 안내 생략 (#480)", async () => {
  const tempDir = makeTemplateFixture();
  const target = makeTmp();
  try {
    const io = stubIo({ selects: ["vercel"] });
    await askAllOptionalWorkflows({
      tempDir, types: ["spring"], targetRoot: target, tty: true, io,
      forceAsk: true, scope: ["deploy"],
      current: { deploy: "docker-ssh", publish: ["nexus"], secretBackup: true, codeReviewCoderabbit: true, changelogProvider: "commit", changelogBaseUrl: "", deployBranch: "develop" },
    });
    assert.ok(!io.calls.logs.some((l) => l.includes("두 가지") && l.includes("독립")), "한 축 수정인데 큰 그림 안내가 나옴");
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

// ── #498: 타입별 적용 가능 deploy/publish 타겟 — 모바일 앱 타입 질문 스킵 ──

test("applicableTargets: 모바일 앱/basic은 두 축 모두 빈 배열, 서버형은 전체 유지 (#498)", () => {
  assert.deepEqual(applicableTargets(["flutter"]), { deploy: [], publish: [] });
  assert.deepEqual(applicableTargets(["react-native"]), { deploy: [], publish: [] });
  assert.deepEqual(applicableTargets(["react-native-expo"]), { deploy: [], publish: [] });
  assert.deepEqual(applicableTargets(["basic"]), { deploy: [], publish: [] });
  assert.deepEqual(applicableTargets(["spring"]), { deploy: ["docker-ssh", "vercel"], publish: ["nexus", "npm", "github-packages"] });
  // 멀티타입 합집합 — flutter+spring이면 spring 덕에 두 축 모두 살아 있다
  assert.deepEqual(applicableTargets(["flutter", "spring"]), { deploy: ["docker-ssh", "vercel"], publish: ["nexus", "npm", "github-packages"] });
});

test("타입 선언 정합성: 모든 VALID_TYPES에 선언 존재 + 템플릿 폴더와 모순 없음 (#498)", () => {
  const ROOT = process.cwd();
  for (const t of VALID_TYPES) {
    assert.ok(Array.isArray(TYPE_DEPLOY_TARGETS[t]), `TYPE_DEPLOY_TARGETS에 ${t} 선언 누락`);
    assert.ok(Array.isArray(TYPE_PUBLISH_TARGETS[t]), `TYPE_PUBLISH_TARGETS에 ${t} 선언 누락`);
    const typeDir = join(ROOT, ".github/workflows/project-types", t);
    // server-deploy 폴더 보유 타입은 docker-ssh가 반드시 선언돼 있어야 한다 (없으면 복사 게이트가 죽는다)
    if (existsSync(join(typeDir, "server-deploy"))) {
      assert.ok(TYPE_DEPLOY_TARGETS[t].includes("docker-ssh"), `${t}: server-deploy 폴더가 있는데 docker-ssh 미선언`);
    }
    // publish/<target> 폴더 보유 타입은 그 타겟이 선언에 포함돼야 한다
    const pubDir = join(typeDir, "publish");
    if (existsSync(pubDir)) {
      for (const target of readdirSync(pubDir)) {
        assert.ok(TYPE_PUBLISH_TARGETS[t].includes(target), `${t}: publish/${target} 폴더가 있는데 선언에 없음`);
      }
    }
  }
});

test("askAllOptionalWorkflows: flutter 단독 — intent/deploy/publish 질문 전부 스킵, none·[] (#498)", async () => {
  const tempDir = makeTemplateFixture({ secretBackup: false });
  const target = makeTmp();
  try {
    // basic 단독과 동일하게 배포 질문 없음 — select는 changelog 하나만
    const io = stubIo({ selects: ["github-ai"], confirms: [false], texts: ["develop"] });
    const r = await askAllOptionalWorkflows({
      tempDir, types: ["flutter"], targetRoot: target, tty: true, io,
    });
    assert.equal(r.deploy, "none");
    assert.deepEqual(r.publish, []);
    assert.equal(r.intent, "none");
    assert.equal(io.calls.select.length, 1, "intent/deploy 스킵 — changelog만");
    assert.equal(io.calls.multiselect.length, 0, "publish 질문 안 함");
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

test("askAllOptionalWorkflows: flutter 단독 + 저장값 docker-ssh — 조용히 none 정리, 안내 없음 (#498)", async () => {
  const tempDir = makeTemplateFixture({ secretBackup: false });
  const target = makeTmp();
  try {
    // 구버전 통합으로 flutter 단독인데 deploy: docker-ssh가 저장된 케이스 (실측: elum)
    touch(target, "version.yml", VY_NEW("docker-ssh", ["nexus"], false).replace('["spring"]', '["flutter"]'));
    const io = stubIo({ selects: ["github-ai"], confirms: [false], texts: ["develop"] });
    const r = await askAllOptionalWorkflows({
      tempDir, types: ["flutter"], targetRoot: target, tty: true, io,
    });
    assert.equal(r.deploy, "none", "적용 불가 docker-ssh는 none으로 정리");
    assert.deepEqual(r.publish, [], "적용 불가 nexus는 제거");
    assert.equal(r.intent, "none");
    assert.equal(io.calls.select.length, 1, "재질문 없음 — changelog만");
    // 사용자 방침: 경고/안내 자체가 불필요 — 정리 관련 ⚠ 문구가 없어야 한다
    assert.ok(!io.calls.logs.some((l) => l.includes("⚠") && l.includes("deploy")), "정리에 경고 문구가 나옴");
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

test("askAllOptionalWorkflows: flutter+spring 멀티타입 — 질문 유지 (#498)", async () => {
  const tempDir = makeTemplateFixture({ secretBackup: false });
  const target = makeTmp();
  try {
    // spring이 있으므로 intent 질문부터 정상 진행
    const io = stubIo({ selects: ["app", "docker-ssh", "github-ai"], confirms: [false], texts: ["develop"] });
    const r = await askAllOptionalWorkflows({
      tempDir, types: ["flutter", "spring"], targetRoot: target, tty: true, io,
    });
    assert.equal(r.intent, "app");
    assert.equal(r.deploy, "docker-ssh");
    assert.equal(io.calls.select.length, 3, "intent + deploy + changelog");
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

test("askAllOptionalWorkflows: 비대화형 flutter 단독 — 기본값도 none으로 확정 (#498)", async () => {
  const tempDir = makeTemplateFixture({ secretBackup: false });
  const target = makeTmp();
  try {
    const io = stubIo(); // 호출 자체가 없어야 함
    const r = await askAllOptionalWorkflows({
      tempDir, types: ["flutter"], targetRoot: target, force: true, tty: false, io,
    });
    assert.equal(r.deploy, "none", "docker-ssh 기본값이 새어 나가면 안 됨");
    assert.deepEqual(r.publish, []);
    assert.equal(r.intent, "none");
    assert.equal(io.calls.select.length, 0);
  } finally { rmSync(tempDir, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});
