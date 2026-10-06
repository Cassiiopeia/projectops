// QA 봇 워크플로우의 실제 JS 를 가짜 github/context 로 실행해, 게시되는 내용이 언어별로 맞는지 본다 (#787).
// 한국어는 이관 전 JS 가 만들던 문자열(골든)과 바이트 동일해야 한다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const ROOT = join(import.meta.dirname, "..");
const YAML = readFileSync(join(ROOT, ".github/workflows/PROJECT-COMMON-QA-ISSUE-CREATION-BOT.yaml"), "utf8");
const GOLD = JSON.parse(readFileSync(join(ROOT, ".github/scripts/test/golden/qa_bot_ko.json"), "utf8"));

// "QA 이슈 생성" 스텝의 script 본문을 꺼내 들여쓰기를 걷는다
function stepScript() {
  const i = YAML.indexOf("      - name: QA 이슈 생성");
  const k = YAML.indexOf("script: |", i) + "script: |\n".length;
  const rest = YAML.slice(k);
  const end = rest.search(/\n {6}- name:/);
  const block = end === -1 ? rest : rest.slice(0, end);
  return block.split("\n").map((l) => (l.startsWith(" ".repeat(12)) ? l.slice(12) : l)).join("\n");
}

async function run(isPr, lang) {
  const calls = [];
  const github = { rest: {
    pulls: { get: async () => ({ data: { head: { ref: "20261007_#12_login" } } }) },
    issues: {
      get: async () => ({ data: { title: "🚀 [버그] 로그인 실패" } }),
      create: async (a) => { calls.push(["create", a]); return { data: { number: 56 } }; },
      createComment: async (a) => { calls.push(["comment", a]); },
    },
  } };
  const context = { repo: { owner: "o", repo: "r" }, payload: {
    comment: { user: { login: "octo" }, id: 1 },
    issue: { number: isPr ? 34 : 12, title: "🚀 [버그] 로그인 실패", user: { login: "octo" }, ...(isPr ? { pull_request: {} } : {}) },
  } };
  const saved = { ...process.env };
  process.env.REPO_LANG = lang;
  process.env.DEFAULT_QA_ASSIGNEE = "default";
  const prevCwd = process.cwd();
  process.chdir(ROOT); // 워크플로우는 체크아웃한 저장소 루트에서 python3 .github/scripts/... 를 부른다
  try {
    const { createRequire } = await import("node:module");
    const fn = new Function("github", "context", "process", "require", "console",
      `return (async () => {${stepScript()}})()`);
    await fn(github, context, process, createRequire(import.meta.url), { log() {}, error() {} });
  } finally {
    process.chdir(prevCwd);
    process.env = saved;
  }
  return { create: calls.find((c) => c[0] === "create")[1], comment: calls.find((c) => c[0] === "comment")[1] };
}

for (const [key, isPr] of [["issue", false], ["pr", true]]) {
  test(`한국어 게시 내용이 이관 전과 바이트 동일하다 (${key})`, async () => {
    const { create, comment } = await run(isPr, "ko");
    assert.equal(create.title, GOLD[key].qaTitle);
    assert.equal(create.body, GOLD[key].qaBody);
    assert.equal(comment.body, GOLD[key].commentBody);
  });

  test(`영문 게시 내용에는 한글이 없고 태그는 영문 표준이다 (${key})`, async () => {
    const { create, comment } = await run(isPr, "en");
    const text = [create.title, create.body, comment.body].join("\n").replaceAll("로그인 실패", "");
    assert.ok(!/[가-힣]/.test(text), text.match(/.*[가-힣].*/)?.[0]);
    assert.match(create.title, /^🔍 \[QA\]/);
  });
}

test("라벨과 담당자 같은 동작은 언어와 무관하다", async () => {
  for (const lang of ["en", "ko"]) {
    const { create } = await run(false, lang);
    assert.deepEqual(create.labels, ["status: todo"]);
    assert.deepEqual(create.assignees, ["octo"]);
  }
});
