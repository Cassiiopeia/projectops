import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import en from "../src/i18n/en.js";
import ko from "../src/i18n/ko.js";
import { normalizeLang, resolveLang, setLang, getLang, t, tEn } from "../src/i18n/index.js";
import { parseArgs, CliError } from "../src/cli/args.js";
import { helpText } from "../src/cli/help.js";

afterEach(() => setLang("en", "default"));

test("normalizeLang: ko variants map to ko, everything else to en, empty is unspecified", () => {
  assert.equal(normalizeLang("ko"), "ko");
  assert.equal(normalizeLang("ko-KR"), "ko");
  assert.equal(normalizeLang("ko_KR.UTF-8"), "ko");
  assert.equal(normalizeLang("en-US"), "en");
  assert.equal(normalizeLang("ja-JP"), "en");
  assert.equal(normalizeLang(""), null);
  assert.equal(normalizeLang(undefined), null);
});

test("resolveLang: flag > env > CI pin > system > default", () => {
  assert.deepEqual(resolveLang({ flag: "ko", env: { PROJECTOPS_LANG: "en" }, locale: "en-US" }), { lang: "ko", source: "flag" });
  assert.deepEqual(resolveLang({ env: { PROJECTOPS_LANG: "ko" }, locale: "en-US" }), { lang: "ko", source: "env" });
  assert.deepEqual(resolveLang({ env: {}, pinEnglish: true, locale: "ko-KR" }), { lang: "en", source: "ci" });
  assert.deepEqual(resolveLang({ env: { CI: "true" }, locale: "ko-KR" }), { lang: "en", source: "ci" });
  assert.deepEqual(resolveLang({ env: {}, locale: "ko-KR" }), { lang: "ko", source: "system" });
  assert.deepEqual(resolveLang({ env: {}, locale: "fr-FR" }), { lang: "en", source: "system" });
  assert.deepEqual(resolveLang({ env: {}, locale: "" }), { lang: "en", source: "default" });
});

test("an explicit flag or env wins even in CI", () => {
  assert.equal(resolveLang({ flag: "ko", pinEnglish: true, env: { CI: "true" } }).lang, "ko");
  assert.equal(resolveLang({ env: { CI: "true", PROJECTOPS_LANG: "ko" } }).lang, "ko");
});

test("t: current language, placeholders, English fallback, unknown key echoes the key", () => {
  setLang("ko");
  assert.equal(t("mode.prompt"), ko["mode.prompt"]);
  assert.match(t("mode.update", { range: "v1" }), /v1/);
  setLang("en");
  assert.equal(t("mode.prompt"), en["mode.prompt"]);
  assert.equal(t("no.such.key"), "no.such.key");
  assert.equal(t("mode.update", {}), en["mode.update"]); // missing var keeps the placeholder
});

test("tEn ignores the active language (run logs stay English)", () => {
  setLang("ko");
  assert.equal(tEn("mode.prompt"), en["mode.prompt"]);
});

test("catalogs have the same keys (ko may not lag behind en for migrated areas)", () => {
  const enKeys = Object.keys(en).sort();
  const koKeys = Object.keys(ko).sort();
  assert.deepEqual(koKeys, enKeys);
});

test("every placeholder in en exists in ko", () => {
  for (const key of Object.keys(en)) {
    const vars = (s) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(",");
    assert.equal(vars(ko[key]), vars(en[key]), `placeholders differ for ${key}`);
  }
});

test("--lang accepts en/ko and rejects others; -y and --yes mean --force", () => {
  assert.equal(parseArgs(["--lang", "ko"]).lang, "ko");
  assert.equal(parseArgs([]).lang, null);
  assert.throws(() => parseArgs(["--lang", "xx"]), CliError);
  assert.equal(parseArgs(["-y"]).force, true);
  assert.equal(parseArgs(["--yes"]).force, true);
});

test("help text exists in both languages and documents --lang", () => {
  assert.match(helpText("en"), /Usage:/);
  assert.match(helpText("ko"), /사용법:/);
  assert.match(helpText("en"), /--lang/);
  assert.match(helpText("ko"), /--lang/);
  setLang("ko");
  assert.equal(getLang(), "ko");
  assert.equal(helpText(), helpText("ko"));
});
