import { test } from "node:test";
import assert from "node:assert/strict";
import { parseExisting, buildVersionYml, convertLegacySingularType, parseTemplateOptions } from "../src/core/version-yml.js";

test("roundtrip version/types/versionCode", () => {
  const yml = buildVersionYml({
    version: "1.2.3", types: ["spring", "react"], paths: new Map(),
    branch: "main", versionCode: 5, now: "2026-07-08 00:00:00", today: "2026-07-08",
  });
  const p = parseExisting(yml);
  assert.equal(p.version, "1.2.3");
  assert.deepEqual(p.types, ["spring", "react"]);
  assert.equal(p.versionCode, 5);
});

test("parseExisting version is source of truth", () => {
  const p = parseExisting('version: "9.9.9"\nproject_types: ["basic"]\n');
  assert.equal(p.version, "9.9.9");
});

test("parseExisting ignores comment lines (version_code oversight guard)", () => {
  const p = parseExisting('# version_code: 1 - Play Store 빌드 번호\nversion_code: 42\n');
  assert.equal(p.versionCode, 42);
});

test("parseExisting versionCode defaults to 1 when invalid", () => {
  assert.equal(parseExisting("version_code: 0\n").versionCode, 1);
  assert.equal(parseExisting("no code here\n").versionCode, 1);
});

test("parseExisting project_paths block", () => {
  const yml = 'project_paths:\n  flutter: "app"\n  react: "client"\nmetadata:\n';
  const p = parseExisting(yml);
  assert.equal(p.paths.get("flutter"), "app");
  assert.equal(p.paths.get("react"), "client");
});

test("buildVersionYml emits integrated_from projectops and template_integrator", () => {
  const yml = buildVersionYml({ version: "1.0.0", types: ["basic"], now: "n", today: "t" });
  assert.ok(yml.includes('integrated_from: "projectops"'));
  assert.ok(yml.includes('last_updated_by: "template_integrator"'));
  assert.ok(yml.includes('project_types: ["basic"]'));
});

test("buildVersionYml: 단수 project_type 키를 쓰지 않는다 (v4.1.0 SSOT)", () => {
  const yml = buildVersionYml({ version: "1.0.0", types: ["spring", "react"], now: "n", today: "t" });
  assert.ok(!/^project_type:/m.test(yml), "단수 project_type 라인이 생성되면 안 됨");
  assert.ok(yml.includes('project_types: ["spring","react"]'));
});

// #456 — deploy_branch를 default_branch와 별개 키로 저장한다 (릴리스 PR의 head).
test("buildVersionYml: deployBranch 지정 시 metadata.deploy_branch 출력", () => {
  const yml = buildVersionYml({
    version: "1.0.0", types: ["basic"], branch: "main", deployBranch: "develop", now: "n", today: "t",
  });
  assert.ok(yml.includes('default_branch: "main"'), "default_branch는 유지");
  assert.ok(yml.includes('deploy_branch: "develop"'), "deploy_branch 별개 키 출력");
});

test("buildVersionYml: deployBranch 미지정이면 deploy_branch 라인 없음(하위호환)", () => {
  const yml = buildVersionYml({ version: "1.0.0", types: ["basic"], branch: "main", now: "n", today: "t" });
  assert.ok(!/deploy_branch:/.test(yml), "deployBranch 없으면 라인 미출력");
});

test("parseExisting: default_branch·deploy_branch 읽기", () => {
  const yml = 'version: "1.0.0"\nmetadata:\n  default_branch: "main"\n  deploy_branch: "release"\n';
  const p = parseExisting(yml);
  assert.equal(p.defaultBranch, "main");
  assert.equal(p.deployBranch, "release");
});

test("parseExisting: deploy_branch 없으면 null(폴백은 호출부 책임)", () => {
  const p = parseExisting('version: "1.0.0"\nmetadata:\n  default_branch: "main"\n');
  assert.equal(p.deployBranch, null);
});

// ── convertLegacySingularType (#471) — workflows 모드 구식 스키마 최소 변환 ──

test("convertLegacySingularType: 단수 키만 있으면 배열로 교체 (나머지 내용 보존)", () => {
  const yml = '# 주석의 project_type: 언급은 무시\nversion: "2.5.81"\nversion_code: 148 # app build number\nproject_type: "spring" # spring, flutter, react\nmetadata:\n  default_branch: "main"\n';
  const out = convertLegacySingularType(yml);
  assert.ok(out.includes('project_types: ["spring"]'), "배열 키로 변환");
  assert.ok(!/^project_type:/m.test(out), "단수 키 제거");
  assert.ok(out.includes('version: "2.5.81"'), "버전 라인 보존");
  assert.ok(out.includes("version_code: 148"), "version_code 보존");
  assert.ok(out.includes('  default_branch: "main"'), "metadata 보존");
  assert.deepEqual(parseExisting(out).types, ["spring"], "변환 결과를 parseExisting이 읽음");
});

test("convertLegacySingularType: next 타입은 react로 흡수 (4.1.0)", () => {
  const out = convertLegacySingularType('project_type: "next"\n');
  assert.ok(out.includes('project_types: ["react"]'));
});

test("convertLegacySingularType: 배열 키 공존 시 단수 키만 제거", () => {
  const out = convertLegacySingularType('project_types: ["spring"]\nproject_type: "spring"\n');
  assert.ok(out.includes('project_types: ["spring"]'));
  assert.ok(!/^project_type:/m.test(out));
});

test("convertLegacySingularType: 변환 불필요(신형/단수 없음)면 null — 멱등 no-op", () => {
  assert.equal(convertLegacySingularType('version: "1.0.0"\nproject_types: ["spring"]\n'), null);
  assert.equal(convertLegacySingularType('version: "1.0.0"\n'), null);
  const converted = convertLegacySingularType('project_type: "spring"\n');
  assert.equal(convertLegacySingularType(converted), null, "재실행 시 추가 변환 없음");
});

// ── semver 자동 승격 (#546) ───────────────────────────────────────────
// 기록한 값을 다시 읽을 수 있어야 한다. 값 뒤 인라인 주석 때문에 왕복이 조용히
// 깨진 적이 있다(파서가 "true # ..."를 값으로 잡아 null 반환) — 그 자리를 고정한다.
test("semver_auto: 기본값(신규 통합)은 true로 기록되고 다시 읽힌다", () => {
  const yml = buildVersionYml({
    version: "1.0.0", types: ["spring"], now: "2026-09-15 00:00:00", today: "2026-09-15",
    templateOptions: { templateVersion: "4.3.0" },
  });
  assert.match(yml, /^\s+semver_auto: true/m);
  assert.equal(parseTemplateOptions(yml).semverAuto, true);
});

test("semver_auto: false도 왕복한다", () => {
  const yml = buildVersionYml({
    version: "1.0.0", types: ["spring"], now: "x", today: "y",
    templateOptions: { templateVersion: "4.3.0", semverAuto: false },
  });
  assert.equal(parseTemplateOptions(yml).semverAuto, false);
});

test("semver_auto: 값 뒤 인라인 주석이 있어도 파싱된다", () => {
  const yml = 'version: "1.0.0"\nmetadata:\n  template:\n    options:\n      semver_auto: true   # 사람이 단 주석\n';
  assert.equal(parseTemplateOptions(yml).semverAuto, true);
});

test("semver_auto: 키가 없는 구 version.yml은 null (호출부가 OFF로 해석)", () => {
  const yml = 'version: "1.0.0"\nmetadata:\n  last_updated: "x"\n';
  assert.equal(parseTemplateOptions(yml).semverAuto, null);
});

// ── 프로젝트 성격 app_release (#553) ──────────────────────────────────
// 워크플로우와 스킬이 같은 값을 보게 하는 것이 목적이다. 종전에는 스킬 설정 파일(사용자 홈)에만
// 있어서 워크플로우가 볼 수 없었고, 같은 사실이 두 곳에 따로 존재했다.
test("app_release: 미지정이면 키 자체를 쓰지 않는다 (기존 레포 무변화)", () => {
  const yml = buildVersionYml({
    version: "1.0.0", types: ["flutter"], now: "x", today: "y",
    templateOptions: { templateVersion: "4.3.0" },
  });
  assert.ok(!/app_release:/.test(yml));
  assert.equal(parseTemplateOptions(yml).appRelease, null);
});

test("app_release: true를 기록하고 다시 읽는다", () => {
  const yml = buildVersionYml({
    version: "1.0.0", types: ["flutter"], now: "x", today: "y",
    templateOptions: { templateVersion: "4.3.0", appRelease: true },
  });
  assert.match(yml, /^\s+app_release: true/m);
  assert.equal(parseTemplateOptions(yml).appRelease, true);
});

test("app_release: false도 왕복한다", () => {
  const yml = buildVersionYml({
    version: "1.0.0", types: ["spring"], now: "x", today: "y",
    templateOptions: { templateVersion: "4.3.0", appRelease: false },
  });
  assert.equal(parseTemplateOptions(yml).appRelease, false);
});

test("app_release: 값 뒤 인라인 주석이 있어도 파싱된다", () => {
  const yml = 'version: "1.0.0"\nmetadata:\n  template:\n    options:\n      app_release: true   # 손으로 단 주석\n';
  assert.equal(parseTemplateOptions(yml).appRelease, true);
});

test("app_release와 semver_auto가 서로 간섭하지 않는다", () => {
  const yml = buildVersionYml({
    version: "1.0.0", types: ["flutter"], now: "x", today: "y",
    templateOptions: { templateVersion: "4.3.0", semverAuto: false, appRelease: true },
  });
  const o = parseTemplateOptions(yml);
  assert.equal(o.semverAuto, false);
  assert.equal(o.appRelease, true);
});
