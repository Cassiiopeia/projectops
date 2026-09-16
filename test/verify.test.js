import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { scanUnsubstituted, collectRequiredSecrets, verifyInstall, OPTIONAL_SECRETS } from "../src/core/verify.js";

// 워크플로우 폴더를 만들고 파일을 채운다. 반환: { root, wfDir }
function fixture(files) {
  const root = mkdtempSync(join(tmpdir(), "verify-"));
  const wfDir = join(root, ".github", "workflows");
  mkdirSync(wfDir, { recursive: true });
  for (const [name, content] of Object.entries(files)) writeFileSync(join(wfDir, name), content, "utf8");
  return { root, wfDir };
}

// ── 미치환 토큰 스캔 ──────────────────────────────────────────────────
test("scanUnsubstituted: 남은 토큰을 파일·줄번호와 함께 보고", () => {
  const { wfDir } = fixture({
    "A.yaml": 'jobs:\n  build:\n    run: echo __DEPLOY_PORT__\n',
  });
  const found = scanUnsubstituted(wfDir);
  assert.equal(found.length, 1);
  assert.equal(found[0].filename, "A.yaml");
  assert.equal(found[0].line, 3);
  assert.equal(found[0].token, "__DEPLOY_PORT__");
});

test("scanUnsubstituted: heredoc 구분자(__SUH_*__)는 치환 대상이 아니므로 제외", () => {
  // 값이 아니라 문법이다. 이걸 세면 정상 설치가 매번 경고를 뿜는다.
  const { wfDir } = fixture({
    "A.yaml": "run: cat <<'__SUH_FILE_CONTENT_EOF__'\ndata\n__SUH_FILE_CONTENT_EOF__\n",
  });
  assert.deepEqual(scanUnsubstituted(wfDir), []);
});

test("scanUnsubstituted: 주석 줄은 실행되지 않으므로 제외", () => {
  // 템플릿에는 선택 스텝이 통째로 주석 처리돼 들어 있다.
  const { wfDir } = fixture({
    "A.yaml": "# run: echo __SERVICE_DOMAIN__\n    #   __JAVA_VERSION__\n",
  });
  assert.deepEqual(scanUnsubstituted(wfDir), []);
});

test("scanUnsubstituted: 한 줄에 여러 토큰이면 각각 보고", () => {
  const { wfDir } = fixture({ "A.yaml": "run: cp __APPLICATION_YML_PATH__ __APPLICATION_YML_DIR__\n" });
  const found = scanUnsubstituted(wfDir);
  assert.equal(found.length, 2);
  assert.deepEqual(found.map((f) => f.token).sort(),
    ["__APPLICATION_YML_DIR__", "__APPLICATION_YML_PATH__"]);
});

test("scanUnsubstituted: 치환이 끝난 워크플로우는 빈 배열", () => {
  const { wfDir } = fixture({ "A.yaml": "run: echo 8080\nname: myapp\n" });
  assert.deepEqual(scanUnsubstituted(wfDir), []);
});

test("scanUnsubstituted: 폴더가 없으면 빈 배열 (설치 실패로 오인시키지 않는다)", () => {
  assert.deepEqual(scanUnsubstituted(join(tmpdir(), "no-such-dir-verify")), []);
});

test("scanUnsubstituted: filenames를 주면 그 파일만 검사", () => {
  const { wfDir } = fixture({
    "A.yaml": "run: echo __DEPLOY_PORT__\n",
    "B.yaml": "run: echo __JAVA_VERSION__\n",
  });
  const found = scanUnsubstituted(wfDir, ["B.yaml"]);
  assert.equal(found.length, 1);
  assert.equal(found[0].filename, "B.yaml");
});

// ── 필요한 Secret 수집 ────────────────────────────────────────────────
test("collectRequiredSecrets: 사용 파일과 함께 이름 오름차순으로 수집", () => {
  const { wfDir } = fixture({
    "B.yaml": "  host: ${{ secrets.SERVER_HOST }}\n",
    "A.yaml": "  key: ${{ secrets.SSH_KEY }}\n  host: ${{ secrets.SERVER_HOST }}\n",
  });
  const got = collectRequiredSecrets(wfDir);
  assert.deepEqual([...got.keys()], ["SERVER_HOST", "SSH_KEY"]);
  assert.deepEqual(got.get("SERVER_HOST"), ["A.yaml", "B.yaml"]);
});

test("collectRequiredSecrets: GITHUB_TOKEN은 자동 주입이라 제외", () => {
  const { wfDir } = fixture({ "A.yaml": "  token: ${{ secrets.GITHUB_TOKEN }}\n" });
  assert.equal(collectRequiredSecrets(wfDir).size, 0);
});

test("collectRequiredSecrets: 폴백이 있는 선택 secret은 제외", () => {
  // 필수와 섞으면 "등록해야 동작합니다" 안내 자체를 못 믿게 된다.
  const { wfDir } = fixture({ "A.yaml": "  key: ${{ secrets.MODEL_API_KEY }}\n" });
  assert.ok(OPTIONAL_SECRETS.has("MODEL_API_KEY"));
  assert.equal(collectRequiredSecrets(wfDir).size, 0);
});

test("collectRequiredSecrets: 주석 안의 secret은 제외", () => {
  // 쓰지도 않는 값을 "등록하세요"라고 안내하게 된다.
  const { wfDir } = fixture({ "A.yaml": "# key: ${{ secrets.UNUSED_EXAMPLE }}\n" });
  assert.equal(collectRequiredSecrets(wfDir).size, 0);
});

test("collectRequiredSecrets: 같은 파일에서 중복 참조해도 파일명은 한 번만", () => {
  const { wfDir } = fixture({
    "A.yaml": "  a: ${{ secrets.SERVER_HOST }}\n  b: ${{ secrets.SERVER_HOST }}\n",
  });
  assert.deepEqual(collectRequiredSecrets(wfDir).get("SERVER_HOST"), ["A.yaml"]);
});

test("collectRequiredSecrets: 밑줄로 시작하는 이름도 정규식이 잡는다", () => {
  const { wfDir } = fixture({ "A.yaml": "  t: ${{ secrets._CUSTOM_TOKEN }}\n" });
  assert.deepEqual([...collectRequiredSecrets(wfDir).keys()], ["_CUSTOM_TOKEN"]);
});

test("collectRequiredSecrets: _GITHUB_PAT_TOKEN은 선택이라 제외 (#551)", () => {
  // PAT 없이도 릴리스가 완주한다 — GITHUB_TOKEN으로 머지하고 후속은 dispatch로 깨운다.
  // 필수로 안내하면 등록하지 않아도 되는 값을 만들게 한다.
  const { wfDir } = fixture({ "A.yaml": "  t: ${{ secrets._GITHUB_PAT_TOKEN }}\n" });
  assert.ok(OPTIONAL_SECRETS.has("_GITHUB_PAT_TOKEN"));
  assert.equal(collectRequiredSecrets(wfDir).size, 0);
});

// ── 통합 진입점 ───────────────────────────────────────────────────────
test("verifyInstall: targetRoot 기준으로 워크플로우 폴더를 찾아 검사", () => {
  const { root } = fixture({
    "A.yaml": "  run: echo __DEPLOY_PORT__\n  host: ${{ secrets.SERVER_HOST }}\n",
  });
  const r = verifyInstall(root);
  assert.equal(r.ok, false);
  assert.equal(r.unresolved.length, 1);
  assert.deepEqual([...r.secrets.keys()], ["SERVER_HOST"]);
});

test("verifyInstall: 미치환이 없으면 ok=true", () => {
  const { root } = fixture({ "A.yaml": "  run: echo 8080\n" });
  const r = verifyInstall(root);
  assert.equal(r.ok, true);
  assert.deepEqual(r.unresolved, []);
});
