#!/usr/bin/env node
// Build project type outputs from src/core/project-types.json (#1244): byte copies + generated doc blocks
//
//   node scripts/build_project_types.mjs          # rewrite copies and blocks
//   node scripts/build_project_types.mjs --check  # check freshness only, no writes (exit 1 if stale)
//
// The registry is the only source. Never hand-edit the copies or the blocks between
// <!-- generated: project-types:<name> --> and <!-- /generated -->.
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { PROJECT_TYPES } from "../src/core/project-types.js";

const repositoryRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const SOURCE_PATH = "src/core/project-types.json";
// Copies 2: user repos (copied with .github/config, read by .github/scripts/project_types.py) · skills (scripts/common)
const COPY_PATHS = [".github/config/project-types.json", "scripts/common/project_types.json"];
const BLOCK_END_MARKER = "<!-- /generated -->";

const code = (text) => `\`${text}\``;

// "`flutter`, `spring`, ..." (separator per document language)
function renderTypeList(separator) {
  return PROJECT_TYPES.map((type) => code(type.id)).join(separator);
}

// Whole markdown table. Markers sit outside the table (GitHub ends a table at the first line that does not start with "|").
// The header and separator rows already in the block are kept, so each document keeps its own language
function renderTable(rows) {
  return (currentBlockText) => {
    const [headerRow, separatorRow] = currentBlockText.split("\n").filter((line) => line.startsWith("|"));
    if (!headerRow || !separatorRow) throw new Error("[project types] table block needs its header and separator rows");
    return `\n${[headerRow, separatorRow, ...rows].join("\n")}\n`;
  };
}

// CLAUDE.md table rows: Type | Description | Version sync file
function renderTypeTableRows() {
  return PROJECT_TYPES.map((type) => `| ${code(type.id)} | ${type.description} | ${code(type.version.display)} |`);
}

// Version-control doc rows: Type | Version file | Version location
function renderVersionFileRows() {
  return PROJECT_TYPES.map((type) => {
    const location = type.version.example === "-" ? "-" : code(type.version.example);
    return `| ${code(type.id)} | ${code(type.version.display)} | ${location} |`;
  });
}

// package.json rule > " + `a` or `b` dependency, not `c`"
function describePackageRule(rule) {
  if (!rule) return "";
  const required = [...(rule.requires_all || []).map(code)];
  const anyOf = [...(rule.requires_any || []).map(code), ...(rule.requires_any_prefix || []).map((prefix) => code(`${prefix}*`))];
  if (anyOf.length) required.push(anyOf.join(" or "));
  const excluded = [...(rule.excludes_any || []).map(code), ...(rule.excludes_any_prefix || []).map((prefix) => code(`${prefix}*`))];
  return ` + ${required.join(" and ")} dependency${excluded.length ? `, no ${excluded.join(" or ")}` : ""}`;
}

// Detection doc rows: Type | Required files | Secondary checks
function renderDetectionRows() {
  return PROJECT_TYPES.map((type) => {
    const markers = type.detect.markers.length ? type.detect.markers.map(code).join(" or ") : "Matches no other type";
    const fallback = type.detect.fallback_only ? " (only when no other type matches)" : "";
    return `| **${type.label}** (${code(type.id)}) | ${markers}${describePackageRule(type.detect.package_json)}${fallback} | ${type.detect.secondary} |`;
  });
}

// Document > generated blocks it holds (block name > renderer; inline blocks keep surrounding text on the same line)
const DOCUMENT_BLOCKS = [
  { path: "README.md", blocks: { "types-list": () => renderTypeList(", ") } },
  { path: "docs/i18n/README.ko.md", blocks: { "types-list": () => renderTypeList(", ") } },
  { path: "docs/i18n/README.ja.md", blocks: { "types-list": () => renderTypeList("、") } },
  { path: "docs/i18n/README.zh-CN.md", blocks: { "types-list": () => renderTypeList("、") } },
  { path: "CLAUDE.md", blocks: { "types-table": () => renderTable(renderTypeTableRows()) } },
  { path: "docs/en/version-control.md", blocks: { "version-files": () => renderTable(renderVersionFileRows()) } },
  { path: "docs/VERSION-CONTROL.md", blocks: { "version-files": () => renderTable(renderVersionFileRows()) } },
  { path: "skills/references/project-detection.md", blocks: { detection: () => renderTable(renderDetectionRows()) } },
];

// Replace one named block (error if its markers are missing)
function replaceBlock(documentText, blockName, content, documentPath) {
  const startMarker = `<!-- generated: project-types:${blockName} -->`;
  const startIndex = documentText.indexOf(startMarker);
  const endIndex = documentText.indexOf(BLOCK_END_MARKER, startIndex);
  if (startIndex < 0 || endIndex < 0) throw new Error(`[project types] markers for "${blockName}" missing in ${documentPath}`);
  const currentBlockText = documentText.slice(startIndex + startMarker.length, endIndex);
  const nextBlockText = typeof content === "function" ? content(currentBlockText) : content;
  return documentText.slice(0, startIndex + startMarker.length) + nextBlockText + documentText.slice(endIndex);
}

const isCheckMode = process.argv.includes("--check");
const stalePaths = [];
// Write only when changed; in check mode record and leave the file alone
function syncFile(relativePath, nextText) {
  const absolutePath = join(repositoryRoot, relativePath);
  const currentText = existsSync(absolutePath) ? readFileSync(absolutePath, "utf8") : null;
  if (currentText === nextText) return;
  stalePaths.push(relativePath);
  if (!isCheckMode) writeFileSync(absolutePath, nextText);
}

// Byte copies of the source
const sourceText = readFileSync(join(repositoryRoot, SOURCE_PATH), "utf8");
for (const copyPath of COPY_PATHS) syncFile(copyPath, sourceText);

// Doc blocks
for (const document of DOCUMENT_BLOCKS) {
  let text = readFileSync(join(repositoryRoot, document.path), "utf8");
  for (const [blockName, render] of Object.entries(document.blocks)) text = replaceBlock(text, blockName, render(), document.path);
  syncFile(document.path, text);
}

if (isCheckMode && stalePaths.length) {
  console.error(`[project types] out of date: ${stalePaths.join(", ")}`);
  console.error("Run: node scripts/build_project_types.mjs");
  process.exit(1);
}
console.log(stalePaths.length ? `[project types] updated: ${stalePaths.join(", ")}` : "[project types] up to date");
