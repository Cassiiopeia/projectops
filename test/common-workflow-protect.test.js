import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { copyWorkflows, listWorkflowConflicts } from "../src/core/copy/workflows.js";

// common 워크플로우 보호 (#560).
// 종전에는 "unchanged면 스킵, 아니면 무조건 덮어쓰기"라 사용자 수정이 백업도 질문도 없이
// 사라졌다. common/deploy조차 .bak을 남기는데 본체만 아무것도 남기지 않았다.

const NAME = "PROJECT-COMMON-R.yaml";
const CTX = { types: [], paths: new Map(), deployTarget: "none", publishTargets: [], force: true,
              repoName: "r", resolvers: {}, templateVersion: "1.0.0", now: "x" };

function template(body = "name: R\non:\n  push:\n") {
  const root = mkdtempSync(join(tmpdir(), "tpl-"));
  const dir = join(root, ".github/workflows/project-types/common");
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, NAME), body, "utf8");
  return { root, dir };
}
const wfPath = (t) => join(t, ".github/workflows", NAME);

test("기준점 없는 기존 레포: 덮어쓰되 .bak을 남긴다", () => {
  // 핵심 회귀. common의 종전 계약("항상 최신")은 지키되 되돌릴 수단을 남겨야 한다.
  const { root: tpl, dir } = template();
  const t = mkdtempSync(join(tmpdir(), "old-"));
  mkdirSync(join(t, ".github/workflows"), { recursive: true });
  writeFileSync(wfPath(t), "name: R\non:\n  push:\n# 내 커스텀\n", "utf8");
  writeFileSync(join(dir, NAME), "name: R\non:\n  push:\n# 템플릿 개선\n", "utf8");

  copyWorkflows(CTX, tpl, t, {});

  assert.match(readFileSync(wfPath(t), "utf8"), /템플릿 개선/, "템플릿 갱신은 유지된다");
  assert.ok(existsSync(wfPath(t) + ".bak"), ".bak이 있어야 한다");
  assert.match(readFileSync(wfPath(t) + ".bak", "utf8"), /내 커스텀/, "내 수정이 .bak에 보존된다");
});

test("기준점 있음 + 사용자 수정: 결정 미지정이면 유지(덮어쓰지 않는다)", () => {
  const { root: tpl, dir } = template();
  const t = mkdtempSync(join(tmpdir(), "new-"));
  copyWorkflows(CTX, tpl, t, {});                                  // 기준점 생성
  writeFileSync(wfPath(t), readFileSync(wfPath(t), "utf8") + "# 내 커스텀\n", "utf8");
  writeFileSync(join(dir, NAME), "name: R\non:\n  push:\n# 템플릿 개선\n", "utf8");

  copyWorkflows(CTX, tpl, t, {});                                  // 결정 미지정 = skip

  assert.match(readFileSync(wfPath(t), "utf8"), /내 커스텀/);
});

test("기준점 있음 + 사용자 미수정: 질문 없이 자동 갱신 (종전 동작 보존)", () => {
  const { root: tpl, dir } = template();
  const t = mkdtempSync(join(tmpdir(), "up-"));
  copyWorkflows(CTX, tpl, t, {});
  writeFileSync(join(dir, NAME), "name: R\non:\n  push:\n# 템플릿 개선\n", "utf8");

  copyWorkflows(CTX, tpl, t, {});

  assert.match(readFileSync(wfPath(t), "utf8"), /템플릿 개선/);
  assert.ok(!existsSync(wfPath(t) + ".bak"), "손대지 않았으면 .bak을 만들 이유가 없다");
});

test("backup 결정을 주면 .bak 후 교체", () => {
  const { root: tpl, dir } = template();
  const t = mkdtempSync(join(tmpdir(), "bak-"));
  copyWorkflows(CTX, tpl, t, {});
  writeFileSync(wfPath(t), readFileSync(wfPath(t), "utf8") + "# 내 커스텀\n", "utf8");
  writeFileSync(join(dir, NAME), "name: R\non:\n  push:\n# 템플릿 개선\n", "utf8");

  copyWorkflows(CTX, tpl, t, { decisions: new Map([[NAME, "backup"]]) });

  assert.match(readFileSync(wfPath(t), "utf8"), /템플릿 개선/);
  assert.match(readFileSync(wfPath(t) + ".bak", "utf8"), /내 커스텀/);
});

test("충돌 목록: 사용자 수정이 확인된 common 파일만 질문 대상", () => {
  const { root: tpl, dir } = template();
  const t = mkdtempSync(join(tmpdir(), "cf-"));
  copyWorkflows(CTX, tpl, t, {});
  writeFileSync(wfPath(t), readFileSync(wfPath(t), "utf8") + "# 내 커스텀\n", "utf8");
  writeFileSync(join(dir, NAME), "name: R\non:\n  push:\n# 템플릿 개선\n", "utf8");

  const conflicts = listWorkflowConflicts(CTX, tpl, t);
  assert.deepEqual(conflicts, [{ filename: NAME, type: "common" }]);
});

test("충돌 목록: 기준점이 없으면 질문하지 않는다 (엔진이 .bak으로 처리)", () => {
  const { root: tpl, dir } = template();
  const t = mkdtempSync(join(tmpdir(), "cf2-"));
  mkdirSync(join(t, ".github/workflows"), { recursive: true });
  writeFileSync(wfPath(t), "name: R\non:\n  push:\n# 내 커스텀\n", "utf8");
  writeFileSync(join(dir, NAME), "name: R\non:\n  push:\n# 템플릿 개선\n", "utf8");

  assert.deepEqual(listWorkflowConflicts(CTX, tpl, t), []);
});
