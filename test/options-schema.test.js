// Checks that the option source of truth (options-schema.js) does not drift from the real code.
// If it drifts, AI agents use options that do not exist or miss ones that do.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { FLAGS, MODES, VERSION_YML, buildSchema } from "../src/core/options-schema.js";
import { MODE_VALUES } from "../src/cli/args.js";
import { VALID_TYPES } from "../src/context.js";
import { parseTemplateOptions } from "../src/core/version-yml.js";

const ARGS_SRC = readFileSync(new URL("../src/cli/args.js", import.meta.url), "utf8");

test("every CLI flag in args.js is in the source of truth", () => {
  const inCode = new Set([...ARGS_SRC.matchAll(/case "(-{1,2}[a-z-]+)"/g)].map((m) => m[1]));
  const inSchema = new Set(FLAGS.flatMap((f) => [f.flag, f.alias, ...(f.aliases ?? []), f.negation].filter(Boolean)));
  const missing = [...inCode].filter((f) => !inSchema.has(f));
  assert.deepEqual(missing, [], `flags missing from the source of truth (src/core/options-schema.js): ${missing.join(", ")}`);
  const ghost = [...inSchema].filter((f) => !inCode.has(f));
  assert.deepEqual(ghost, [], `flags only in the source of truth, not in the code: ${ghost.join(", ")}`);
});

test("the mode list matches the code", () => {
  assert.deepEqual(MODES.map((m) => m.name).sort(), [...MODE_VALUES].sort());
});

test("--type values match VALID_TYPES", () => {
  assert.deepEqual(FLAGS.find((f) => f.flag === "--type").values, VALID_TYPES);
});

test("every key parseTemplateOptions returns is in the version.yml source of truth", () => {
  const parsed = Object.keys(parseTemplateOptions(""));
  const documented = new Set(VERSION_YML.map((k) => k.parserKey).filter(Boolean));
  const missing = parsed.filter((k) => !documented.has(k));
  assert.deepEqual(missing, [], `options without a description in the source of truth: ${missing.join(", ")}`);
});

test("every entry has a description and every enum has a value list", () => {
  for (const f of FLAGS) assert.ok(f.description || f.deprecated, `${f.flag}: no description`);
  for (const k of VERSION_YML) {
    assert.ok(k.description, `${k.path}: no description`);
    if (k.type.startsWith("enum")) assert.ok(Array.isArray(k.values) && k.values.length, `${k.path}: no enum values`);
  }
});

test("--mode options --json is parseable JSON", () => {
  const out = execFileSync("node", ["bin/projectops.js", "--mode", "options", "--json"], { encoding: "utf8" });
  const j = JSON.parse(out);
  assert.equal(j.tool, "projectops");
  assert.equal(j.schemaVersion, buildSchema().schemaVersion);
  assert.ok(j.flags.length > 10 && j.versionYml.length > 10);
});

test("--mode options prints a human-readable table without network or writes", () => {
  const out = execFileSync("node", ["bin/projectops.js", "--mode", "options"], { encoding: "utf8" });
  assert.match(out, /VERSION\.YML KEYS/);
  assert.match(out, /semver_auto/);
});

// ── agent guide file ──────────────────────────────────────────────────────
import { mkdtempSync, rmSync, existsSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { installAgentGuide, AGENT_GUIDE_PATH, agentGuideText } from "../src/core/agent-guide.js";
import { DOCS_TO_REMOVE } from "../src/core/exclusions.js";

test("the agent guide installed in user repos points to the command instead of embedding an option table", () => {
  const root = mkdtempSync(join(tmpdir(), "ag-"));
  try {
    installAgentGuide(root, "4.99.0");
    const text = readFileSync(join(root, AGENT_GUIDE_PATH), "utf8");
    assert.match(text, /npx projectops --mode options --json/);
    assert.match(text, /--mode doctor/);
    assert.match(text, /4\.99\.0/);
    // Copying option values into docs makes them stale fast — key names at most, no tables
    assert.doesNotMatch(text, /\| *semver_auto *\|/);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("this repo's AGENTS.md covers every tracked skill", () => {
  const agents = readFileSync(new URL("../AGENTS.md", import.meta.url), "utf8");
  const skills = readdirSync(new URL("../skills", import.meta.url), { withFileTypes: true })
    .filter((e) => e.isDirectory() && existsSync(new URL(`../skills/${e.name}/SKILL.md`, import.meta.url)))
    .map((e) => e.name);
  // Only checks that the skill folders were read (lower bound). Skill counts go up and down, so no exact count is pinned (#849)
  assert.ok(skills.length >= 10, `could not read the skill folders: ${skills.length}`);
  const missing = skills.filter((s) => !agents.includes(`\`${s}\``));
  assert.deepEqual(missing, [], `skills missing from the AGENTS.md routing table: ${missing.join(", ")}`);
});

test("template-only guide files are not copied into user projects", () => {
  for (const f of ["AGENTS.md", "GEMINI.md", "llms.txt", "CODE_OF_CONDUCT.md"]) assert.ok(DOCS_TO_REMOVE.includes(f), `${f} is not in the copy exclusion list`);
  const initializer = readFileSync(new URL("../.github/scripts/template_initializer.py", import.meta.url), "utf8");
  for (const f of ["AGENTS.md", "GEMINI.md", "llms.txt", "CODE_OF_CONDUCT.md"]) assert.ok(initializer.includes(`("${f}"`), `${f} is not in the initializer delete list`);
});

// ── Detailed enough for an agent to read and decide? (#835 follow-up) ──────────────────────────────
// This CLI is called by AI agents without a person. A short one-line description does not say "when to use it · what changes in the repo ·
// what happens if omitted", so agents guess. New flags and options cannot pass without details.
import { FLAG_DETAILS, KEY_DETAILS, RECIPES, AGENT_RULES, OUTPUT_FILES, renderText } from "../src/core/options-schema.js";
import { helpText } from "../src/cli/help.js";

test("every (non-deprecated) flag has when · effect · omitted", () => {
  const missing = [];
  for (const f of FLAGS.filter((x) => !x.deprecated)) {
    const d = FLAG_DETAILS[f.flag];
    if (!d || !d.when || !d.effect || !d.omitted) missing.push(f.flag);
  }
  assert.deepEqual(missing, [], `flags without details: ${missing.join(", ")} — add when/effect/omitted to FLAG_DETAILS in options-schema.js`);
});

test("every version.yml key has when · effect", () => {
  const missing = VERSION_YML.filter((k) => !KEY_DETAILS[k.path]?.when || !KEY_DETAILS[k.path]?.effect).map((k) => k.path);
  assert.deepEqual(missing, [], `keys without details: ${missing.join(", ")} — add them to KEY_DETAILS`);
});

test("the details tables hold no entries missing from the source of truth (typos, removed flags)", () => {
  const flags = new Set(FLAGS.map((f) => f.flag));
  assert.deepEqual(Object.keys(FLAG_DETAILS).filter((k) => !flags.has(k)), []);
  const keys = new Set(VERSION_YML.map((k) => k.path));
  assert.deepEqual(Object.keys(KEY_DETAILS).filter((k) => !keys.has(k)), []);
});

test("details are not one-word hand-waving", () => {
  for (const [name, d] of [...Object.entries(FLAG_DETAILS), ...Object.entries(KEY_DETAILS)]) {
    assert.ok((d.effect || "").length >= 20, `${name}: effect is too short`);
    assert.ok((d.when || "").length >= 10, `${name}: when is too short`);
  }
});

test("example commands use only real flags", () => {
  const known = new Set(FLAGS.flatMap((f) => [f.flag, f.alias, ...(f.aliases ?? []), f.negation].filter(Boolean)));
  for (const cmd of [...Object.values(FLAG_DETAILS).map((d) => d.example), ...RECIPES.map((r) => r.command)].filter((c) => c?.startsWith("npx projectops"))) {
    for (const m of cmd.matchAll(/\s(--?[a-z][a-z-]*)/g)) assert.ok(known.has(m[1]), `${m[1]} in example "${cmd}" is not a real flag`);
  }
});

test("agent rules, recipes and the output file table exist and all appear in the text output", () => {
  assert.ok(AGENT_RULES.length >= 6 && RECIPES.length >= 6 && OUTPUT_FILES.length >= 6);
  const text = renderText(buildSchema("x"));
  for (const sec of ["RULES FOR AGENTS", "RECIPES", "FLAGS", "VERSION.YML KEYS", "FILES WRITTEN"]) assert.match(text, new RegExp(sec));
  assert.match(text, /if omitted:/);
  assert.match(text, /caution:/);
});

test("each flag entry of --mode options --json includes its details", () => {
  const j = buildSchema("x");
  const cr = j.flags.find((f) => f.flag === "--coderabbit");
  assert.ok(cr.when && cr.effect && cr.omitted && cr.caution && cr.example);
  assert.match(cr.effect, /\.coderabbit\.yaml/);
  assert.match(cr.omitted, /Off/);
  assert.ok(j.versionYml.find((k) => k.path.endsWith("excluded_workflows")).effect);
});

test("--help explains the question rules, --force meaning, exit codes and result locations (en and ko)", () => {
  for (const [lang, must] of [
    ["en", [/asks NOTHING/, /--force/, /never overwrites/, /exit code/i, /\.github\/\.projectops\/incoming/, /--mode options --json/, /--coderabbit/]],
    ["ko", [/묻지 않는다/, /--force/, /덮어쓰지 않는다/, /종료 코드/, /\.github\/\.projectops\/incoming/, /--mode options --json/, /--coderabbit/]],
  ]) {
    const text = helpText(lang);
    for (const re of must) assert.match(text, re, `${lang} --help is missing ${re}`);
  }
});

test("CodeRabbit can be toggled by flag; if omitted, saved value → off", async () => {
  const { parseArgs } = await import("../src/cli/args.js");
  assert.equal(parseArgs(["--mode", "full", "--coderabbit"]).codeReviewCoderabbit, true);
  assert.equal(parseArgs(["--mode", "full", "--no-coderabbit"]).codeReviewCoderabbit, false);
  assert.equal(parseArgs(["--mode", "full"]).codeReviewCoderabbit, null);   // null = nothing said → saved value, else default (off)
});

// ── project type registry (#1244) ────────────────────────────────────────
// src/core/project-types.json is the only source of type facts; these checks keep it valid and in step with the repo.
import { PROJECT_TYPES, VALID_TYPES as REGISTRY_TYPES, validateRegistry, deployTriggerWorkflows } from "../src/core/project-types.js";
import { DEPLOY_TARGETS, PUBLISH_TARGETS } from "../src/core/constants.js";

const PROJECT_TYPES_DIR = ".github/workflows/project-types";

// Every file name under a folder, recursively
function listFileNames(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory() ? listFileNames(join(directory, entry.name)) : [entry.name]);
}

test("registry validates", () => {
  assert.deepEqual(validateRegistry(PROJECT_TYPES), []);
});

test("registry rejects unknown fields", () => {
  const problems = validateRegistry([{ ...PROJECT_TYPES[0], markes: [] }]);
  assert.equal(problems.length, 1);
  assert.match(problems[0], /markes/);
});

test("every workflow folder is a registry type", () => {
  const folders = readdirSync(PROJECT_TYPES_DIR, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && entry.name !== "common").map((entry) => entry.name);
  assert.deepEqual(folders.filter((name) => !REGISTRY_TYPES.includes(name)), []);
});

test("deploy trigger workflows exist", () => {
  const existing = new Set(listFileNames(PROJECT_TYPES_DIR));
  assert.deepEqual(deployTriggerWorkflows().filter((name) => !existing.has(name)), []);
});

test("axes use known targets", () => {
  for (const type of PROJECT_TYPES) {
    for (const target of type.axes.deploy) assert.ok(DEPLOY_TARGETS.includes(target), `${type.id}: deploy ${target}`);
    for (const target of type.axes.publish) assert.ok(PUBLISH_TARGETS.includes(target), `${type.id}: publish ${target}`);
  }
});

test("package.json classification follows the registry dependency rules", async () => {
  const { classifyPackageText } = await import("../src/core/detect.js");
  const classify = (packageJson) => classifyPackageText(typeof packageJson === "string" ? packageJson : JSON.stringify(packageJson));
  // "export" in a script must not read as an expo dependency
  assert.equal(classify({ dependencies: { "react-native": "1" }, scripts: { build: "next export" } }), "react-native");
  assert.equal(classify({ dependencies: { expo: "1", "react-native": "1" } }), "react-native-expo");
  assert.equal(classify({ devDependencies: { "@react-native/babel-preset": "1" } }), "react-native");
  assert.equal(classify({ dependencies: { next: "1" } }), "react");
  assert.equal(classify({ name: "tool" }), "node");
  // Broken JSON keeps the old text rule instead of failing
  assert.equal(classify('{"react-native" expo'), "react-native-expo");
});

test("generated project type copies and doc blocks are current", () => {
  // Throws (exit 1) when a copy or a <!-- generated: project-types:* --> block is stale
  execFileSync("node", ["scripts/build_project_types.mjs", "--check"], { encoding: "utf8", stdio: "pipe" });
});

test("every registry version handler exists in version_manager.py", () => {
  // Handler table keys, read as text so the check stays in Node: "name": VersionFormat(... / "name": sync_...
  const versionManagerText = readFileSync(".github/scripts/version_manager.py", "utf8");
  const tableKeys = (tableName) => {
    const tableText = versionManagerText.slice(versionManagerText.indexOf(`${tableName} = {`));
    return new Set([...tableText.slice(0, tableText.indexOf("\n}")).matchAll(/^\s+"([a-z_]+)":/gm)].map((match) => match[1]));
  };
  const formats = tableKeys("VERSION_FORMAT_HANDLERS");
  const buildNumbers = tableKeys("BUILD_NUMBER_HANDLERS");
  for (const type of PROJECT_TYPES) {
    if (type.version.format) assert.ok(formats.has(type.version.format), `${type.id}: no version format handler "${type.version.format}"`);
    if (type.version.build_number) assert.ok(buildNumbers.has(type.version.build_number), `${type.id}: no build number handler "${type.version.build_number}"`);
  }
});
