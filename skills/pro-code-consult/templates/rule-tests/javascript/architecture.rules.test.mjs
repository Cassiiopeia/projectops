// Architecture rule test: docs/architecture/rules/<id>.rule violations <-> <id>.allow
// Edit rules in the rules folder (this file is a pro-code-consult template — verdict logic only). Run: node --test
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// Excluded folders (same list as the other stack templates)
const SKIPPED_DIRECTORY_NAMES = new Set([
  '.git', 'build', 'dist', 'node_modules', '.dart_tool', 'Pods', '.gradle',
  'venv', '.venv', '__pycache__', '.next', 'out', 'target', '.idea',
]);
const LIST_KEYS = new Set(['paths', 'extensions', 'exclude']);
// Rule files themselves are always excluded
const ALWAYS_EXCLUDED_PREFIX = 'docs/architecture/';

/** Search upward from the current folder for docs/architecture/rules (works from monorepo subfolders) */
function findRulesDirectory(start) {
  for (let directory = start; ; directory = path.dirname(directory)) {
    const candidate = path.join(directory, 'docs', 'architecture', 'rules');
    if (fs.existsSync(candidate) && fs.statSync(candidate).isDirectory()) return candidate;
    if (path.dirname(directory) === directory) return null;
  }
}

/** key=value (split on the first = only, # comments) > rule */
function parseRule(file) {
  const rule = { id: path.basename(file, '.rule'), pattern: '', paths: [], extensions: [], exclude: [] };
  for (const raw of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) continue;
    const index = line.indexOf('=');
    const key = line.slice(0, index).trim();
    const value = line.slice(index + 1).trim();
    if (LIST_KEYS.has(key)) rule[key] = value.split(',').map((item) => item.trim()).filter(Boolean);
    else if (key === 'pattern') rule.pattern = value;
  }
  return rule;
}

function readAllowEntries(file) {
  if (!fs.existsSync(file)) return [];
  return fs.readFileSync(file, 'utf8').split(/\r?\n/).map((line) => line.trim())
    .filter((line) => line && !line.startsWith('#'));
}

function* walk(directory) {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (!SKIPPED_DIRECTORY_NAMES.has(entry.name)) yield* walk(path.join(directory, entry.name));
    } else if (entry.isFile()) {
      yield path.join(directory, entry.name);
    }
  }
}

function findViolatingFiles(repositoryRoot, rule) {
  const pattern = new RegExp(rule.pattern, 'm');
  const violating = new Set();
  for (const prefix of rule.paths.length ? rule.paths : ['']) {
    const base = path.join(repositoryRoot, prefix);
    if (!fs.existsSync(base)) continue;
    const candidates = fs.statSync(base).isFile() ? [base] : [...walk(base)];
    for (const absolute of candidates) {
      const relative = path.relative(repositoryRoot, absolute).split(path.sep).join('/');
      if (relative.startsWith(ALWAYS_EXCLUDED_PREFIX) || rule.exclude.some((excluded) => relative.startsWith(excluded))) continue;
      if (rule.extensions.length && !rule.extensions.some((ext) => relative.endsWith(ext))) continue;
      if (pattern.test(fs.readFileSync(absolute).toString('utf8'))) violating.add(relative);
    }
  }
  return [...violating].sort();
}

const rulesDirectory = findRulesDirectory(path.dirname(fileURLToPath(import.meta.url)));
const ruleFiles = rulesDirectory
  ? fs.readdirSync(rulesDirectory).filter((name) => name.endsWith('.rule')).sort()
  : [];

for (const ruleFileName of ruleFiles) {
  test(`architecture rule: ${ruleFileName}`, () => {
    const repositoryRoot = path.resolve(rulesDirectory, '..', '..', '..');
    const rule = parseRule(path.join(rulesDirectory, ruleFileName));
    assert.ok(rule.pattern, `${ruleFileName}: missing pattern key`);
    const violating = new Set(findViolatingFiles(repositoryRoot, rule));
    const allowed = new Set(readAllowEntries(path.join(rulesDirectory, `${rule.id}.allow`)));

    // New violations (files not in the freeze list) > fix the code
    const newViolations = [...violating].filter((file) => !allowed.has(file)).sort();
    assert.deepEqual(newViolations, [], `[${rule.id}] new violations: ${newViolations.join(', ')}`);
    // Fixed entries > remove them from the freeze list (keeps the list from loosening)
    const fixedEntries = [...allowed].filter((file) => !violating.has(file)).sort();
    assert.deepEqual(fixedEntries, [], `[${rule.id}] fixed, so remove from ${rule.id}.allow: ${fixedEntries.join(', ')}`);
  });
}
