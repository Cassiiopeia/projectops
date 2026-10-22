import { test } from "node:test";
import assert from "node:assert/strict";
import { ADAPTERS, adapterById } from "../src/core/ide/registry.js";
import { assertAdapter } from "../src/core/ide/adapter.js";
import { SHARED_SCRIPTS_DEV_ONLY } from "../src/core/ide/skills-copy.js";
import { collectStatuses, formatStatuses, runSkills } from "../src/commands/skills.js";
import { mkdtempSync, rmSync, mkdirSync, writeFileSync, existsSync, readFileSync, readdirSync } from "node:fs";
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
// 복사는 overlay 라 덮어쓰기만 하면 **폐기한 스킬이 남의 컴퓨터에 영영 남는다.**
// util 복사가 같은 함정에 빠졌던 자리다 (#500). 스킬을 합치거나 지울 때마다
// 기존 설치본에 구 스킬이 남아 계속 잡히면 "지웠는데 왜 뜨나"가 된다 (#619).
test("cursor: 소스에서 사라진 우리 스킬은 설치본에서도 지운다", () => {
  const home = mkdtempSync(join(tmpdir(), "cuh-"));
  const src = mkdtempSync(join(tmpdir(), "cus-"));
  try {
    const dest = join(home, ".cursor/skills");
    // 이미 깔려 있는 상태를 만든다 — 우리 것 둘 + 남의 것 하나
    mkdirSync(join(dest, "pro-old/scripts"), { recursive: true });
    writeFileSync(join(dest, "pro-old/SKILL.md"), "x");
    mkdirSync(join(dest, "suh-ancient"), { recursive: true });
    writeFileSync(join(dest, "suh-ancient/SKILL.md"), "x");
    mkdirSync(join(dest, "somansa-tools"), { recursive: true });
    writeFileSync(join(dest, "somansa-tools/SKILL.md"), "x");

    // 새 소스에는 pro-new 만 있다
    mkdirSync(join(src, "pro-new"), { recursive: true });
    writeFileSync(join(src, "pro-new/SKILL.md"), "x");

    const io = stubIo({ home });
    assert.equal(adapterById("cursor").apply(io, { sourceSkillsDir: src, templateVersion: "9.9.9" }), true);

    const at = (r) => join(dest, r);
    assert.ok(existsSync(at("pro-new/SKILL.md")), "새 스킬이 깔려야 한다");
    // 폐기된 우리 스킬은 사라진다 (옛 접두사도 함께)
    assert.equal(existsSync(at("pro-old")), false, "폐기된 pro- 스킬이 남았다");
    assert.equal(existsSync(at("suh-ancient")), false, "폐기된 suh- 스킬이 남았다");
    // 남의 스킬은 건드리지 않는다
    assert.ok(existsSync(at("somansa-tools/SKILL.md")), "남의 스킬을 지웠다");
  } finally { rmSync(home, { recursive: true, force: true }); rmSync(src, { recursive: true, force: true }); }
});

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

// 공용 파이썬은 런타임 항목만 (#988) — 관리자용 생성기·문서는 남의 홈에 갈 이유가 없다
test("cursor: 공용 파이썬의 개발 전용 항목은 복사하지 않고, 예전 설치본에 있던 것도 지운다", () => {
  const home = mkdtempSync(join(tmpdir(), "cuh-"));
  const src = mkdtempSync(join(tmpdir(), "cus-"));
  try {
    const skillsSrc = join(src, "skills");
    const scriptsSrc = join(src, "scripts");
    mkdirSync(join(skillsSrc, "pro-thing"), { recursive: true });
    writeFileSync(join(skillsSrc, "pro-thing/SKILL.md"), "x");
    mkdirSync(join(scriptsSrc, "common"), { recursive: true });
    mkdirSync(join(scriptsSrc, "tests"), { recursive: true });
    writeFileSync(join(scriptsSrc, "common/__init__.py"), "");
    writeFileSync(join(scriptsSrc, "prefs_cli.py"), "x");
    writeFileSync(join(scriptsSrc, "tests/test_x.py"), "x");
    for (const name of SHARED_SCRIPTS_DEV_ONLY) writeFileSync(join(scriptsSrc, name), "x");

    // 예전 버전이 개발 전용 파일까지 깔아 둔 홈
    const scriptsDest = join(home, ".cursor/scripts");
    mkdirSync(join(home, ".cursor/skills"), { recursive: true });
    mkdirSync(scriptsDest, { recursive: true });
    writeFileSync(join(scriptsDest, "README.md"), "old");
    writeFileSync(join(scriptsDest, "sync_extras.py"), "old");
    writeFileSync(join(home, ".cursor/skills/cursor-skills-meta.json"), JSON.stringify({ version: "4.72.0", sharedScripts: ["README.md", "sync_extras.py"] }));

    const io = stubIo({ home });
    assert.equal(adapterById("cursor").apply(io, { sourceSkillsDir: skillsSrc, sourceScriptsDir: scriptsSrc, templateVersion: "9.9.9" }), true);

    assert.ok(existsSync(join(scriptsDest, "common/__init__.py")));
    assert.ok(existsSync(join(scriptsDest, "prefs_cli.py")));
    assert.equal(existsSync(join(scriptsDest, "tests")), false);
    for (const name of SHARED_SCRIPTS_DEV_ONLY) assert.equal(existsSync(join(scriptsDest, name)), false, name);
    const meta = JSON.parse(readFileSync(join(home, ".cursor/skills/cursor-skills-meta.json"), "utf8"));
    assert.deepEqual([...meta.sharedScripts].sort(), ["common", "prefs_cli.py"]);
  } finally { rmSync(home, { recursive: true, force: true }); rmSync(src, { recursive: true, force: true }); }
});

// 제외 목록 정합성: 설치된 스킬 CLI 가 개발 전용 항목을 import·실행하면 홈 설치에서 죽는다
test("개발 전용 공용 파이썬은 스킬 런타임 코드가 import·실행하지 않는다", () => {
  const isTestPath = (path) => /(^|\/)(tests?|__pycache__)(\/|$)/.test(path) || path.endsWith("conftest.py");
  const pythonFiles = (dir) => readdirSync(dir, { recursive: true })
    .map((rel) => String(rel).split("\\").join("/"))
    .filter((rel) => rel.endsWith(".py") && !isTestPath(rel))
    .map((rel) => join(dir, rel));
  const devOnlyPythonFiles = new Set([...SHARED_SCRIPTS_DEV_ONLY].map((name) => join(process.cwd(), "scripts", name)));
  const runtimeFiles = ["skills", "plugins", "hooks", "scripts"]
    .map((dir) => join(process.cwd(), dir))
    .filter((dir) => existsSync(dir))
    .flatMap(pythonFiles)
    .filter((file) => !devOnlyPythonFiles.has(file));
  assert.ok(runtimeFiles.length > 50, `runtime python files: ${runtimeFiles.length}`);
  const offenders = [];
  for (const name of SHARED_SCRIPTS_DEV_ONLY) {
    if (!name.endsWith(".py")) continue;
    const stem = name.slice(0, -3);
    // import 문, 또는 경로 조립용 따옴표 리터럴 ("build_troubleshooting.py")
    const usage = new RegExp(`^\\s*(from|import)\\s+${stem}\\b|["']${name.replace(".", "\\.")}["']`, "m");
    for (const file of runtimeFiles) if (usage.test(readFileSync(file, "utf8"))) offenders.push(`${file} -> ${name}`);
  }
  assert.deepEqual(offenders, []);
});

// ── copilot 어댑터 (실제 복사, ~/.copilot/skills/<이름>/SKILL.md — #200) ──
test("copilot: 사용 흔적이 없으면 cliMissing, apply 는 아무것도 만들지 않는다", () => {
  const home = mkdtempSync(join(tmpdir(), "cph-"));
  const src = mkdtempSync(join(tmpdir(), "cps-"));
  try {
    mkdirSync(join(src, "pro-thing"), { recursive: true });
    writeFileSync(join(src, "pro-thing/SKILL.md"), "x");
    const io = stubIo({ home });
    assert.equal(adapterById("copilot").detect(io).cliMissing, true);
    assert.equal(adapterById("copilot").apply(io, { sourceSkillsDir: src, templateVersion: "9.9.9" }), false);
    // 쓰지 않는 사람 홈에 ~/.copilot 을 만들면 안 된다
    assert.equal(existsSync(join(home, ".copilot")), false);
  } finally { rmSync(home, { recursive: true, force: true }); rmSync(src, { recursive: true, force: true }); }
});

test("copilot: copilot CLI 또는 VS Code Copilot 확장이 있으면 설치 후보", () => {
  const home = mkdtempSync(join(tmpdir(), "cph-"));
  try {
    assert.equal(adapterById("copilot").detect(stubIo({ home, present: { copilot: 1 } })).cliMissing, false);
    mkdirSync(join(home, ".vscode/extensions/github.copilot-chat-0.30.0"), { recursive: true });
    const status = adapterById("copilot").detect(stubIo({ home }));
    assert.equal(status.cliMissing, false);
    assert.equal(status.installed, false);
  } finally { rmSync(home, { recursive: true, force: true }); }
});

// IntelliJ·Android Studio 에만 Copilot 이 있는 사람: OS별 플러그인 위치로 감지
test("copilot: JetBrains Copilot 플러그인이 있으면 설치 후보 (macOS·Windows·Linux 위치)", () => {
  const pluginPaths = [
    "Library/Application Support/JetBrains/IntelliJIdea2025.2/plugins/github-copilot-intellij",
    "AppData/Roaming/JetBrains/IntelliJIdea2025.2/plugins/github-copilot-intellij",
    ".local/share/JetBrains/IntelliJIdea2025.2/github-copilot-intellij",
    "Library/Application Support/Google/AndroidStudio2025.1/plugins/github-copilot-intellij",
  ];
  for (const pluginPath of pluginPaths) {
    const home = mkdtempSync(join(tmpdir(), "cpj-"));
    try {
      mkdirSync(join(home, pluginPath), { recursive: true });
      assert.equal(adapterById("copilot").detect(stubIo({ home })).cliMissing, false, pluginPath);
    } finally { rmSync(home, { recursive: true, force: true }); }
  }
  // 다른 플러그인만 있으면 감지하지 않는다
  const home = mkdtempSync(join(tmpdir(), "cpj-"));
  try {
    mkdirSync(join(home, "Library/Application Support/JetBrains/IntelliJIdea2025.2/plugins/some-other-plugin"), { recursive: true });
    assert.equal(adapterById("copilot").detect(stubIo({ home })).cliMissing, true);
  } finally { rmSync(home, { recursive: true, force: true }); }
});

// ~/.copilot/intellij-skills 는 JetBrains 플러그인이 관리하는 내장 스킬 폴더 — 설치·제거가 건드리면 안 된다
test("copilot: JetBrains 관리 폴더 intellij-skills 는 그대로 둔다", () => {
  const home = mkdtempSync(join(tmpdir(), "cph-"));
  const src = mkdtempSync(join(tmpdir(), "cps-"));
  try {
    const managedSkill = join(home, ".copilot/intellij-skills/debug/SKILL.md");
    mkdirSync(join(home, ".copilot/intellij-skills/debug"), { recursive: true });
    writeFileSync(managedSkill, "managed");
    mkdirSync(join(src, "pro-thing"), { recursive: true });
    writeFileSync(join(src, "pro-thing/SKILL.md"), "x");
    const io = stubIo({ home });
    assert.equal(adapterById("copilot").apply(io, { sourceSkillsDir: src, templateVersion: "9.9.9" }), true);
    assert.equal(adapterById("copilot").remove(io, { sourceSkillsDir: src }), true);
    assert.equal(readFileSync(managedSkill, "utf8"), "managed");
  } finally { rmSync(home, { recursive: true, force: true }); rmSync(src, { recursive: true, force: true }); }
});

test("copilot: skills/ 복사 + meta 기록 + 폐기 스킬 정리 + 남의 스킬 보존한 제거", () => {
  const home = mkdtempSync(join(tmpdir(), "cph-"));
  const src = mkdtempSync(join(tmpdir(), "cps-"));
  try {
    const dest = join(home, ".copilot/skills");
    // 이미 깔린 상태: 폐기된 우리 스킬 + 사용자가 직접 넣은 스킬
    mkdirSync(join(dest, "pro-old"), { recursive: true });
    writeFileSync(join(dest, "pro-old/SKILL.md"), "x");
    mkdirSync(join(dest, "my-own-skill"), { recursive: true });
    writeFileSync(join(dest, "my-own-skill/SKILL.md"), "x");
    mkdirSync(join(src, "pro-new"), { recursive: true });
    writeFileSync(join(src, "pro-new/SKILL.md"), "x");
    mkdirSync(join(src, "references"), { recursive: true });
    writeFileSync(join(src, "references/common-rules.md"), "x");

    const io = stubIo({ home });   // ~/.copilot 폴더가 흔적이 된다
    assert.equal(adapterById("copilot").apply(io, { sourceSkillsDir: src, templateVersion: "9.9.9" }), true);
    // Copilot 이 읽는 모양: ~/.copilot/skills/<이름>/SKILL.md, 스킬이 참조하는 references/ 도 옆에
    assert.ok(existsSync(join(dest, "pro-new/SKILL.md")));
    assert.ok(existsSync(join(dest, "references/common-rules.md")));
    assert.equal(existsSync(join(dest, "pro-old")), false, "폐기된 pro- 스킬이 남았다");
    const meta = JSON.parse(readFileSync(join(dest, "copilot-skills-meta.json"), "utf8"));
    assert.equal(meta.version, "9.9.9");
    const status = adapterById("copilot").detect(io);
    assert.equal(status.installed, true);
    assert.equal(status.version, "9.9.9");

    // 제거: 우리 것만 지우고 사용자 스킬과 폴더는 남긴다
    assert.equal(adapterById("copilot").remove(io, { sourceSkillsDir: src }), true);
    assert.equal(existsSync(join(dest, "pro-new")), false);
    assert.equal(existsSync(join(dest, "references")), false);
    assert.equal(existsSync(join(dest, "copilot-skills-meta.json")), false);
    assert.ok(existsSync(join(dest, "my-own-skill/SKILL.md")), "사용자 스킬을 지웠다");
  } finally { rmSync(home, { recursive: true, force: true }); rmSync(src, { recursive: true, force: true }); }
});

test("copilot: 테스트 코드는 복사하지 않는다", () => {
  const home = mkdtempSync(join(tmpdir(), "cph-"));
  const src = mkdtempSync(join(tmpdir(), "cps-"));
  try {
    mkdirSync(join(src, "pro-thing/tests"), { recursive: true });
    mkdirSync(join(src, "pro-thing/scripts"), { recursive: true });
    writeFileSync(join(src, "pro-thing/SKILL.md"), "x");
    writeFileSync(join(src, "pro-thing/scripts/thing_cli.py"), "x");
    writeFileSync(join(src, "pro-thing/tests/test_thing.py"), "x");
    writeFileSync(join(src, "conftest.py"), "x");

    const io = stubIo({ home, present: { copilot: 1 } });
    assert.equal(adapterById("copilot").apply(io, { sourceSkillsDir: src, templateVersion: "9.9.9" }), true);

    const at = (r) => join(home, ".copilot/skills", r);
    assert.ok(existsSync(at("pro-thing/SKILL.md")));
    assert.ok(existsSync(at("pro-thing/scripts/thing_cli.py")));
    assert.equal(existsSync(at("pro-thing/tests")), false);
    assert.equal(existsSync(at("conftest.py")), false);
  } finally { rmSync(home, { recursive: true, force: true }); rmSync(src, { recursive: true, force: true }); }
});

// Copilot 은 frontmatter name 이 폴더명과 다르면 스킬을 조용히 무시한다 — 실제 skills/ 로 지킨다
test("copilot: 실제 스킬은 frontmatter name 이 폴더명과 같다", () => {
  const skillsRoot = join(process.cwd(), "skills");
  for (const name of readdirSync(skillsRoot)) {
    const skillFile = join(skillsRoot, name, "SKILL.md");
    if (!existsSync(skillFile)) continue;
    const frontmatterName = /^name:\s*["']?([^"'\s]+)/m.exec(readFileSync(skillFile, "utf8"))?.[1];
    assert.equal(frontmatterName, name, `${name}/SKILL.md 의 name 이 폴더명과 다르다`);
    assert.match(name, /^[a-z0-9-]{1,64}$/, `${name}: Copilot 스킬 이름 규칙(소문자·숫자·하이픈, 64자) 위반`);
  }
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

test("pi-harness: settings.json 을 해석하지 못하면 덮어쓰지 않는다 — 사용자 키 보존 (#911)", () => {
  const home = mkdtempSync(join(tmpdir(), "pih-"));
  try {
    const loaderDir = join(home, ".pi/agent/git/github.com/Cassiiopeia/projectops/harness");
    mkdirSync(loaderDir, { recursive: true });
    writeFileSync(join(loaderDir, "harness-loader.ts"), "//");
    const settings = join(home, ".pi/agent/settings.json");
    const brokenSettings = '{ "theme": "dark", }';   // 끝 쉼표: JSON.parse 실패
    writeFileSync(settings, brokenSettings);
    assert.equal(adapterById("pi-harness").apply(stubIo({ present: { pi: 1 }, home })), false);
    assert.equal(readFileSync(settings, "utf8"), brokenSettings);
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
