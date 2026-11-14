#!/usr/bin/env node
// 옵션 레퍼런스 생성: src/core/options-schema.js > docs/en/cli.md · docs/CLI.md 의 생성 블록
//
//   node scripts/build_options_reference.mjs          # 생성 블록 다시 쓰기
//   node scripts/build_options_reference.mjs --check  # 쓰지 않고 최신인지만 (아니면 종료코드 1)
//
// 원본은 options-schema.js 하나. 생성 블록은 손으로 고치지 않는다 (options-schema.js 수정 후 실행).
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { buildSchema } from "../src/core/options-schema.js";

const repositoryRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
// 블록을 넣을 문서 (영어·한국어 짝)
const targetDocPaths = ["docs/en/cli.md", "docs/CLI.md"];
const blockStartMarker = "<!-- generated: options -->";
const blockEndMarker = "<!-- /generated -->";

// 표 칸 정리 (파이프 이스케이프, 줄바꿈 제거)
function toTableCell(text) {
  return String(text ?? "").replace(/\|/g, "\\|").replace(/\n/g, " ");
}

function toCodeList(values) {
  return values.map((value) => `\`${value}\``).join(" ");
}

function toDefaultText(defaultValue) {
  if (defaultValue === undefined) return "";
  if (Array.isArray(defaultValue)) return defaultValue.length ? toCodeList(defaultValue) : "`[]`";
  return typeof defaultValue === "string" ? defaultValue : `\`${JSON.stringify(defaultValue)}\``;
}

// 값·기본값 칸: "values: a b; default: x"
function toValuesAndDefaultCell(entry) {
  const parts = [];
  if (entry.values?.length) parts.push(`values: ${toCodeList(entry.values)}`);
  const defaultText = toDefaultText(entry.default);
  if (defaultText) parts.push(`default: ${defaultText}`);
  return toTableCell(parts.join("; "));
}

function toFlagNameCell(flagEntry) {
  const names = [...(flagEntry.aliases ?? [flagEntry.alias]), flagEntry.flag + (flagEntry.value ? ` ${flagEntry.value}` : ""), flagEntry.negation]
    .filter(Boolean)
    .map((name) => `\`${name}\``);
  return names.join(", ");
}

// 플래그 표 > version.yml 키 표
function renderOptionsReference(schema) {
  const lines = [
    blockStartMarker,
    "<!-- Do not edit by hand. Source: src/core/options-schema.js. Rebuild: node scripts/build_options_reference.mjs -->",
    "",
    "### CLI flags",
    "",
    "| Flag | `version.yml` key | Values / default | Description |",
    "|---|---|---|---|",
  ];
  for (const flagEntry of schema.flags) {
    const description = flagEntry.deprecated ? `(deprecated) ${flagEntry.deprecated}` : flagEntry.description;
    const versionYmlKey = flagEntry.versionYml ? `\`${flagEntry.versionYml}\`` : "";
    lines.push(`| ${toFlagNameCell(flagEntry)} | ${versionYmlKey} | ${toValuesAndDefaultCell(flagEntry)} | ${toTableCell(description)} |`);
  }
  lines.push(
    "",
    "### `version.yml` keys",
    "",
    "| Key | Type | Values / default | Set by | Description |",
    "|---|---|---|---|---|",
  );
  for (const keyEntry of schema.versionYml) {
    lines.push(`| \`${keyEntry.path}\` | ${toTableCell(keyEntry.type)} | ${toValuesAndDefaultCell(keyEntry)} | ${toTableCell(keyEntry.edit)} | ${toTableCell(keyEntry.description)} |`);
  }
  lines.push("", blockEndMarker);
  return lines.join("\n");
}

// 문서 안 생성 블록 교체 (마커 없으면 오류)
function replaceGeneratedBlock(documentText, generatedBlock, documentPath) {
  const startIndex = documentText.indexOf(blockStartMarker);
  const endIndex = documentText.indexOf(blockEndMarker);
  if (startIndex < 0 || endIndex < startIndex) {
    throw new Error(`[options reference] markers missing in ${documentPath}`);
  }
  return documentText.slice(0, startIndex) + generatedBlock + documentText.slice(endIndex + blockEndMarker.length);
}

const isCheckMode = process.argv.includes("--check");
const generatedBlock = renderOptionsReference(buildSchema());
const staleDocPaths = [];
for (const documentPath of targetDocPaths) {
  const absolutePath = join(repositoryRoot, documentPath);
  const currentText = readFileSync(absolutePath, "utf8");
  const nextText = replaceGeneratedBlock(currentText, generatedBlock, documentPath);
  if (nextText === currentText) continue;
  staleDocPaths.push(documentPath);
  if (!isCheckMode) writeFileSync(absolutePath, nextText);
}

if (isCheckMode && staleDocPaths.length) {
  console.error(`[options reference] out of date: ${staleDocPaths.join(", ")}`);
  console.error("Run: node scripts/build_options_reference.mjs");
  process.exit(1);
}
console.log(staleDocPaths.length ? `[options reference] updated: ${staleDocPaths.join(", ")}` : "[options reference] up to date");
