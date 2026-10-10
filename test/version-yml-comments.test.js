// 업데이트가 한국어 레포의 version.yml 주석을 영문으로 바꾸고 last_updated_by 를 덮어쓰던 문제 (#811).
// 설정은 그대로인데 diff 가 86줄이라 리뷰어가 진짜 변경을 찾을 수 없었다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { execFileSync } from "node:child_process";
import { buildVersionYml, resolveUpdatedBy } from "../src/core/version-yml.js";

const base = { version: "1.0.0", types: ["spring"], now: "2026-10-08 00:00:00", today: "2026-10-08" };

test("language: ko 레포는 헤더와 키 주석이 한국어다", () => {
  const out = buildVersionYml({ ...base, templateOptions: { language: "ko", closeOnRelease: true } });
  assert.match(out, /# 프로젝트 버전 관리 파일/);
  assert.match(out, /project_types: \["spring"\]   # 멀티타입 배열/);
  assert.match(out, /semver_auto: true   # 커밋 제목으로 버전 승격 폭 결정/);
  assert.doesNotMatch(out, /array of types/);
});

test("language: en 또는 미기재는 영문 주석", () => {
  for (const templateOptions of [{ language: "en" }, null]) {
    const out = buildVersionYml({ ...base, templateOptions });
    assert.match(out, /# Project version management file/);
    assert.match(out, /# array of types, first entry is primary/);
  }
});

test("last_updated_by 는 넘겨받은 값을 쓴다", () => {
  const out = buildVersionYml({ ...base, updatedBy: "Cassiiopeia" });
  assert.match(out, /last_updated_by: "Cassiiopeia"/);
});

test("resolveUpdatedBy: git 사용자가 없으면 기존 값을 지킨다", () => {
  const dir = mkdtempSync(join(tmpdir(), "vyby-"));
  execFileSync("git", ["init", "-q"], { cwd: dir });
  // 전역 설정을 무시해 CI 처럼 user.name 이 없는 상태를 만든다
  const env = { ...process.env, GIT_CONFIG_GLOBAL: "/dev/null", GIT_CONFIG_SYSTEM: "/dev/null" };
  const saved = { ...process.env };
  Object.assign(process.env, env);
  try {
    assert.equal(resolveUpdatedBy('metadata:\n  last_updated_by: "Cassiiopeia"\n', dir), "Cassiiopeia");
    assert.equal(resolveUpdatedBy("", dir), "template_integrator");
    execFileSync("git", ["config", "user.name", "someone"], { cwd: dir });
    assert.equal(resolveUpdatedBy('metadata:\n  last_updated_by: "Cassiiopeia"\n', dir), "someone");
  } finally {
    for (const k of Object.keys(process.env)) if (!(k in saved)) delete process.env[k];
    Object.assign(process.env, saved);
  }
});

test("머리말이 semver_auto 기본값을 실제 동작(키 없음 = 켜짐)대로 설명한다", () => {
  for (const language of ["en", "ko"]) {
    const out = buildVersionYml({ ...base, templateOptions: { language } });
    assert.doesNotMatch(out, /key missing \/ false|키 없음 \/ false/, `${language}: 키 없음을 patch 로 설명하면 안 된다`);
    assert.match(out, /semver_auto: false -> /);
  }
});

test("version_code 주석 앞 공백은 version_manager.py 와 같은 1칸 (업데이트 diff 방지)", () => {
  const out = buildVersionYml({ ...base, versionCode: 136 });
  assert.match(out, /^version_code: 136 # /m);
  const vm = readFileSync(new URL("../.github/scripts/version_manager.py", import.meta.url), "utf8");
  assert.match(vm, /version_code: \{new_code\} # app build number/, "version_manager.py 형식이 바뀌면 이 테스트와 같이 맞춘다");
});
