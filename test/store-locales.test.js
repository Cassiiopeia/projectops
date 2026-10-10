// store_locales 옵션 (#829) — version.yml 은 마법사가 전체를 다시 쓰므로 왕복과 보존이 깨지면 업데이트 때 값이 사라진다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { buildVersionYml, parseTemplateOptions, parseExisting } from "../src/core/version-yml.js";

const build = (templateOptions) => buildVersionYml({
  version: "1.0.0", types: ["flutter"], now: "2026-10-10 00:00:00", today: "2026-10-10",
  templateOptions: { templateVersion: "4.40.0", ...templateOptions },
});

test("store_locales: 기록하고 다시 읽는다", () => {
  const yml = build({ storeLocales: ["ko-KR", "en-US", "ja-JP", "zh-CN"] });
  assert.match(yml, /store_locales: \["ko-KR", "en-US", "ja-JP", "zh-CN"\]/);
  assert.deepEqual(parseTemplateOptions(yml).storeLocales, ["ko-KR", "en-US", "ja-JP", "zh-CN"]);
});

test("store_locales: 미지정이면 키 자체를 쓰지 않는다 (기존 레포 무변화)", () => {
  assert.doesNotMatch(build({}), /store_locales/);
  assert.doesNotMatch(build({ storeLocales: [] }), /store_locales/);
  assert.equal(parseTemplateOptions(build({})).storeLocales, null);
});

test("store_locales: 값 뒤 인라인 주석이 있어도 파싱된다", () => {
  const o = parseTemplateOptions('metadata:\n  template:\n    options:\n      store_locales: ["ko-KR","en-US"]   # 설명\n');
  assert.deepEqual(o.storeLocales, ["ko-KR", "en-US"]);
});

test("store_locales: 다시 쓰기를 거쳐도 보존된다 (업데이트 시뮬레이션)", () => {
  const first = build({ storeLocales: ["ko-KR", "en-US"] });
  const carried = parseTemplateOptions(first).storeLocales;
  const second = build({ storeLocales: carried });
  assert.deepEqual(parseTemplateOptions(second).storeLocales, ["ko-KR", "en-US"]);
});

test("store_locales: 다른 옵션을 건드리지 않는다", () => {
  const o = parseTemplateOptions(build({ storeLocales: ["ko-KR"], semverAuto: false, appRelease: true }));
  assert.equal(o.semverAuto, false);
  assert.equal(o.appRelease, true);
});

test("store_locales_ios / store_locales_play: 기록하고 다시 읽는다, 서로 간섭하지 않는다", () => {
  const yml = build({ storeLocales: ["ko-KR", "en-US", "ja-JP", "zh-CN"], storeLocalesIos: ["ko-KR", "en-US"], storeLocalesPlay: ["ko-KR", "en-US", "ja-JP"] });
  assert.match(yml, /store_locales_ios: \["ko-KR", "en-US"\]/);
  assert.match(yml, /store_locales_play: \["ko-KR", "en-US", "ja-JP"\]/);
  const o = parseTemplateOptions(yml);
  assert.deepEqual(o.storeLocales, ["ko-KR", "en-US", "ja-JP", "zh-CN"]);
  assert.deepEqual(o.storeLocalesIos, ["ko-KR", "en-US"]);
  assert.deepEqual(o.storeLocalesPlay, ["ko-KR", "en-US", "ja-JP"]);
});

test("store_locales_ios/play: 미지정이면 키를 쓰지 않는다 (기존 레포 무변화)", () => {
  const yml = build({ storeLocales: ["ko-KR"] });
  assert.doesNotMatch(yml, /store_locales_(ios|play)/);
  const o = parseTemplateOptions(yml);
  assert.equal(o.storeLocalesIos, null);
  assert.equal(o.storeLocalesPlay, null);
});

test("store_locales_ios: 공통 키와 접두어가 같아도 서로 잘못 읽지 않는다", () => {
  const o = parseTemplateOptions('metadata:\n  template:\n    options:\n      store_locales_ios: ["ko-KR"]\n');
  assert.equal(o.storeLocales, null);
  assert.deepEqual(o.storeLocalesIos, ["ko-KR"]);
});

test("store_locales_ios/play: 다시 쓰기를 거쳐도 보존된다 (업데이트 시뮬레이션)", () => {
  const first = build({ storeLocales: ["ko-KR", "en-US"], storeLocalesIos: ["ko-KR"], storeLocalesPlay: ["ko-KR", "en-US"] });
  const p = parseTemplateOptions(first);
  const second = build({ storeLocales: p.storeLocales, storeLocalesIos: p.storeLocalesIos, storeLocalesPlay: p.storeLocalesPlay });
  const q = parseTemplateOptions(second);
  assert.deepEqual([q.storeLocales, q.storeLocalesIos, q.storeLocalesPlay], [["ko-KR", "en-US"], ["ko-KR"], ["ko-KR", "en-US"]]);
});
