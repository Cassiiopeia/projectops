import { test } from "node:test";
import assert from "node:assert/strict";
import { ADAPTERS, adapterById } from "../src/core/ide/registry.js";
import { assertAdapter } from "../src/core/ide/adapter.js";
import { collectStatuses, formatStatuses, runSkills } from "../src/commands/skills.js";
import { mkdtempSync, rmSync, mkdirSync, writeFileSync, existsSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// stub io — which/run/home/log 제어. run 호출은 calls에 기록.
function stubIo({ present = {}, runs = {}, home } = {}) {
  const calls = [], logs = [];
  return {
    calls, logs,
    which: (c) => (present[c] ? `/usr/bin/${c}` : null),
    run: (c, a = []) => {
      const key = [c, ...a].join(" ");
      calls.push(key);
      for (const k of Object.keys(runs)) if (key.includes(k)) return runs[k];
      return { code: 0, stdout: "", stderr: "" };
    },
    home: () => home || "/home/x",
    log: (m) => logs.push(m),
  };
}

// ── 레지스트리 계약 ──
test("모든 어댑터가 계약(id/label/detect/apply/remove)을 만족", () => {
  for (const a of ADAPTERS) assertAdapter(a);
  // id 유일성
  const ids = ADAPTERS.map((a) => a.id);
  assert.equal(new Set(ids).size, ids.length);
});

test("registry는 order 오름차순 정렬", () => {
  const orders = ADAPTERS.map((a) => a.order ?? 100);
  const sorted = [...orders].sort((x, y) => x - y);
  assert.deepEqual(orders, sorted);
});

test("adapterById 조회", () => {
  assert.equal(adapterById("claude").label, "Claude Code");
  assert.equal(adapterById("없음"), null);
});

// ── claude 어댑터 ──
test("claude: CLI 없으면 cliMissing", () => {
  assert.equal(adapterById("claude").detect(stubIo({})).cliMissing, true);
});

test("claude: 미설치 감지 → apply가 install 경로", () => {
  const io = stubIo({ present: { claude: 1 } });
  adapterById("claude").apply(io);
  assert.ok(io.calls.some((c) => c.includes("marketplace add Cassiiopeia/projectops")));
  assert.ok(io.calls.some((c) => c.includes("plugin install projectops@projectops-marketplace")));
});

test("claude: 설치 감지 → apply가 update 경로", () => {
  const io = stubIo({
    present: { claude: 1 },
    runs: { "plugin list": { code: 0, stdout: JSON.stringify([{ name: "projectops@projectops-marketplace", scope: "user", version: "3.0.1" }]), stderr: "" } },
  });
  adapterById("claude").apply(io);
  assert.ok(io.calls.some((c) => c.includes("plugin update")));
});

// ── cursor 어댑터 (실제 복사) ──
test("cursor: skills/ 복사 + meta.json 기록", () => {
  const home = mkdtempSync(join(tmpdir(), "cuh-"));
  const src = mkdtempSync(join(tmpdir(), "cus-"));
  try {
    mkdirSync(join(src, "analyze"), { recursive: true });
    writeFileSync(join(src, "analyze/SKILL.md"), "x");
    const io = stubIo({ home });
    const ok = adapterById("cursor").apply(io, { sourceSkillsDir: src, templateVersion: "9.9.9" });
    assert.equal(ok, true);
    assert.ok(existsSync(join(home, ".cursor/skills/analyze/SKILL.md")));
    const meta = JSON.parse(readFileSync(join(home, ".cursor/skills/cursor-skills-meta.json"), "utf8"));
    assert.equal(meta.version, "9.9.9");
    // detect가 설치 인식
    assert.equal(adapterById("cursor").detect(io).installed, true);
    // remove (선별 삭제 — 소스 폴더명 기준. 이 테스트 폴더엔 analyze+meta만 있어 폴더가 비고 제거됨)
    assert.equal(adapterById("cursor").remove(io, { sourceSkillsDir: src }), true);
    assert.equal(existsSync(join(home, ".cursor/skills")), false);
  } finally { rmSync(home, { recursive: true, force: true }); rmSync(src, { recursive: true, force: true }); }
});

// projectops 자신을 검사하는 테스트는 사용자 홈으로 나가면 안 된다 (#591).
// skills/ 를 통째로 복사하므로 여기서 거르지 않으면 그대로 쌓인다.
test("cursor: 테스트 코드는 복사하지 않는다", () => {
  const home = mkdtempSync(join(tmpdir(), "cuh-"));
  const src = mkdtempSync(join(tmpdir(), "cus-"));
  try {
    mkdirSync(join(src, "pro-thing/tests"), { recursive: true });
    mkdirSync(join(src, "pro-thing/scripts"), { recursive: true });
    writeFileSync(join(src, "pro-thing/SKILL.md"), "x");
    writeFileSync(join(src, "pro-thing/scripts/thing_cli.py"), "x");
    writeFileSync(join(src, "pro-thing/tests/test_thing.py"), "x");
    writeFileSync(join(src, "conftest.py"), "x");

    const io = stubIo({ home });
    assert.equal(adapterById("cursor").apply(io, { sourceSkillsDir: src, templateVersion: "9.9.9" }), true);

    const at = (r) => join(home, ".cursor/skills", r);
    // 스킬을 쓰는 데 필요한 것은 그대로 간다
    assert.ok(existsSync(at("pro-thing/SKILL.md")));
    assert.ok(existsSync(at("pro-thing/scripts/thing_cli.py")));
    // 이 저장소 자기 테스트는 나가지 않는다
    assert.equal(existsSync(at("pro-thing/tests")), false);
    assert.equal(existsSync(at("pro-thing/tests/test_thing.py")), false);
    assert.equal(existsSync(at("conftest.py")), false);
  } finally { rmSync(home, { recursive: true, force: true }); rmSync(src, { recursive: true, force: true }); }
});

// ── gemini/codex ──
test("gemini: update 실패 시 install 폴백", () => {
  const io = stubIo({ present: { gemini: 1 }, runs: { "extensions update": { code: 1, stdout: "", stderr: "" } } });
  adapterById("gemini").apply(io);
  assert.ok(io.calls.some((c) => c.includes("extensions install")));
});

test("codex: CLI 없고 native도 없으면 cliMissing", () => {
  const home = mkdtempSync(join(tmpdir(), "coh-"));
  try {
    assert.equal(adapterById("codex").detect(stubIo({ home })).cliMissing, true);
  } finally { rmSync(home, { recursive: true, force: true }); }
});

test("codex: native symlink 존재 시 installed", () => {
  const home = mkdtempSync(join(tmpdir(), "co2-"));
  try {
    mkdirSync(join(home, ".agents/skills/projectops"), { recursive: true });
    assert.equal(adapterById("codex").detect(stubIo({ home })).installed, true);
  } finally { rmSync(home, { recursive: true, force: true }); }
});

// ── pi + harness ──
test("pi: 미설치 → install 호출", () => {
  const io = stubIo({ present: { pi: 1 } }); // pi list 빈 출력 → 미설치
  adapterById("pi").apply(io);
  assert.ok(io.calls.some((c) => c.includes("install https://github.com/Cassiiopeia/projectops")));
});

test("pi-harness: settings.json extensions 배열 add/remove", () => {
  const home = mkdtempSync(join(tmpdir(), "pih-"));
  try {
    // loader 파일 + settings 준비
    const loaderDir = join(home, ".pi/agent/git/github.com/Cassiiopeia/projectops/harness");
    mkdirSync(loaderDir, { recursive: true });
    writeFileSync(join(loaderDir, "harness-loader.ts"), "//");
    const settings = join(home, ".pi/agent/settings.json");
    writeFileSync(settings, "{}");
    const io = stubIo({ present: { pi: 1 }, home });
    // 활성화
    assert.equal(adapterById("pi-harness").apply(io), true);
    let s = JSON.parse(readFileSync(settings, "utf8"));
    assert.equal(s.extensions.length, 1);
    assert.ok(s.extensions[0].includes("harness-loader.ts"));
    // detect
    assert.equal(adapterById("pi-harness").detect(io).installed, true);
    // 해제
    assert.equal(adapterById("pi-harness").remove(io), true);
    s = JSON.parse(readFileSync(settings, "utf8"));
    assert.equal(s.extensions.length, 0);
  } finally { rmSync(home, { recursive: true, force: true }); }
});

test("pi-harness: loader 없으면 optional 항목이 상태 목록에서 제외", () => {
  const io = stubIo({ present: { pi: 1 } }); // loader 파일 없음
  const rows = collectStatuses(io);
  assert.equal(rows.some((r) => r.adapter.id === "pi-harness"), false);
});

// ── 오케스트레이터 ──
test("runSkills 비대화형: 감지된 어댑터에 apply 순차 실행", async () => {
  const io = stubIo({ present: { claude: 1 } });
  const code = await runSkills({ io, interactive: false, templateVersion: "9.9.9" });
  assert.equal(code, 0);
  assert.ok(io.calls.some((c) => c.includes("plugin install")));
});

test("runSkills 대화형: action=apply + targets 선택 → 해당 어댑터만 apply", async () => {
  const io = stubIo({ present: { claude: 1, gemini: 1 } });
  const ui = {
    selectAction: async () => "apply",
    selectTargets: async () => ["gemini"], // claude 제외, gemini만
  };
  await runSkills({ io, interactive: true, ui });
  assert.ok(io.calls.some((c) => c.includes("gemini")));
  assert.ok(!io.calls.some((c) => c.includes("plugin install projectops"))); // claude 미실행
});

test("runSkills 대화형: action=skip → 변경 동작(install/update/uninstall) 없음", async () => {
  const io = stubIo({ present: { claude: 1 } });
  const ui = { selectAction: async () => "skip", selectTargets: async () => [] };
  await runSkills({ io, interactive: true, ui });
  // detect용 'plugin list'는 허용, 변경성 명령만 없어야 함
  assert.ok(!io.calls.some((c) => /install|update|uninstall/.test(c)));
});

test("formatStatuses: 설치 버전이 템플릿과 같으면 최신 태그", () => {
  const rows = [{ adapter: { label: "Claude Code" }, status: { installed: true, version: "9.9.9", cliMissing: false } }];
  const out = formatStatuses(rows, "9.9.9");
  assert.ok(out[0].includes("✓ 최신"));
});
