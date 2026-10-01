// version.yml deploy 블록 위치·보존 회귀 테스트 (#670)
// deploy 블록이 metadata 와 template 사이에 끼면 template 이 deploy 의 자식이 되어 구조가 깨진다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { buildVersionYml, parseExisting, parseDeployBlock } from "../src/core/version-yml.js";
import { upsertDeployBlock } from "../src/commands/workflows.js";

const deployValues = () => new Map([["spring", new Map([["SERVICE_DOMAIN", "example.com"]])]]);
const build = (dv = deployValues()) => buildVersionYml({
  version: "1.0.0", types: ["spring"], branch: "main", now: "n", today: "t",
  deployValues: dv,
  templateOptions: { templateVersion: "4.0.0", deployTarget: "docker-ssh", publishTargets: [], includeSecretBackup: false, optionsDate: "t" },
});

test("deploy 블록은 template 을 가로채지 않는다 — template 은 metadata 의 2칸 자식 (#670)", () => {
  const yml = build();
  const lines = yml.split("\n");
  const tpl = lines.findIndex((l) => l === "  template:");
  const dep = lines.findIndex((l) => l.startsWith("deploy:"));
  assert.ok(tpl > 0 && dep > 0);
  assert.ok(dep > tpl, "deploy 는 template 뒤의 별도 최상위 키");
  // template 과 그 하위 사이에 최상위 키가 끼지 않아야 한다
  const between = lines.slice(lines.findIndex((l) => l === "metadata:"), tpl);
  assert.ok(!between.some((l) => /^\S/.test(l) && !l.startsWith("metadata:")), "metadata~template 사이에 최상위 키 없음");
  assert.equal(parseExisting(yml).templateVersion, "4.0.0");
  assert.equal(parseExisting(yml).options.deploy, "docker-ssh");
});

test("parseDeployBlock: 값을 읽고, 구버전 깨진 구조의 template 키는 타입으로 취급하지 않는다 (#670)", () => {
  const broken = [
    'version: "1.0.0"', "metadata:", '  default_branch: "main"', "",
    "deploy:   # 설명", "  spring:", '    SERVICE_DOMAIN: "my.real.com"', "  template:", '    version: "4.0.0"', "",
  ].join("\n");
  const m = parseDeployBlock(broken);
  assert.equal(m.get("spring").get("SERVICE_DOMAIN"), "my.real.com");
  assert.equal(m.has("template"), false);
});

test("upsertDeployBlock: 구버전 깨진 구조에서도 template 을 지우지 않는다 (#670)", () => {
  const broken = [
    'version: "1.0.0"', "metadata:", '  default_branch: "main"', "",
    "deploy:", "  spring:", '    SERVICE_DOMAIN: "example.com"', "  template:", '    version: "4.0.0"', "    options:", '      deploy: "docker-ssh"', "",
  ].join("\n");
  const out = upsertDeployBlock(broken, deployValues());
  assert.equal(parseExisting(out).templateVersion, "4.0.0");
  assert.equal((out.match(/^deploy:/gm) || []).length, 1);
});
