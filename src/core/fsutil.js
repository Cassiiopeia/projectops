// Shared filesystem utilities (byte copy that keeps LF). Text is copied as is to keep the original line endings.
import {
  copyFileSync as copyFileBytes, existsSync, lstatSync, readFileSync, readlinkSync, symlinkSync,
  writeFileSync, mkdirSync, readdirSync, rmSync,
} from "node:fs";
import { dirname, join } from "node:path";

export const exists = (p) => existsSync(p);
export const readText = (p) => readFileSync(p, "utf8");

export function writeText(p, s) {
  mkdirSync(dirname(p), { recursive: true });
  writeFileSync(p, s);
}

// Copy a single file (creates parent directories, byte for byte)
export function copyFileSync(src, dst) {
  mkdirSync(dirname(dst), { recursive: true });
  copyFileBytes(src, dst);
}

// Recursive copy of files, folders and symlinks. Avoids the built-in fs recursive copy (cp-sync):
// on Windows with Node 22+, a non-ASCII (e.g. Korean) path kills the process with no message.
export function copyPathSync(src, dst, filter) {
  if (filter && !filter(src)) return;
  const stat = lstatSync(src);
  if (stat.isSymbolicLink()) {
    rmSync(dst, { force: true });
    symlinkSync(readlinkSync(src), dst);
  } else if (stat.isDirectory()) {
    mkdirSync(dst, { recursive: true });
    for (const name of readdirSync(src)) copyPathSync(join(src, name), join(dst, name), filter);
  } else {
    copyFileSync(src, dst);
  }
}

// Recursive directory copy (contents go under dst)
export function copyDirSync(src, dst, { filter } = {}) {
  mkdirSync(dst, { recursive: true });
  copyPathSync(src, dst, filter);
}

// Delete a file/folder (harmless if missing)
export function remove(p) {
  rmSync(p, { recursive: true, force: true });
}

// Names of .yaml/.yml files directly under a directory. Subfolders excluded.
// Sort: group by extension first (.yaml before .yml), alphabetical within each group.
// (Iteration order sets the key order of the version.yml deploy block — keeps output byte-identical to existing installs)
export function listYamlFiles(dir) {
  if (!existsSync(dir)) return [];
  const names = readdirSync(dir, { withFileTypes: true })
    .filter((e) => e.isFile() && /\.(ya?ml)$/.test(e.name))
    .map((e) => e.name);
  const yaml = names.filter((n) => n.endsWith(".yaml")).sort();
  const yml = names.filter((n) => n.endsWith(".yml")).sort();
  return [...yaml, ...yml];
}
