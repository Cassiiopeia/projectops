// #446 배너·상태 카드 검증 — writer 주입으로 출력 캡처
import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { printBanner, printBannerCompact } from "../src/ui/banner.js";
import {
  printDetectionLog, printAnalysisCard, printIdeStatus, printInstallKind, collectIdeStatuses,
} from "../src/ui/status-cards.js";
import { visualWidth } from "../src/ui/ansi.js";
import { setLang } from "../src/i18n/index.js";

// These tests assert the Korean catalog; English output has its own tests at the bottom.
beforeEach(() => setLang("ko", "flag"));
afterEach(() => setLang("en", "default"));

const capture = () => {
  const buf = [];
  const out = (s) => buf.push(s);
  out.text = () => buf.join("");
  return out;
};
const strip = (s) => s.replace(/\x1b\[[0-9;]*m/g, "");

test("printBanner: 박스 타이틀 + 메타 4줄 (시안 A)", () => {
  const out = capture();
  printBanner({ version: "4.0.3", modeLabel: "대화형 통합 마법사" }, out);
  const t = strip(out.text());
  assert.match(t, /P R O J E C T O P S/);
  assert.match(t, /╔═+╗/);
  assert.match(t, /Version : v4\.0\.3/);
  assert.match(t, /Author {2}: Cassiiopeia/);
  assert.match(t, /Mode {4}: 대화형 통합 마법사/);
  assert.match(t, /github\.com\/Cassiiopeia\/projectops/);
  // 박스 정렬: ║로 시작하는 줄은 모두 ║로 끝나야 함
  for (const line of t.split("\n")) {
    if (line.startsWith("║")) assert.ok(line.endsWith("║"), `박스 줄 정렬 깨짐: "${line}"`);
  }
});

test("printBannerCompact: 비대화형 1줄", () => {
  const out = capture();
  printBannerCompact({ version: "4.0.3", mode: "full" }, out);
  const t = strip(out.text());
  assert.equal(t.trim().split("\n").length, 1);
  assert.match(t, /projectops v4\.0\.3 \(full 모드, --force\)/);
});

test("printDetectionLog: 타입별 마커 + 버전/브랜치, basic 폴백", () => {
  const out = capture();
  printDetectionLog({ types: ["spring", "react"], version: "1.2.3", branch: "main" }, out);
  const t = strip(out.text());
  assert.match(t, /build\.gradle 발견, spring 감지/);
  assert.match(t, /package\.json 발견, react 감지/);
  assert.match(t, /버전: v1\.2\.3, 브랜치: main/);

  const out2 = capture();
  printDetectionLog({ types: ["basic"], version: "0.0.1", branch: "main" }, out2);
  assert.match(strip(out2.text()), /마커 파일 없음, basic/);
});

test("printAnalysisCard: 멀티타입·옵션·모노레포 경로 표시", () => {
  const out = capture();
  printAnalysisCard({
    mode: "full", modeLabel: "전체 설치", types: ["spring", "react"], version: "1.2.3", branch: "main",
    deployTarget: "docker-ssh", publishTargets: ["nexus"], includeSecretBackup: false, showOptional: true,
    paths: new Map([["spring", "server"], ["react", "client"]]),
  }, out);
  const t = strip(out.text());
  assert.match(t, /타입\(멀티\).*spring, react/);
  assert.match(t, /배포.*docker-ssh/);
  assert.match(t, /Publish.*nexus/);
  assert.match(t, /Secret 백업.*제외/);
  assert.match(t, /spring→server, react→client/);
});

test("printAnalysisCard: 한글·영문 혼합 라벨이 시각 폭으로 정렬됨 (CJK 폭 버그 수정)", () => {
  const out = capture();
  printAnalysisCard({
    mode: "full", modeLabel: "전체 설치", types: ["basic"], version: "4.2.1", branch: "main",
    deployTarget: "none", publishTargets: [], includeSecretBackup: false, showOptional: true,
    paths: new Map(),
  }, out);
  // Each data row is "|  {label padded to 14 columns} {value}", so the value starts at the same column everywhere.
  const lines = strip(out.text()).split("\n").filter((l) => /^│ {2}\S/u.test(l));
  assert.ok(lines.length >= 6, `at least 6 data rows (got ${lines.length})`);
  const valueStartCols = lines.map((l) => {
    const m = l.match(/^(│ {2}.*?\s{2,})\S/u); // labels may contain one space, label and value are separated by 2+
    return m ? visualWidth(m[1]) : -1;
  });
  const first = valueStartCols[0];
  assert.ok(first > 0 && valueStartCols.every((c) => c === first), `모든 값 시작 컬럼이 동일해야 함: ${valueStartCols}`);
});

test("printIdeStatus: 설치/미설치/CLI없음 3상태", () => {
  const out = capture();
  printIdeStatus([
    { id: "claude", label: "Claude Code", installed: true, version: "4.0.2", scope: "user", cliMissing: false },
    { id: "cursor", label: "Cursor", installed: false, cliMissing: false },
    { id: "gemini", label: "Gemini CLI", installed: false, cliMissing: true, note: "CLI 없음" },
  ], out);
  const t = strip(out.text());
  assert.match(t, /Claude Code.*설치됨 v4\.0\.2 \(user\)/);
  assert.match(t, /Cursor.*미설치/);
  assert.match(t, /Gemini CLI.*CLI 없음/);
});

test("printInstallKind: 신규 vs 업데이트 + 판정 근거 라인", () => {
  const out = capture();
  printInstallKind({ currentTemplateVersion: "", templateVersion: "4.0.3" }, out);
  const t1 = strip(out.text());
  assert.match(t1, /신규 통합/);
  assert.match(t1, /이전 통합 기록이 없어/, "왜 신규인지 근거를 밝힌다");

  const out2 = capture();
  printInstallKind({ currentTemplateVersion: "3.0.188", templateVersion: "4.0.3" }, out2);
  const t2 = strip(out2.text());
  assert.match(t2, /업데이트: 템플릿 v3\.0\.188 → v4\.0\.3/);
  assert.match(t2, /이전 통합 기록이 있/, "왜 업데이트인지 근거를 밝힌다");
});

test("collectIdeStatuses: 어댑터 전체 순회 (예외 없음)", () => {
  // 아무것도 설치 안 된 io 스텁 — which 전부 null
  const io = { which: () => null, run: () => ({ ok: false, stdout: "" }), home: () => "/nonexistent-home", log: () => {} };
  const statuses = collectIdeStatuses(io);
  assert.ok(statuses.length >= 5, "어댑터 5개 이상");
  for (const s of statuses) {
    assert.ok(typeof s.label === "string" && s.label.length > 0);
    assert.ok(typeof s.installed === "boolean");
  }
});

// ---- English output (the default language) ----

test("English: banner shows the language line, cards and install kind use English labels", () => {
  setLang("en", "system");
  const out = capture();
  printBanner({ version: "4.0.3", modeLabel: "Interactive installer" }, out);
  const t = strip(out.text());
  assert.match(t, /Mode {4}: Interactive installer/);
  assert.match(t, /Language: en \(system\)/);

  const out2 = capture();
  printAnalysisCard({
    mode: "full", modeLabel: "Full install", types: ["spring"], version: "1.2.3", branch: "main",
    deployTarget: "docker-ssh", publishTargets: [], includeSecretBackup: false, showOptional: true, paths: new Map(),
  }, out2);
  const card = strip(out2.text());
  assert.match(card, /Summary/);
  assert.match(card, /Type\s+spring/);
  assert.match(card, /Secret backup\s+excluded/);
  assert.match(card, /Publish\s+none/);

  const out3 = capture();
  printInstallKind({ currentTemplateVersion: "3.0.188", templateVersion: "4.0.3" }, out3);
  assert.match(strip(out3.text()), /Update: template v3\.0\.188 to v4\.0\.3/);
  const out4 = capture();
  printInstallKind({ currentTemplateVersion: "", templateVersion: "4.0.3" }, out4);
  assert.match(strip(out4.text()), /New install: first install in this project/);

  const out5 = capture();
  printBannerCompact({ version: "4.0.3", mode: "full" }, out5);
  assert.match(strip(out5.text()), /projectops v4\.0\.3 \(full mode, --force\)/);

  const out6 = capture();
  printDetectionLog({ types: ["spring"], version: "1.2.3", branch: "main" }, out6);
  assert.match(strip(out6.text()), /build\.gradle found, spring detected/);
  assert.match(strip(out6.text()), /version: v1\.2\.3, branch: main/);
});
