// 스토어 다국어 설정 감지 (#843): store_locales 없이 여러 언어에 한 문구를 올리는 레포를 찾아 알리기만 한다.
// 동작·version.yml 은 바꾸지 않는다. 결과는 완료 화면 한 줄 + 마이그레이션 가이드 체크리스트 한 항목.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

// 언어 폴더 이름 모양 (ko, ko-KR, en-US, zh-Hans)
const LOCALE_NAME = /^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$/;
// DELIVER_LOCALES 대입 (yaml `KEY: "a,b"`, 셸 `KEY=a,b`, Ruby `ENV["KEY"] = "a,b"`). `||` 기본값은 대입이 아니라 제외
const DELIVER_LOCALES_ASSIGN = /DELIVER_LOCALES["']?\]?\s*[:=]\s*["']?([A-Za-z0-9_, -]+)/g;
const MINIMUM_LOCALE_COUNT = 2;

/**
 * 다국어 스토어 신호 3종 수집: DELIVER_LOCALES 2개 이상, Play metadata 언어 폴더, release-notes 언어 폴더
 * storeLocales 가 이미 있거나(null 아님) 신호가 없으면 null
 */
export function detectMultiLocaleStore({ root, flutterPath = ".", storeLocales = null }) {
  if (storeLocales != null) return null;
  const appRoot = join(root, flutterPath || ".");
  const signals = [
    ...findDeliverLocales(root, appRoot),
    ...findLocaleDirectories(root, join(appRoot, "android/fastlane/metadata/android"), "play-metadata"),
    ...findLocaleDirectories(root, join(appRoot, "release-notes"), "release-notes"),
  ];
  // 루트와 앱 폴더가 다를 때만 루트 release-notes 도 본다 (같으면 중복)
  if (appRoot !== join(root, ".")) signals.push(...findLocaleDirectories(root, join(root, "release-notes"), "release-notes"));
  if (signals.length === 0) return null;
  const locales = [...new Set(signals.flatMap((s) => s.locales))];
  return { signals, locales };
}

// 워크플로우(.yml/.yaml) + Fastfile(ios·android·루트) 의 DELIVER_LOCALES
function findDeliverLocales(root, appRoot) {
  const candidates = [];
  const workflowsDir = join(root, ".github/workflows");
  if (existsSync(workflowsDir)) {
    for (const name of readdirSync(workflowsDir)) {
      if (/\.ya?ml$/.test(name)) candidates.push(join(workflowsDir, name));
    }
  }
  for (const sub of ["ios/fastlane/Fastfile", "android/fastlane/Fastfile", "fastlane/Fastfile"]) {
    candidates.push(join(appRoot, sub));
  }
  const found = [];
  for (const file of new Set(candidates)) {
    if (!isFile(file)) continue;
    const text = readFileSync(file, "utf8");
    for (const match of text.matchAll(DELIVER_LOCALES_ASSIGN)) {
      const locales = match[1].split(",").map((s) => s.trim()).filter((s) => LOCALE_NAME.test(s));
      if (locales.length >= MINIMUM_LOCALE_COUNT) {
        found.push({ source: "deliver-locales", path: toRelative(root, file), locales });
        break; // 파일당 1건이면 충분
      }
    }
  }
  return found;
}

// <dir>/<lang>/ 폴더가 2개 이상이면 신호 1건
function findLocaleDirectories(root, dir, source) {
  if (!existsSync(dir) || !statSync(dir).isDirectory()) return [];
  const locales = readdirSync(dir)
    .filter((name) => LOCALE_NAME.test(name) && statSync(join(dir, name)).isDirectory())
    .sort();
  return locales.length >= MINIMUM_LOCALE_COUNT ? [{ source, path: toRelative(root, dir), locales }] : [];
}

function isFile(path) {
  return existsSync(path) && statSync(path).isFile();
}

// 화면·가이드 표기는 OS 와 무관하게 / 구분자
function toRelative(root, path) {
  return relative(root, path).split("\\").join("/");
}

/**
 * 진입점(비대화형·대화형) 공통: 기존 레포 + storeLocales 미설정일 때만 감지 > trace 기록 > 결과 반환
 * 신규 설치는 null (알릴 대상은 이미 다국어로 운영 중인 레포)
 */
export function detectStoreLocalesHint({ root, existing, paths, trace = null }) {
  if (!existing) return null;
  const hint = detectMultiLocaleStore({
    root, flutterPath: paths?.get?.("flutter") || ".", storeLocales: existing.options?.storeLocales ?? null,
  });
  trace?.event?.("detect", "store-locales-hint", hint ? "multi-locale" : "none", hint
    ? { locales: hint.locales, signals: hint.signals.map((s) => `${s.source}:${s.path}`) }
    : { storeLocalesSet: existing.options?.storeLocales != null });
  return hint;
}
