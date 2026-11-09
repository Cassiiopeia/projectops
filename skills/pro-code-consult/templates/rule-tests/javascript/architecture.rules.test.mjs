// 아키텍처 규칙 테스트: docs/architecture/rules/<id>.rule 위반 <-> <id>.allow 대조
// 규칙은 rules 폴더에서 고친다 (이 파일은 pro-code-consult 템플릿 — 판정 로직만). 실행: node --test
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// 탐색 제외 폴더 (다른 스택 템플릿과 같은 목록)
const SKIPPED_DIRECTORY_NAMES = new Set([
  '.git', 'build', 'dist', 'node_modules', '.dart_tool', 'Pods', '.gradle',
  'venv', '.venv', '__pycache__', '.next', 'out', 'target', '.idea',
]);
const LIST_KEYS = new Set(['paths', 'extensions', 'exclude']);
// 규칙 파일 자신은 판정 대상에서 늘 제외
const ALWAYS_EXCLUDED_PREFIX = 'docs/architecture/';

/** 현재 폴더부터 위로 docs/architecture/rules 탐색 (모노레포 서브폴더에서도 동작) */
function findRulesDirectory(start) {
  for (let directory = start; ; directory = path.dirname(directory)) {
    const candidate = path.join(directory, 'docs', 'architecture', 'rules');
    if (fs.existsSync(candidate) && fs.statSync(candidate).isDirectory()) return candidate;
    if (path.dirname(directory) === directory) return null;
  }
}

/** key=value (첫 = 에서만 자름, # 주석) > 규칙 */
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
    assert.ok(rule.pattern, `${ruleFileName}: pattern 키가 없다`);
    const violating = new Set(findViolatingFiles(repositoryRoot, rule));
    const allowed = new Set(readAllowEntries(path.join(rulesDirectory, `${rule.id}.allow`)));

    // 새 위반 (동결 목록에 없는 파일) > 코드를 고친다
    const newViolations = [...violating].filter((file) => !allowed.has(file)).sort();
    assert.deepEqual(newViolations, [], `[${rule.id}] 새 위반: ${newViolations.join(', ')}`);
    // 고쳐진 항목 > 동결 목록에서 지운다 (목록이 느슨해지지 않게)
    const fixedEntries = [...allowed].filter((file) => !violating.has(file)).sort();
    assert.deepEqual(fixedEntries, [], `[${rule.id}] 고쳐졌으니 ${rule.id}.allow 에서 지운다: ${fixedEntries.join(', ')}`);
  });
}
