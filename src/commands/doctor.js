// doctor command (#558) — diagnoses integration state and repo settings. Read-only, touches no files.
//
// Output design:
//   ① Item names carry their purpose ("what the setting is for"). Seeing only `actions: write`
//      does not tell what it handles in your own release flow.
//   ② The tool does not rule "you must fix this". It states only the facts found; whether that is a
//      problem for you is the user's call — there is no reason to register secrets for workflows you do not use.
//   ③ Only problem items expand as `symptom → impact → action`; healthy items collapse to one line.
//   ④ Strings actually shown on GitHub settings screens ("Read and write permissions", etc.)
//      are not translated. Translated, the explanation reads fine but the item cannot be found on screen.
//
// Remote checks run only with GITHUB_TOKEN. Missing it is not a failure — local checks alone
// catch most common accidents (substitution failures, missing secrets).
import { join } from "node:path";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { PATHS } from "../core/paths.js";
import { parseExisting } from "../core/version-yml.js";
import { verifyInstall } from "../core/verify.js";
import { readBaseline } from "../core/baseline.js";
import { detectRepoName } from "../core/detect-fs.js";
import { detectMigrations } from "../core/migrations/index.js";
import { scanPlaceholderTriggers } from "../core/placeholder-triggers.js";
import { t } from "../i18n/index.js";

// Kept as a function so it is evaluated at language switch time (withLang, etc.)
const permPurpose = () => t("doctor.perm.purpose");

const GITHUB_CHECK_TIMEOUT_MILLISECONDS = 5000;

// GitHub REST call. Failure returns {ok:false} instead of throwing, so the diagnosis does not stop.
async function gh(path, token) {
  try {
    const res = await fetch(`https://api.github.com${path}`, {
      headers: { Authorization: `token ${token}`, Accept: "application/vnd.github+json",
                 "User-Agent": "projectops-doctor" },
      signal: AbortSignal.timeout(GITHUB_CHECK_TIMEOUT_MILLISECONDS),   // Keeps the diagnosis from hanging on a blocked network
    });
    if (!res.ok) return { ok: false, status: res.status };
    return { ok: true, data: await res.json() };
  } catch (e) {
    return { ok: false, error: e?.message || String(e) };
  }
}

// Extract owner/repo from the git remote. null if missing.
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

// ── Local checks ─────────────────────────────────────────────────────────
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
    return rows; // Before integration the remaining checks are meaningless
  }

  add({ name: t("doctor.integ.name"), purpose: t("doctor.integ.purpose"), status: "OK",
        // Without a recorded template version, show readable text instead of "vunknown" — old installs lack this value in version.yml
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

  // Substitution and secret checks use the same module as post-install verification (#549) — two copies would split the criteria.
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

  // Automatic trigger + sample values (#662) — your-project-style values slip past the unreplaced token check and keep producing failed runs
  const autoPlaceholders = scanPlaceholderTriggers(wfDir);
  add({
    name: t("doctor.ph.name"), purpose: t("doctor.ph.purpose"),
    status: autoPlaceholders.length ? "WARN" : "OK",
    value: autoPlaceholders.length ? t("doctor.count", { n: autoPlaceholders.length }) : t("doctor.none"),
    detail: autoPlaceholders.length ? [
      t("doctor.ph.l1"),
      ...autoPlaceholders.flatMap((w) => [
        `  ${w.file}  (${w.triggers.join(", ")})`,
        ...w.values.map((p) => `    ${w.file}:${p.line}  ${p.key}: "${p.value}"`),
      ]),
      t("doctor.ph.fix"),
    ] : null,
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

  // AI summary keys (#569) — there was no way to check "I registered it, does it work?".
  // Repo secrets cannot be read locally, so this tells which names to use
  // and that not registering is fine. Whether they are actually registered is checked remotely.
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

  // Check permissions declarations in workflow files (#558).
  // Repo settings (Settings > Actions) are "the maximum that can be requested", while a workflow's
  // permissions block is "what is actually requested". They are different layers, so even with healthy repo settings
  // a missing declaration gets a 403 from the API — exactly the #555 accident.
  const needsActionsWrite = [];
  for (const f of files) {
    const body = readFileSync(join(wfDir, f), "utf8");
    // Only files that wake other workflows — a mention in a comment line (describing the woken side) is not a call
    const code = body.split("\n").filter((line) => !/^\s*#/.test(line)).join("\n");
    if (!code.includes("dispatch_downstream.py")) continue;
    const perm = body.match(/^permissions:\r?\n((?:\s+.*\r?\n)+)/m);
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

  // Retired old-generation workflows (#809) — updates only detect and leave them, so they run alongside the new ones.
  // Logging alone would make doctor report "no problems", so they are caught here.
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

// ── Remote checks ─────────────────────────────────────────────────────────
// Workflows that never declare a permissions block — only then do the repo default permissions (Settings) apply as is.
// With a declaration, it runs with the declared scope even if the repo default is read (measured on release automerge with an org read default, #723).
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
    // Every workflow declares permissions itself → the repo default (read) does not affect actual behavior
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

      // Whether AI summary keys are actually registered (#569) — if so, also shows which service.
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
      // AI keys are optional items covered separately above — mixing them into the unregistered 'needed for deploy' list makes them read as required (#723)
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

// ── Render ──────────────────────────────────────────────────────────────
const ICON = { OK: "✅", WARN: "⚠️", FAIL: "❌", INFO: "ℹ️" };

export function renderRows(rows, write = (s) => process.stderr.write(s + "\n")) {
  const head = (r) => `${r.name}${r.purpose ? ` - ${r.purpose}` : ""}`;
  for (const r of rows) {
    write(`${ICON[r.status] || "·"} ${head(r)}: ${r.value}`);
    // Healthy items collapse to one line. Expand only when the user needs to do something.
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

// Entry point. Returns the number of items to look at (not used as the exit code — a diagnosis is not a failure)
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
