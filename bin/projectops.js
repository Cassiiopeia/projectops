#!/usr/bin/env node
// projectops CLI entry — passes argv to run() in src/index.js.
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { pathToFileURL } from "node:url";

const [nodeMajor, nodeMinor] = process.versions.node.split(".").map(Number);
if (nodeMajor < 20 || (nodeMajor === 20 && nodeMinor < 12)) {
  console.error(`Node.js 20.12 or later is required (current: ${process.versions.node})`);
  process.exit(1);
}

const here = dirname(fileURLToPath(import.meta.url));
const indexPath = join(here, "..", "src", "index.js");
const { run } = await import(pathToFileURL(indexPath).href);

const code = await run(process.argv.slice(2), { cwd: process.cwd() });
// When stdout is a pipe, writes are async, so exiting right away cuts large output (--mode options --json) near 8KB.
// The callback of an empty write fires after all earlier writes are flushed, so exit there.
process.stdout.write("", () => process.exit(code));
