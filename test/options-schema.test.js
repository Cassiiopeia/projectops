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
  for (const f of ["AGENTS.md", "GEMINI.md", "llms.txt", "CODE_OF_CONDUCT.md"]) assert.ok(DOCS_TO_REMOVE.includes(f), `${f} 가 복사 제외 목록에 없다`);
  const initializer = readFileSync(new URL("../.github/scripts/template_initializer.py", import.meta.url), "utf8");
  for (const f of ["AGENTS.md", "GEMINI.md", "llms.txt", "CODE_OF_CONDUCT.md"]) assert.ok(initializer.includes(`("${f}"`), `${f} 가 initializer 삭제 목록에 없다`);
});

// ── agent 가 읽고 판단할 수 있을 만큼 자세한가 (#835 후속) ──────────────────────────────
// 이 CLI 는 사람 없이 AI agent 가 부른다. 짧은 한 줄 설명만으로는 "언제 쓰나 · 레포에서 무엇이 바뀌나 ·
// 안 주면 어떻게 되나"를 알 수 없어 agent 가 추측하게 된다. 새 플래그·옵션은 상세 없이는 통과하지 못한다.
import { FLAG_DETAILS, KEY_DETAILS, RECIPES, AGENT_RULES, OUTPUT_FILES, renderText } from "../src/core/options-schema.js";
import { helpText } from "../src/cli/help.js";

test("모든 (폐기 아닌) 플래그에 when · effect · omitted 가 있다", () => {
  const missing = [];
  for (const f of FLAGS.filter((x) => !x.deprecated)) {
    const d = FLAG_DETAILS[f.flag];
    if (!d || !d.when || !d.effect || !d.omitted) missing.push(f.flag);
  }
  assert.deepEqual(missing, [], `상세가 없는 플래그: ${missing.join(", ")} — options-schema.js 의 FLAG_DETAILS 에 when/effect/omitted 를 적는다`);
});

test("모든 version.yml 키에 when · effect 가 있다", () => {
  const missing = VERSION_YML.filter((k) => !KEY_DETAILS[k.path]?.when || !KEY_DETAILS[k.path]?.effect).map((k) => k.path);
  assert.deepEqual(missing, [], `상세가 없는 키: ${missing.join(", ")} — KEY_DETAILS 에 적는다`);
});

test("상세 표에 정본에 없는 항목(오타·삭제된 플래그)이 남아 있지 않다", () => {
  const flags = new Set(FLAGS.map((f) => f.flag));
  assert.deepEqual(Object.keys(FLAG_DETAILS).filter((k) => !flags.has(k)), []);
  const keys = new Set(VERSION_YML.map((k) => k.path));
  assert.deepEqual(Object.keys(KEY_DETAILS).filter((k) => !keys.has(k)), []);
});

test("상세는 한 단어짜리 얼버무림이 아니다", () => {
  for (const [name, d] of [...Object.entries(FLAG_DETAILS), ...Object.entries(KEY_DETAILS)]) {
    assert.ok((d.effect || "").length >= 20, `${name}: effect 가 너무 짧다`);
    assert.ok((d.when || "").length >= 10, `${name}: when 이 너무 짧다`);
  }
});

test("예시 명령은 실제 플래그만 쓴다", () => {
  const known = new Set(FLAGS.flatMap((f) => [f.flag, f.alias, ...(f.aliases ?? []), f.negation].filter(Boolean)));
  for (const cmd of [...Object.values(FLAG_DETAILS).map((d) => d.example), ...RECIPES.map((r) => r.command)].filter((c) => c?.startsWith("npx projectops"))) {
    for (const m of cmd.matchAll(/\s(--?[a-z][a-z-]*)/g)) assert.ok(known.has(m[1]), `예시 "${cmd}" 의 ${m[1]} 는 없는 플래그다`);
  }
});

test("agent 규칙·레시피·출력 파일 표가 있고 text 출력에 모두 나온다", () => {
  assert.ok(AGENT_RULES.length >= 6 && RECIPES.length >= 6 && OUTPUT_FILES.length >= 6);
  const text = renderText(buildSchema("x"));
  for (const sec of ["RULES FOR AGENTS", "RECIPES", "FLAGS", "VERSION.YML KEYS", "FILES WRITTEN"]) assert.match(text, new RegExp(sec));
  assert.match(text, /if omitted:/);
  assert.match(text, /caution:/);
});

test("--mode options --json 의 각 플래그 항목에 상세가 합쳐져 있다", () => {
  const j = buildSchema("x");
  const cr = j.flags.find((f) => f.flag === "--coderabbit");
  assert.ok(cr.when && cr.effect && cr.omitted && cr.caution && cr.example);
  assert.match(cr.effect, /\.coderabbit\.yaml/);
  assert.match(cr.omitted, /Off/);
  assert.ok(j.versionYml.find((k) => k.path.endsWith("excluded_workflows")).effect);
});

test("--help 가 질문 규칙·--force 의미·종료 코드·결과 위치를 설명한다 (영·한)", () => {
  for (const [lang, must] of [
    ["en", [/asks NOTHING/, /--force/, /never overwrites/, /exit code/i, /\.github\/\.projectops\/incoming/, /--mode options --json/, /--coderabbit/]],
    ["ko", [/묻지 않는다/, /--force/, /덮어쓰지 않는다/, /종료 코드/, /\.github\/\.projectops\/incoming/, /--mode options --json/, /--coderabbit/]],
  ]) {
    const text = helpText(lang);
    for (const re of must) assert.match(text, re, `${lang} --help 에 ${re} 가 없다`);
  }
});

test("CodeRabbit 은 플래그로 켜고 끌 수 있고 안 주면 저장값 → 꺼짐 순이다", async () => {
  const { parseArgs } = await import("../src/cli/args.js");
  assert.equal(parseArgs(["--mode", "full", "--coderabbit"]).codeReviewCoderabbit, true);
  assert.equal(parseArgs(["--mode", "full", "--no-coderabbit"]).codeReviewCoderabbit, false);
  assert.equal(parseArgs(["--mode", "full"]).codeReviewCoderabbit, null);   // null = 말이 없었다 → 저장값, 없으면 기본(꺼짐)
});
