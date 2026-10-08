// 옵션 정본(options-schema.js)이 실제 코드와 어긋나지 않는지 대조한다.
// 어긋나면 AI agent 가 없는 옵션을 쓰거나 있는 옵션을 모르게 된다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { FLAGS, MODES, VERSION_YML, buildSchema } from "../src/core/options-schema.js";
import { MODE_VALUES } from "../src/cli/args.js";
import { VALID_TYPES } from "../src/context.js";
import { parseTemplateOptions } from "../src/core/version-yml.js";

const ARGS_SRC = readFileSync(new URL("../src/cli/args.js", import.meta.url), "utf8");

test("args.js 의 모든 CLI 플래그가 정본에 있다", () => {
  const inCode = new Set([...ARGS_SRC.matchAll(/case "(-{1,2}[a-z-]+)"/g)].map((m) => m[1]));
  const inSchema = new Set(FLAGS.flatMap((f) => [f.flag, f.alias, ...(f.aliases ?? []), f.negation].filter(Boolean)));
  const missing = [...inCode].filter((f) => !inSchema.has(f));
  assert.deepEqual(missing, [], `정본(src/core/options-schema.js)에 없는 플래그: ${missing.join(", ")}`);
  const ghost = [...inSchema].filter((f) => !inCode.has(f));
  assert.deepEqual(ghost, [], `코드에 없는데 정본에만 있는 플래그: ${ghost.join(", ")}`);
});

test("모드 목록이 코드와 같다", () => {
  assert.deepEqual(MODES.map((m) => m.name).sort(), [...MODE_VALUES].sort());
});

test("--type 값이 VALID_TYPES 와 같다", () => {
  assert.deepEqual(FLAGS.find((f) => f.flag === "--type").values, VALID_TYPES);
});

test("parseTemplateOptions 가 돌려주는 모든 키가 version.yml 정본에 있다", () => {
  const parsed = Object.keys(parseTemplateOptions(""));
  const documented = new Set(VERSION_YML.map((k) => k.parserKey).filter(Boolean));
  const missing = parsed.filter((k) => !documented.has(k));
  assert.deepEqual(missing, [], `정본에 설명이 없는 옵션: ${missing.join(", ")}`);
});

test("모든 항목에 설명이 있고 enum 에는 값 목록이 있다", () => {
  for (const f of FLAGS) assert.ok(f.description || f.deprecated, `${f.flag}: 설명 없음`);
  for (const k of VERSION_YML) {
    assert.ok(k.description, `${k.path}: 설명 없음`);
    if (k.type.startsWith("enum")) assert.ok(Array.isArray(k.values) && k.values.length, `${k.path}: enum 값 없음`);
  }
});

test("--mode options --json 은 파싱 가능한 JSON 이다", () => {
  const out = execFileSync("node", ["bin/projectops.js", "--mode", "options", "--json"], { encoding: "utf8" });
  const j = JSON.parse(out);
  assert.equal(j.tool, "projectops");
  assert.equal(j.schemaVersion, buildSchema().schemaVersion);
  assert.ok(j.flags.length > 10 && j.versionYml.length > 10);
});

test("--mode options 는 네트워크·쓰기 없이 사람이 읽는 표를 낸다", () => {
  const out = execFileSync("node", ["bin/projectops.js", "--mode", "options"], { encoding: "utf8" });
  assert.match(out, /VERSION\.YML KEYS/);
  assert.match(out, /semver_auto/);
});

// ── agent 안내 파일 ──────────────────────────────────────────────────────
import { mkdtempSync, rmSync, existsSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { installAgentGuide, AGENT_GUIDE_PATH, agentGuideText } from "../src/core/agent-guide.js";
import { DOCS_TO_REMOVE } from "../src/core/exclusions.js";

test("사용자 레포에 설치되는 agent 안내는 옵션 표를 박지 않고 명령으로 안내한다", () => {
  const root = mkdtempSync(join(tmpdir(), "ag-"));
  try {
    installAgentGuide(root, "4.99.0");
    const text = readFileSync(join(root, AGENT_GUIDE_PATH), "utf8");
    assert.match(text, /npx projectops --mode options --json/);
    assert.match(text, /--mode doctor/);
    assert.match(text, /4\.99\.0/);
    // 옵션 값을 문서에 복제하면 곧 낡는다 — 키 이름 정도만 허용하고 표는 두지 않는다
    assert.doesNotMatch(text, /\| *semver_auto *\|/);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("이 레포의 AGENTS.md 는 추적되는 스킬을 빠짐없이 안내한다", () => {
  const agents = readFileSync(new URL("../AGENTS.md", import.meta.url), "utf8");
  const skills = readdirSync(new URL("../skills", import.meta.url), { withFileTypes: true })
    .filter((e) => e.isDirectory() && existsSync(new URL(`../skills/${e.name}/SKILL.md`, import.meta.url)))
    .map((e) => e.name);
  assert.ok(skills.length >= 20);
  const missing = skills.filter((s) => !agents.includes(`\`${s}\``));
  assert.deepEqual(missing, [], `AGENTS.md 라우팅 표에 없는 스킬: ${missing.join(", ")}`);
});

test("템플릿 전용 안내 파일은 사용자 프로젝트로 복사되지 않는다", () => {
  for (const f of ["AGENTS.md", "GEMINI.md", "llms.txt"]) assert.ok(DOCS_TO_REMOVE.includes(f), `${f} 가 복사 제외 목록에 없다`);
  const initializer = readFileSync(new URL("../.github/scripts/template_initializer.py", import.meta.url), "utf8");
  for (const f of ["AGENTS.md", "GEMINI.md", "llms.txt"]) assert.ok(initializer.includes(`("${f}"`), `${f} 가 initializer 삭제 목록에 없다`);
});
