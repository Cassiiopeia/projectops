import { test } from "node:test";
import assert from "node:assert/strict";
import { runInteractive } from "../src/commands/interactive.js";
import { CANCEL } from "../src/ui/prompts.js";
import { writeText, exists } from "../src/core/fsutil.js";
import { mkdtempSync, rmSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { GUIDE_FILE } from "../src/core/migration-guide.js";

// 최소 템플릿 소스 (local acquire용)
function makeSource(dir) {
  const b = join(dir, ".github/workflows/project-types");
  writeText(join(b, "common/PROJECT-COMMON-CI.yaml"), "name: ci\n");
  writeText(join(b, "react/PROJECT-REACT-CICD.yaml"), '  APP: "__X__"  # @wizard ask:myapp\n');
  writeText(join(dir, ".github/scripts/version_manager.sh"), "#!/bin/bash\n");
  writeText(join(dir, ".github/ISSUE_TEMPLATE/bug.md"), "bug\n");
  writeText(join(dir, "version.yml"), 'version: "3.0.0"\n');
}

// io 스텁 팩토리 — 지정 시퀀스대로 응답
function stubIo(answers) {
  const q = { ...answers };
  const noop = () => {};
  return {
    intro: noop, outro: noop, note: noop, cancelMessage: noop,
    selectMode: async () => q.mode,
    confirmProjectMenu: async () => q.confirm ?? "continue",
    editMenu: async () => "done",
    selectTypes: async () => q.types ?? CANCEL,
    askText: async (_m, d) => d,
    askYesNo: async (_m, i) => i,
  };
}

test("대화형: 모드 취소 → exit 0, 파일 미생성", async () => {
  const src = mkdtempSync(join(tmpdir(), "iasrc-"));
  const cwd = mkdtempSync(join(tmpdir(), "iacwd-"));
  try {
    makeSource(src);
    const code = await runInteractive({}, {
      cwd, source: { type: "local", path: src }, clock: { now: "n", today: "t" },
      io: stubIo({ mode: CANCEL }),
    });
    assert.equal(code, 0);
    assert.equal(exists(join(cwd, "version.yml")), false); // 취소라 통합 안 함
  } finally { rmSync(src, { recursive: true, force: true }); rmSync(cwd, { recursive: true, force: true }); }
});

test("대화형: full 선택 → continue → 실제 통합 실행", async () => {
  const src = mkdtempSync(join(tmpdir(), "iasrc2-"));
  const cwd = mkdtempSync(join(tmpdir(), "iacwd2-"));
  try {
    makeSource(src);
    writeText(join(cwd, "package.json"), '{"dependencies":{"react":"18"}}'); // react 감지
    const code = await runInteractive({}, {
      cwd, source: { type: "local", path: src }, clock: { now: "2026-07-08 00:00:00", today: "2026-07-08" },
      io: stubIo({ mode: "full", confirm: "continue" }),
    });
    assert.equal(code, 0);
    // full 모드 산출물
    assert.ok(exists(join(cwd, "version.yml")));
    assert.ok(exists(join(cwd, ".github/workflows/PROJECT-COMMON-CI.yaml")));
    assert.ok(exists(join(cwd, ".github/workflows/PROJECT-REACT-CICD.yaml")));
    // TEMP 정리됨
    assert.equal(exists(join(cwd, ".template_download_temp")), false);
  } finally { rmSync(src, { recursive: true, force: true }); rmSync(cwd, { recursive: true, force: true }); }
});

test("대화형: issues 모드 → 템플릿만", async () => {
  const src = mkdtempSync(join(tmpdir(), "iasrc3-"));
  const cwd = mkdtempSync(join(tmpdir(), "iacwd3-"));
  try {
    makeSource(src);
    const code = await runInteractive({}, {
      cwd, source: { type: "local", path: src }, clock: { now: "n", today: "t" },
      io: stubIo({ mode: "issues" }),
    });
    assert.equal(code, 0);
    assert.ok(exists(join(cwd, ".github/ISSUE_TEMPLATE/bug.md")));
    assert.equal(exists(join(cwd, "version.yml")), false); // issues는 version.yml 안 만듦
  } finally { rmSync(src, { recursive: true, force: true }); rmSync(cwd, { recursive: true, force: true }); }
});

test("대화형: skills 모드 → IDE 스킬 설치 흐름 실행 후 exit 0", async () => {
  const src = mkdtempSync(join(tmpdir(), "iasrc4-"));
  const cwd = mkdtempSync(join(tmpdir(), "iacwd4-"));
  try {
    makeSource(src);
    // skills 모드는 템플릿을 획득하고 runSkills를 부른다.
    // 실제 IDE CLI를 안 건드리도록 skills를 스텁으로 주입 — 호출 여부만 검증.
    let skillsCalled = false;
    const code = await runInteractive({}, {
      cwd, source: { type: "local", path: src }, clock: { now: "n", today: "t" },
      io: stubIo({ mode: "skills" }),
      skills: async (o) => { skillsCalled = true; assert.equal(o.interactive, true); return 0; },
    });
    assert.equal(skillsCalled, true);
    assert.equal(code, 0);
    // skills는 통합이 아니므로 version.yml을 만들지 않는다
    assert.equal(exists(join(cwd, "version.yml")), false);
    // TEMP 정리됨
    assert.equal(exists(join(cwd, ".template_download_temp")), false);
  } finally { rmSync(src, { recursive: true, force: true }); rmSync(cwd, { recursive: true, force: true }); }
});

// ── #487 타입 탈출구 + 고아 워크플로우 정리 통합 시나리오 ──

test("대화형: 오감지 타입을 '이 타입 제외'로 탈출 → basic 폴백, 해당 타입 미설치 (#487)", async () => {
  const src = mkdtempSync(join(tmpdir(), "iasrc5-"));
  const cwd = mkdtempSync(join(tmpdir(), "iacwd5-"));
  try {
    makeSource(src);
    // 이슈 재현: 아카이브 폴더의 build.gradle이 spring으로 오감지된 상태 (version.yml에 spring 기록)
    writeText(join(cwd, "version.yml"), 'version: "1.0.0"\nversion_code: 1\nproject_types: ["spring"]\n');
    writeText(join(cwd, "code-archive/old/build.gradle"), "// archived\n");
    const engineIo = {
      select: async ({ options }) => {
        const ex = options.find((o) => o.value === "이 타입 제외");
        return ex ? ex.value : options[0].value;
      },
      text: async ({ defaultValue }) => defaultValue ?? "",
      confirm: async ({ initialValue }) => initialValue ?? true,
      multiselect: async ({ initialValues }) => initialValues ?? [],
    };
    // 경로 확정의 대화형 분기(탈출구)는 realTty에서만 열린다 — 테스트 러너는 파이프라 임시로 강제
    const savedTty = process.stdout.isTTY;
    process.stdout.isTTY = true;
    let code;
    try {
      code = await runInteractive({}, {
        cwd, source: { type: "local", path: src }, clock: { now: "2026-07-13 00:00:00", today: "2026-07-13" },
        io: { ...stubIo({ mode: "full", confirm: "continue" }), engineIo },
      });
    } finally { process.stdout.isTTY = savedTty; }
    assert.equal(code, 0);
    // spring이 제외되어 basic으로 폴백 — version.yml에 spring이 남지 않는다
    const vy = readFileSync(join(cwd, "version.yml"), "utf8");
    assert.ok(vy.includes('"basic"'), `basic 폴백이어야 함: ${vy}`);
    assert.ok(!vy.includes('"spring"'), `spring이 제거돼야 함: ${vy}`);
  } finally { rmSync(src, { recursive: true, force: true }); rmSync(cwd, { recursive: true, force: true }); }
});

test("대화형: 선택 안 된 타입의 고아 워크플로우 → 확인 후 .bak 무해화 (#487)", async () => {
  const src = mkdtempSync(join(tmpdir(), "iasrc6-"));
  const cwd = mkdtempSync(join(tmpdir(), "iacwd6-"));
  try {
    makeSource(src);
    // 템플릿에 spring 타입 워크플로우 존재 (server-deploy 하위)
    writeText(join(src, ".github/workflows/project-types/spring/server-deploy/PROJECT-SPRING-SIMPLE-CICD.yaml"), "name: s\n");
    // 대상 레포: react 프로젝트인데 과거 설치된 spring 워크플로우가 잔존 (고아)
    writeText(join(cwd, "package.json"), '{"dependencies":{"react":"18"}}');
    writeText(join(cwd, ".github/workflows/PROJECT-SPRING-SIMPLE-CICD.yaml"), "old\n");
    writeText(join(cwd, ".github/workflows/PROJECT-SPRING-MY-CUSTOM.yaml"), "custom\n"); // 사용자 커스텀 — 보호 대상
    const code = await runInteractive({}, {
      cwd, source: { type: "local", path: src }, clock: { now: "2026-07-13 00:00:00", today: "2026-07-13" },
      io: stubIo({ mode: "full", confirm: "continue" }), // askYesNo 기본값 → 고아 정리 예
    });
    assert.equal(code, 0);
    // 고아는 .bak 무해화, 커스텀은 보존
    assert.equal(exists(join(cwd, ".github/workflows/PROJECT-SPRING-SIMPLE-CICD.yaml")), false);
    assert.ok(exists(join(cwd, ".github/workflows/PROJECT-SPRING-SIMPLE-CICD.yaml.bak")));
    assert.ok(exists(join(cwd, ".github/workflows/PROJECT-SPRING-MY-CUSTOM.yaml")));
    // 선택된 react 워크플로우는 정상 설치
    assert.ok(exists(join(cwd, ".github/workflows/PROJECT-REACT-CICD.yaml")));
  } finally { rmSync(src, { recursive: true, force: true }); rmSync(cwd, { recursive: true, force: true }); }
});

// #493/#494 — full 실행이 끝나면 마이그레이션 가이드·트레이스가 남는다
test("대화형: full 완료 시 마이그레이션 가이드 + JSONL 트레이스 생성", async () => {
  const src = mkdtempSync(join(tmpdir(), "iasrc-mg-"));
  const cwd = mkdtempSync(join(tmpdir(), "iacwd-mg-"));
  try {
    makeSource(src);
    writeText(join(cwd, "package.json"), '{"dependencies":{"react":"18"}}');
    const code = await runInteractive({}, {
      cwd, source: { type: "local", path: src }, clock: { now: "2026-07-14 00:16:04", today: "2026-07-14" },
      io: stubIo({ mode: "full", confirm: "continue" }),
    });
    assert.equal(code, 0);
    const guide = join(cwd, GUIDE_FILE);
    assert.ok(exists(guide), "가이드 생성");
    const md = readFileSync(guide, "utf8");
    assert.match(md, /# ProjectOps 마이그레이션 가이드/);
    assert.match(md, /schema: 1/);
    assert.match(md, /PROJECT-REACT-CICD\.yaml/); // 복사된 워크플로우가 메타에 반영
    // JSONL 트레이스 — 가이드 메타의 trace_file 경로가 실제로 존재
    const traceFile = (md.match(/trace_file: "([^"]+)"/) || [])[1];
    assert.ok(traceFile, "trace_file 포인터 존재");
    assert.ok(exists(join(cwd, traceFile)), "JSONL 파일 존재");
    const jsonl = readFileSync(join(cwd, traceFile), "utf8").trim().split("\n").map((l) => JSON.parse(l));
    assert.equal(jsonl[0].kind, "projectops-migration-trace");
    assert.ok(jsonl.some((e) => e.phase === "copy" && e.target === "PROJECT-REACT-CICD.yaml"));
  } finally { rmSync(src, { recursive: true, force: true }); rmSync(cwd, { recursive: true, force: true }); }
});
