// 선택형 워크플로 그룹 표가 실제 템플릿 폴더와 맞고, 복사와 고아 감지가 같은 판정을 쓰는지 (#851).
//
// 켜는 쪽(복사)만 만들고 끄는 쪽(고아 감지)을 빠뜨리면 "껐는데 계속 돈다"가 된다 (#567).
// 두 쪽이 같은 표를 읽게 했으니, 남은 위험은 새 폴더를 표에 넣지 않는 것이다. 그것을 막는다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync } from "node:fs";
import { join } from "node:path";
import { commonOptionalGroups, serverDeployEnabled } from "../src/core/workflow-groups.js";

const COMMON = new URL("../.github/workflows/project-types/common/", import.meta.url).pathname;
const subdirs = (d) => readdirSync(d, { withFileTypes: true }).filter((e) => e.isDirectory()).map((e) => e.name);

test("common/ 아래 모든 하위 폴더가 선택형 그룹 표에 있다", () => {
  const known = new Set(commonOptionalGroups(COMMON).map((g) => g.dir.split(/[\\/]/)[0]));
  for (const name of subdirs(COMMON)) {
    assert.ok(known.has(name), `common/${name}/ 가 workflow-groups.js 에 없다 — 복사도 고아 감지도 안 된다`);
  }
  for (const name of subdirs(join(COMMON, "deploy"))) {
    assert.ok(commonOptionalGroups(COMMON).some((g) => g.dir === join("deploy", name)), `common/deploy/${name}/ 누락`);
  }
});

test("켜짐/꺼짐은 옵션 값 그대로이고 null 은 꺼짐이다", () => {
  const byDir = (opts) => Object.fromEntries(commonOptionalGroups(COMMON, opts).map((g) => [g.dir, g.enabled]));
  const on = byDir({ includeSecretBackup: true, aiPrSummary: true, projectsSync: true, deployTarget: "vercel" });
  assert.equal(on["pr-summary"], true);
  assert.equal(on["projects-sync"], true);
  assert.equal(on["secret-backup"], true);
  assert.equal(on[join("deploy", "vercel")], true);
  const off = byDir({ includeSecretBackup: false, aiPrSummary: null, projectsSync: false, deployTarget: "none" });
  assert.equal(off["pr-summary"], false, "null 을 켜짐으로 보면 복사와 고아 판정이 갈린다 (#851)");
  assert.equal(off["projects-sync"], false);
  assert.equal(off[join("deploy", "vercel")], false);
});

test("서버 배포 폴더는 docker-ssh 일 때만 (값이 없으면 기본 docker-ssh)", () => {
  assert.equal(serverDeployEnabled("docker-ssh"), true);
  assert.equal(serverDeployEnabled(undefined), true);
  assert.equal(serverDeployEnabled("vercel"), false);
  assert.equal(serverDeployEnabled("none"), false);
});
