// 기본값이 한 곳에서 정해지는지 (#832).
// CodeRabbit 기본값이 대화형(true)과 비대화형(false)으로 갈려 있었다 — 질문하지 않는 version·issues 대화형 모드가
// 설치되지도 않는 CodeRabbit 을 "켬"으로 version.yml 에 기록했다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DEFAULT_CODE_REVIEW_CODERABBIT } from "../src/core/constants.js";

test("CodeRabbit 은 기본으로 꺼져 있다 — 별도 앱 설치 없이는 동작하지 않는다", () => {
  assert.equal(DEFAULT_CODE_REVIEW_CODERABBIT, false);
});

test("대화형·비대화형·질문 경로가 모두 같은 상수를 쓰고 값을 따로 박지 않는다", () => {
  for (const f of ["src/index.js", "src/commands/interactive.js", "src/core/options-ask.js"]) {
    const text = readFileSync(new URL(`../${f}`, import.meta.url), "utf8");
    assert.match(text, /DEFAULT_CODE_REVIEW_CODERABBIT/, `${f} 가 공용 기본값을 쓰지 않는다`);
    assert.doesNotMatch(text, /codeReviewCoderabbit\s*(\?\?|=)\s*(true|false)\b[^=]/,
      `${f} 에 CodeRabbit 기본값이 직접 박혀 있다 — constants.js 의 DEFAULT_CODE_REVIEW_CODERABBIT 를 쓴다`);
  }
});
