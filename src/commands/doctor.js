// doctor 명령 (#558) — 통합 상태·저장소 설정 진단. 읽기 전용, 파일을 건드리지 않는다.
//
// 출력 설계:
//   ① 항목 이름에 purpose("무엇을 위한 설정인지")를 병기한다. `actions: write`만 보고는
//      그게 자기 릴리스 흐름의 무엇을 담당하는지 알 수 없다.
//   ② 도구가 "고쳐야 한다"고 판정하지 않는다. 발견한 사실만 진술하고 그것이 자신에게
//      문제인지는 사용자가 판단한다 — 쓰지 않는 워크플로우의 Secret은 등록할 이유가 없다.
//   ③ 문제 항목만 `현상 → 영향 → 조치` 로 펼치고, 정상 항목은 한 줄로 압축한다.
//   ④ GitHub 설정 화면에 실제로 표시되는 문자열("Read and write permissions" 등)은
//      번역하지 않는다. 번역하면 설명은 읽히지만 정작 화면에서 그 항목을 찾지 못한다.
//
// 원격 점검은 GITHUB_TOKEN이 있을 때만 한다. 없다고 실패시키지 않는다 — 로컬 점검만으로도
// 대부분의 흔한 사고(치환 실패·Secret 누락)를 잡을 수 있다.
import { join } from "node:path";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { PATHS } from "../core/paths.js";
import { parseExisting } from "../core/version-yml.js";
import { verifyInstall } from "../core/verify.js";
import { readBaseline } from "../core/baseline.js";
import { detectRepoName } from "../core/detect-fs.js";
import { detectMigrations } from "../core/migrations/index.js";
import { t } from "../i18n/index.js";

// 언어 전환(withLang 등) 시점에 평가되도록 함수로 둔다
const permPurpose = () => t("doctor.perm.purpose");

// GitHub REST 호출. 실패는 예외가 아니라 {ok:false}로 돌려 진단이 중단되지 않게 한다.
async function gh(path, token) {
  try {
    const res = await fetch(`https://api.github.com${path}`, {
      headers: { Authorization: `token ${token}`, Accept: "application/vnd.github+json",
                 "User-Agent": "projectops-doctor" },
    });
    if (!res.ok) return { ok: false, status: res.status };
    return { ok: true, data: await res.json() };
  } catch (e) {
    return { ok: false, error: e?.message || String(e) };
  }
}

// git remote에서 owner/repo 추출. 없으면 null.
function detectSlug(cwd) {
  try {
    const url = execFileSync("git", ["remote", "get-url", "origin"],
      { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
    const m = url.match(/github\.com[:/]([^/]+)\/([^/.]+)(\.git)?$/);
    return m ? `${m[1]}/${m[2]}` : null;
  } catch {
    return null;
  }
}

// ── 로컬 점검 ─────────────────────────────────────────────────────────
export function localChecks(cwd = ".") {
  const rows = [];
  const add = (r) => rows.push(r);

  const vyPath = join(cwd, PATHS.versionFile);
  const existing = existsSync(vyPath) ? parseExisting(readFileSync(vyPath, "utf8")) : null;

  if (!existing) {
    add({ name: t("doctor.integ.name"), purpose: t("doctor.integ.purpose"), status: "INFO",
          value: t("doctor.integ.noVersionYml"),
          detail: [t("doctor.integ.notIntegrated"),
                   t("doctor.integ.howTo")] });
    return rows; // 통합 전이면 나머지 점검이 의미 없다
  }

  add({ name: t("doctor.integ.name"), purpose: t("doctor.integ.purpose"), status: "OK",
        // 템플릿 버전이 기록돼 있지 않으면 "vunknown" 이 아니라 사람이 읽는 문구로 — 옛 설치는 version.yml 에 이 값이 없다
        value: existing.templateVersion
          ? t("doctor.integ.versions", { tpl: existing.templateVersion, proj: existing.version })
          : t("doctor.integ.versionsNoTemplate", { proj: existing.version }) });

  const wfDir = join(cwd, PATHS.workflowsDir);
  const files = existsSync(wfDir)
    ? readdirSync(wfDir).filter((f) => /\.ya?ml$/.test(f))
    : [];
  add({ name: t("doctor.wf.name"), purpose: t("doctor.wf.purpose"), status: files.length ? "OK" : "WARN",
        value: t("doctor.count", { n: files.length }),
        detail: files.length ? null : [t("doctor.wf.none"),
                                       t("doctor.wf.noneHint")] });

  // 치환·Secret 판정은 설치 후 검증(#549)과 같은 모듈을 쓴다 — 두 곳에 두면 기준이 갈라진다.
  const v = verifyInstall(cwd);
  add({
    name: t("doctor.unres.name"), purpose: t("doctor.unres.purpose"),
    status: v.unresolved.length === 0 ? "OK" : "WARN",
    value: v.unresolved.length === 0 ? t("doctor.none") : t("doctor.cases", { n: v.unresolved.length }),
    detail: v.unresolved.length === 0 ? null : [
      t("doctor.unres.intro"),
      ...v.unresolved.slice(0, 8).map((u) => `  ${u.filename}:${u.line}  ${u.token}`),
      ...(v.unresolved.length > 8 ? [t("doctor.unres.more", { n: v.unresolved.length - 8 })] : []),
      t("doctor.unres.outro"),
    ],
  });

  const secretNames = [...v.secrets.keys()];
  add({
    name: t("doctor.sec.name"), purpose: t("doctor.sec.purpose"),
    status: "INFO", value: secretNames.length ? t("doctor.count", { n: secretNames.length }) : t("doctor.none"),
    detail: secretNames.length ? [
      ...secretNames.map((n) => t("doctor.sec.line", { name: n, n: v.secrets.get(n).length })),
      t("doctor.sec.skipUnused"),
    ] : null,
  });

  // AI 요약 키 (#569) — "등록했는데 되는 건가?"를 확인할 수단이 없었다.
  // 로컬에서는 저장소 Secret을 읽을 수 없으므로, 어떤 이름을 쓰면 되는지와
  // 등록하지 않아도 무방하다는 사실을 알려준다. 실제 등록 여부는 원격 점검이 본다.
  const AI_KEY_NAMES = ["GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY"];
  const hasSummaryWf = files.some((f) => /AI-PR-SUMMARY|RELEASE-CHANGELOG/.test(f));
  if (hasSummaryWf) {
    add({
      name: t("doctor.ai.name"), purpose: t("doctor.ai.purpose"),
      status: "INFO", value: t("doctor.ai.optional"),
      detail: [
        t("doctor.ai.l1"),
        t("doctor.ai.l2"),
        t("doctor.ai.gemini"),
        t("doctor.ai.groq"),
        t("doctor.ai.mistral"),
        t("doctor.ai.paid"),
        t("doctor.ai.l3"),
      ],
    });
  }

  // 워크플로우 파일의 permissions 선언 점검 (#558).
  // 저장소 설정(Settings > Actions)은 "요청할 수 있는 최대 범위"이고, 워크플로우의
  // permissions 블록은 "실제로 요청한 범위"다. 둘은 다른 층이라 저장소 설정이 정상이어도
  // 선언이 빠지면 API가 403을 준다 — #555가 정확히 그 사고였다.
  const needsActionsWrite = [];
  for (const f of files) {
    const body = readFileSync(join(wfDir, f), "utf8");
    if (!body.includes("dispatch_downstream.py")) continue;     // 다른 워크플로우를 깨우는 파일만
    const perm = body.match(/^permissions:\n((?:\s+.*\n)+)/m);
    const hasActionsWrite = perm ? /^\s+actions:\s*write/m.test(perm[1]) : false;
    if (!hasActionsWrite) needsActionsWrite.push(f);
  }
  if (files.length) {
    add({
      name: t("doctor.pd.name"), purpose: t("doctor.pd.purpose"),
      status: needsActionsWrite.length ? "WARN" : "OK",
      value: needsActionsWrite.length ? t("doctor.pd.missing", { n: needsActionsWrite.length }) : t("doctor.ok"),
      detail: needsActionsWrite.length ? [
        ...needsActionsWrite.map((f) => `  ${f}`),
        t("doctor.pd.l1"),
        t("doctor.pd.l2"),
        t("doctor.pd.l3"),
      ] : null,
    });
  }

  // 은퇴한 구세대 워크플로우 (#809) — 업데이트는 감지만 하고 남겨 두므로 신형과 함께 돈다.
  // 예전엔 로그에만 남아 doctor 가 "문제 없음"이라 했다.
  const legacy = detectMigrations(cwd).confirm;
  add({
    name: t("doctor.legacy.name"), purpose: t("doctor.legacy.purpose"),
    status: legacy.length ? "WARN" : "OK",
    value: legacy.length ? t("doctor.count", { n: legacy.length }) : t("doctor.none"),
    detail: legacy.length ? [
      ...legacy.map((e) => `  ${e.file}${e.replacedBy ? `  →  ${e.replacedBy}` : ""}`),
      t("doctor.legacy.l1"),
      ...legacy.map((e) => `  git rm .github/workflows/${e.file}`),
      t("doctor.legacy.l2"),
    ] : null,
  });

  const baseline = readBaseline(cwd);
  add({
    name: t("doctor.bl.name"), purpose: t("doctor.bl.purpose"),
    status: baseline ? "OK" : "INFO",
    value: baseline ? t("doctor.bl.recorded", { n: Object.keys(baseline.files).length }) : t("doctor.none"),
    detail: baseline ? null : [
      t("doctor.bl.l1"),
      t("doctor.bl.l2"),
    ],
  });

  return rows;
}

// ── 원격 점검 ─────────────────────────────────────────────────────────
// permissions 블록을 한 번도 선언하지 않은 워크플로우 — 이때만 저장소 기본 권한(Settings)이 그대로 적용된다.
// 선언이 있으면 저장소 기본값이 read 여도 선언한 범위로 동작한다 (조직 read 기본값에서 릴리스 automerge 실측, #723).
export function workflowsWithoutPermissions(cwd = ".") {
  const wfDir = join(cwd, PATHS.workflowsDir);
  if (!existsSync(wfDir)) return [];
  return readdirSync(wfDir).filter((f) => /\.ya?ml$/.test(f))
    .filter((f) => !/^\s*permissions:/m.test(readFileSync(join(wfDir, f), "utf8")));
}

export async function remoteChecks(slug, token, requiredSecrets = [], undeclared = []) {
  const rows = [];
  const add = (r) => rows.push(r);

  const perm = await gh(`/repos/${slug}/actions/permissions/workflow`, token);
  if (!perm.ok) {
    add({ name: "Workflow permissions", purpose: permPurpose(), status: "INFO",
          value: perm.status === 403 ? t("doctor.rm.noAccess") : t("doctor.rm.failed"),
          detail: [t("doctor.rm.permNoAdmin"),
                   t("doctor.rm.permCheck")] });
  } else if (perm.data?.default_workflow_permissions === "write") {
    add({ name: "Workflow permissions", purpose: permPurpose(), status: "OK",
          value: "Read and write permissions" });
  } else if (undeclared.length === 0) {
    // 모든 워크플로우가 permissions 를 스스로 선언 → 저장소 기본값(read)은 실제 동작에 영향이 없다
    add({ name: "Workflow permissions", purpose: permPurpose(), status: "INFO",
          value: t("doctor.rm.roOk"),
          detail: [t("doctor.rm.roOkDetail")] });
  } else {
    add({
      name: "Workflow permissions", purpose: permPurpose(), status: "WARN",
      value: t("doctor.rm.roWarn"),
      detail: [
        t("doctor.rm.l1"),
        ...undeclared.map((f) => `  ${f}`),
        t("doctor.rm.fix1"),
        t("doctor.rm.fix2"),
      ],
    });
  }

  const repo = await gh(`/repos/${slug}`, token);
  if (repo.ok) {
    const allowed = repo.data?.allow_merge_commit === true;
    add({
      name: t("doctor.mc.name"), purpose: t("doctor.mc.purpose"),
      status: allowed ? "OK" : "WARN",
      value: allowed ? t("doctor.mc.on") : t("doctor.mc.off"),
      detail: allowed ? null : [
        t("doctor.mc.l1"),
        t("doctor.mc.l2"),
        t("doctor.mc.fix"),
      ],
    });
  }

  if (requiredSecrets.length) {
    const sec = await gh(`/repos/${slug}/actions/secrets?per_page=100`, token);
    if (!sec.ok) {
      add({ name: t("doctor.sr.name"), purpose: t("doctor.sr.purpose"), status: "INFO",
            value: t("doctor.rm.noAccess"),
            detail: [t("doctor.sr.noAccess")] });
    } else {
      const have = new Set((sec.data?.secrets || []).map((s) => s.name));

      // AI 요약 키가 실제로 등록돼 있는지 (#569) — 있으면 어느 서비스인지까지 보여준다.
      const AI_KEYS = { GEMINI_API_KEY: "Gemini", OPENAI_API_KEY: "OpenAI", ANTHROPIC_API_KEY: "Anthropic",
                        GROQ_API_KEY: "Groq", MISTRAL_API_KEY: "Mistral", MODEL_API_KEY: t("doctor.air.legacy") };
      const foundAi = Object.entries(AI_KEYS).filter(([n]) => have.has(n));
      rows.push({
        name: t("doctor.air.name"), purpose: t("doctor.ai.purpose"),
        status: "INFO",
        value: foundAi.length ? foundAi.map(([n, label]) => `${n} (${label})`).join(", ") : t("doctor.air.none"),
        detail: foundAi.length ? null : [
          t("doctor.air.l1"),
          t("doctor.air.l2"),
        ],
      });
      // AI 키는 위에서 따로 안내하는 선택 항목이다 — '배포에 필요한 값' 미등록 목록에 섞으면 필수처럼 읽힌다 (#723)
      const missing = requiredSecrets.filter((n) => !have.has(n) && !(n in AI_KEYS));
      add({
        name: t("doctor.sr.name"), purpose: t("doctor.sr.purpose"),
        status: missing.length ? "WARN" : "OK",
        value: missing.length ? t("doctor.sr.missing", { n: missing.length }) : t("doctor.sr.all"),
        detail: missing.length ? [
          ...missing.map((n) => `  ${n}`),
          t("doctor.sr.l1"),
          t("doctor.sr.fix"),
        ] : null,
      });
    }
  }

  return rows;
}

// ── 렌더 ──────────────────────────────────────────────────────────────
const ICON = { OK: "✅", WARN: "⚠️", FAIL: "❌", INFO: "ℹ️" };

export function renderRows(rows, write = (s) => process.stderr.write(s + "\n")) {
  const head = (r) => `${r.name}${r.purpose ? ` - ${r.purpose}` : ""}`;
  for (const r of rows) {
    write(`${ICON[r.status] || "·"} ${head(r)}: ${r.value}`);
    // 정상 항목은 한 줄로 압축한다. 펼치는 것은 사용자가 무언가 해야 할 때뿐이다.
    if (r.detail && r.status !== "OK") {
      for (const line of r.detail) write(`     ${line}`);
      write("");
    }
  }
  const warn = rows.filter((r) => r.status === "WARN" || r.status === "FAIL").length;
  write("");
  write(warn === 0
    ? t("doctor.render.clean")
    : t("doctor.render.warn", { n: warn }));
  return warn;
}

// 진입점. 반환: 살펴볼 항목 수 (exit code로 쓰지 않는다 — 진단은 실패가 아니다)
export async function runDoctor({ cwd = ".", token = process.env.GITHUB_TOKEN || "" } = {}) {
  const write = (s) => process.stderr.write(s + "\n");
  write("");
  write(t("doctor.title"));
  write("────────────────────────────────────────");
  write("");

  const rows = localChecks(cwd);
  const slug = detectSlug(cwd);
  const repoName = detectRepoName(cwd);
  rows.push({ name: t("doctor.gh.name"), purpose: t("doctor.gh.purpose"), status: slug ? "OK" : "INFO",
              value: slug || t("doctor.gh.noOrigin", { folder: repoName ? t("doctor.gh.folder", { name: repoName }) : "" }),
              detail: slug ? null : [t("doctor.gh.noRemote")] });

  if (slug && token) {
    const v = verifyInstall(cwd);
    rows.push(...await remoteChecks(slug, token, [...v.secrets.keys()], workflowsWithoutPermissions(cwd)));
  } else if (slug) {
    rows.push({ name: t("doctor.skip.name"), purpose: t("doctor.skip.purpose"), status: "INFO",
                value: t("doctor.skip.value"),
                detail: [t("doctor.skip.l1"),
                         "  GITHUB_TOKEN=ghp_... npx projectops --mode doctor"] });
  }

  return renderRows(rows, write);
}
