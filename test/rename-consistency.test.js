// #459 namespace neutralization consistency regression test.
// Blocks leftover suh-* skill names and the cassiiopeia plugin name, and keeps external entities (to be preserved) alive.
//
// OS independent: only the tracked file list comes from the shell via `git ls-files` instead of git grep; content checks use Node fs.
// (Fixes false hits caused by git grep pathspec magic, the `:` special character and shell quoting behaving differently on Windows CI.)
import { test } from "node:test";
import assert from "node:assert/strict";
import { execSync } from "node:child_process";
import { readdirSync, statSync, existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

const ROOT = process.cwd();

// Tracked file list (node_modules and .git excluded automatically). git always uses '/' as the path separator (Windows too).
const TRACKED = execSync("git ls-files", { cwd: ROOT, encoding: "utf-8" })
  .split("\n").map((s) => s.trim()).filter(Boolean);

// History (past outputs, specs), CHANGELOG and breaking-changes (old→new notes) are excluded from the leftover check.
// This test file itself contains the search strings (cassiiopeia:suh-, etc.) as literals, so it is excluded too.
const EXCLUDE_PREFIX = ["docs/superpowers/", "docs/projectops/"];
const EXCLUDE_EXACT = [
  "CHANGELOG.md", "CHANGELOG.json", ".github/config/breaking-changes.json",
  "test/rename-consistency.test.js",
  // Legacy auto-migration logic — detecting and cleaning up the old plugin/config name (cassiiopeia)
  // requires referencing that string literally (#459 policy: detection/migration logic keeps the old name).
  "src/core/ide/legacy.js",
  "src/core/ide/adapters/claude.js",
  "src/core/ide/adapters/cursor.js",
];

function isExcluded(path) {
  if (EXCLUDE_EXACT.includes(path)) return true;
  return EXCLUDE_PREFIX.some((p) => path.startsWith(p));
}

// Whether path matches one of the given matchers (extension/path prefix).
function matchScope(path, scopes) {
  return scopes.some((s) => {
    if (s.startsWith("ext:")) return path.endsWith(s.slice(4));
    if (s.endsWith("/")) return path.startsWith(s);   // Directory prefix
    return path === s;                                 // Exact file
  });
}

// Returns paths of tracked files in scopes that contain substring (exclusion list applied).
// allow: official literals stripped before checking (e.g. the GitHub Pages domain is officially lowercase).
function findFiles(substring, scopes, allow = []) {
  const hits = [];
  for (const path of TRACKED) {
    if (isExcluded(path)) continue;
    if (!matchScope(path, scopes)) continue;
    let content;
    try { content = readFileSync(join(ROOT, path), "utf-8"); }
    catch { continue; } // Skip binaries and read failures
    for (const a of allow) content = content.split(a).join("");
    if (content.includes(substring)) hits.push(path);
  }
  return hits;
}

const DOC_CODE = ["ext:.md", "ext:.js", "ext:.py"]; // Active docs and code

test("no suh- folders under skills/", () => {
  const dirs = readdirSync(join(ROOT, "skills"))
    .filter((d) => statSync(join(ROOT, "skills", d)).isDirectory() && d.startsWith("suh-"));
  assert.deepEqual(dirs, [], `leftover suh- skill folders: ${dirs.join(", ")}`);
});

test("all core pro- skill folders exist", () => {
  // pro-issue was merged into pro-github and deleted in #467 (25→24)
  // design, design-analyze, refactor, refactor-analyze, test, ppt and document (7) overlapped superpowers and
  // pro-report and were deleted (24→17)
  // pro-spring-test was deleted in #582 — a template that produced tests without assertions (17→16)
  // pro-figma was merged into pro-figma-verify and deleted in #619 — moving and counting were split, so
  // the moving side built from the picture alone without knowing what had to be moved.
  // #854 renamed the merged skill back to pro-figma (moving and comparing stay one bundle).
  // The old installed pro-figma-verify is removed by the Cursor adapter as a "pro-* not in the source".
  // pro-analyze, pro-plan and pro-implement were deleted in #849 — they overlapped superpowers (brainstorming, writing-plans, executing-plans)
  // pro-note and pro-build were deleted in #853 — zero records had accumulated, and agents pick build commands from marker files directly
  // extras' pro-architecture-consult was renamed to pro-code-consult in #912 — old config keys and install markers are read as fallbacks
  //
  // This list holds only "what must exist". New skills need no change here,
  // **but when deleting a skill, remove it here too** — #582 missed this and develop stayed broken.
  const expected = [
    "pro-changelog-deploy", "pro-commit",
    "pro-figma", "pro-github", "pro-init-worktree",
    "pro-report", "pro-review", "pro-skill-creator",
    "pro-ssh", "pro-testcase",
  ];
  for (const s of expected) {
    assert.ok(existsSync(join(ROOT, "skills", s, "SKILL.md")), `missing: skills/${s}/SKILL.md`);
  }
});

test("no leftover cassiiopeia:suh- command notation in active docs/code", () => {
  const hits = findFiles("cassiiopeia:suh-", DOC_CODE);
  assert.deepEqual(hits, [], `cassiiopeia:suh- leftovers:\n${hits.join("\n")}`);
});

test("no leftover lowercase plugin name cassiiopeia (uppercase org name allowed)", () => {
  // Targets manifests, IDE adapters and active docs. Uppercase Cassiiopeia (org name) passes thanks to case sensitivity.
  // The docs site domain (cassiiopeia.github.io) is allowed, since it is GitHub Pages' official lowercase host.
  const hits = findFiles("cassiiopeia", [
    ".claude-plugin/", ".codex-plugin/", ".agents/", ".cursor/",
    "gemini-extension.json", "src/", "ext:.md",
  ], ["cassiiopeia.github.io"]);
  assert.deepEqual(hits, [], `lowercase cassiiopeia leftovers:\n${hits.join("\n")}`);
});

test("no leftover @suh-lab triggers (the external bot signature Guide by SUH-LAB is separate)", () => {
  const hits = findFiles("@suh-lab", ["ext:.md", ".github/"]);
  assert.deepEqual(hits, [], `@suh-lab leftovers:\n${hits.join("\n")}`);
});

// ── Preserved items (no substitution) still alive — guards against over-substitution regressions ──

// The suh-logger preservation check was dropped along with its target pro-spring-test, deleted in #582.
// Its purpose, guarding against over-substitution, is carried on by the 'Guide by SUH-LAB' check below.

test("preserved: the external bot signature 'Guide by SUH-LAB' match is alive", () => {
  const hits = findFiles("Guide by SUH-LAB", [".github/"]);
  assert.ok(hits.length > 0, "'Guide by SUH-LAB' signature match is gone (build trigger broken)");
});

test("skill count and list match across folders ↔ manifests ↔ README and CLAUDE.md", () => {
  // Actual folders (only those with SKILL.md)
  const listSkills = (dir, prefix) => readdirSync(join(ROOT, dir))
    .filter((d) => d.startsWith(prefix) && existsSync(join(ROOT, dir, d, "SKILL.md"))).sort();
  const core = listSkills("skills", "pro-");
  const extras = listSkills("plugins/projectops-extras/skills", "pro-");
  const read = (path) => readFileSync(join(ROOT, path), "utf-8");
  const expectIn = (path, needles) => {
    const text = read(path);
    const missing = needles.filter((n) => !text.includes(n));
    assert.deepEqual(missing, [], `missing from ${path}`);
  };

  // Count in the manifest descriptions
  const market = JSON.parse(read(".claude-plugin/marketplace.json")).plugins;
  const descriptionOf = (name) => market.find((p) => p.name === name).description;
  assert.ok(descriptionOf("projectops").includes(`(${core.length} skills)`), "marketplace projectops count");
  assert.ok(descriptionOf("projectops-extras").includes(`(${extras.length} skills)`), "marketplace extras count");
  for (const manifest of [".claude-plugin/plugin.json", ".codex-plugin/plugin.json"]) {
    assert.ok(JSON.parse(read(manifest)).description.includes(`(${core.length} skills)`), `${manifest} count`);
  }

  // Count notation and list in the docs
  expectIn("README.md", [`**Agent Skills** (${core.length})`, `See all ${core.length} Agent Skills`,
    `${core.length} skills give consistent results`, ...[...core, ...extras].map((s) => `\`/${s}\``)]);
  // Same line in translations (skill count in the comparison table)
  expectIn("docs/i18n/README.ko.md", [`${core.length}종 Skills로`]);
  expectIn("docs/i18n/README.zh-CN.md", [`${core.length} 个 Skills`]);
  expectIn("docs/i18n/README.ja.md", [`${core.length} 種の Skills`]);
  expectIn("CLAUDE.md", [`core ${core.length} + extras ${extras.length}`,
    ...[...core, ...extras].map((s) => `| \`${s.slice("pro-".length)}\` |`)]);
  expectIn("docs/README.md", [`쓰는 ${core.length}종 Skill`]);
  expectIn("docs/en/readme.md", [`The ${core.length} Skills used in`]);
  expectIn("docs/SKILLS.md", [`Skill 전체 목록 (${core.length}종)`, ...core.map((s) => `### \`/${s}\``)]);
  expectIn("plugins/projectops-extras/README.md", extras.map((s) => `| \`${s}\` |`));
});
