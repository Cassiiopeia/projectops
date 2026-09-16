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

const PERM_PURPOSE = "자동 커밋·태그·후속 워크플로우 실행";

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
    add({ name: "통합 상태", purpose: "이 폴더의 템플릿 설치 여부", status: "INFO",
          value: "version.yml 없음",
          detail: ["이 폴더에는 템플릿이 통합되어 있지 않습니다.",
                   "통합하려면: npx projectops"] });
    return rows; // 통합 전이면 나머지 점검이 의미 없다
  }

  add({ name: "통합 상태", purpose: "이 폴더의 템플릿 설치 여부", status: "OK",
        value: `템플릿 v${existing.templateVersion || "unknown"} / 프로젝트 v${existing.version}` });

  const wfDir = join(cwd, PATHS.workflowsDir);
  const files = existsSync(wfDir)
    ? readdirSync(wfDir).filter((f) => /\.ya?ml$/.test(f))
    : [];
  add({ name: "설치된 워크플로우", purpose: "이 저장소에서 도는 자동화", status: files.length ? "OK" : "WARN",
        value: `${files.length}개`,
        detail: files.length ? null : ["워크플로우가 하나도 없습니다.",
                                       "통합 모드를 workflows 또는 full로 다시 실행해 보세요."] });

  // 치환·Secret 판정은 설치 후 검증(#549)과 같은 모듈을 쓴다 — 두 곳에 두면 기준이 갈라진다.
  const v = verifyInstall(cwd);
  add({
    name: "치환되지 않은 값", purpose: "배포 시점에 실패할 자리",
    status: v.unresolved.length === 0 ? "OK" : "WARN",
    value: v.unresolved.length === 0 ? "없음" : `${v.unresolved.length}건`,
    detail: v.unresolved.length === 0 ? null : [
      "아래 위치에 템플릿 값이 그대로 남아 있습니다.",
      ...v.unresolved.slice(0, 8).map((u) => `  ${u.filename}:${u.line}  ${u.token}`),
      ...(v.unresolved.length > 8 ? [`  … 외 ${v.unresolved.length - 8}건`] : []),
      "그대로 두면 해당 워크플로우가 배포 단계에서 실패합니다. 직접 값을 채워주세요.",
    ],
  });

  const secretNames = [...v.secrets.keys()];
  add({
    name: "필요한 Secret", purpose: "설치된 워크플로우가 요구하는 값",
    status: "INFO", value: secretNames.length ? `${secretNames.length}개` : "없음",
    detail: secretNames.length ? [
      ...secretNames.map((n) => `  ${n}  ← ${v.secrets.get(n).length}개 워크플로우`),
      "쓰지 않는 워크플로우의 값은 등록하지 않아도 됩니다.",
    ] : null,
  });

  // AI 요약 키 (#569) — "등록했는데 되는 건가?"를 확인할 수단이 없었다.
  // 로컬에서는 저장소 Secret을 읽을 수 없으므로, 어떤 이름을 쓰면 되는지와
  // 등록하지 않아도 무방하다는 사실을 알려준다. 실제 등록 여부는 원격 점검이 본다.
  const AI_KEY_NAMES = ["GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY"];
  const hasSummaryWf = files.some((f) => /AI-PR-SUMMARY|RELEASE-CHANGELOG/.test(f));
  if (hasSummaryWf) {
    add({
      name: "AI 요약 키", purpose: "릴리스 노트를 AI로 다듬을지 (선택)",
      status: "INFO", value: "선택 사항",
      detail: [
        "등록하지 않아도 릴리스 노트는 나옵니다 — 커밋 내용을 분석해 만듭니다.",
        "AI가 다듬은 문장을 원하면 아래 중 하나를 저장소 Secret에 등록하세요.",
        "  GEMINI_API_KEY     무료 · https://aistudio.google.com/apikey",
        "  GROQ_API_KEY       무료",
        "  MISTRAL_API_KEY    무료",
        "  OPENAI_API_KEY / ANTHROPIC_API_KEY   유료",
        "등록한 것이 자동으로 쓰입니다. 별도 설정은 필요 없습니다.",
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
      name: "워크플로우 권한 선언", purpose: "다른 워크플로우를 실행할 권한",
      status: needsActionsWrite.length ? "WARN" : "OK",
      value: needsActionsWrite.length ? `${needsActionsWrite.length}건 누락` : "정상",
      detail: needsActionsWrite.length ? [
        ...needsActionsWrite.map((f) => `  ${f}`),
        "다른 워크플로우를 실행하는데 permissions에 'actions: write'가 없습니다.",
        "저장소 설정이 Read and write여도 이 선언이 없으면 API가 403을 반환합니다.",
        "조치: 해당 파일의 permissions 블록에 'actions: write' 추가",
      ] : null,
    });
  }

  const baseline = readBaseline(cwd);
  add({
    name: "업데이트 기준점", purpose: "다음 업데이트가 내 수정을 구분할 근거",
    status: baseline ? "OK" : "INFO",
    value: baseline ? `${Object.keys(baseline.files).length}개 파일 기록됨` : "없음",
    detail: baseline ? null : [
      "기준점이 없어 다음 업데이트는 변경된 파일을 모두 물어봅니다.",
      "통합을 한 번 실행하면 기록되고, 그 다음 업데이트부터 내 수정과 템플릿 개선을 구분합니다.",
    ],
  });

  return rows;
}

// ── 원격 점검 ─────────────────────────────────────────────────────────
export async function remoteChecks(slug, token, requiredSecrets = []) {
  const rows = [];
  const add = (r) => rows.push(r);

  const perm = await gh(`/repos/${slug}/actions/permissions/workflow`, token);
  if (!perm.ok) {
    add({ name: "Workflow permissions", purpose: PERM_PURPOSE, status: "INFO",
          value: perm.status === 403 ? "조회 권한 없음" : "조회 실패",
          detail: ["토큰에 저장소 관리 권한이 없어 확인하지 못했습니다.",
                   "Settings > Actions > General > Workflow permissions 에서 직접 확인하세요."] });
  } else if (perm.data?.default_workflow_permissions === "write") {
    add({ name: "Workflow permissions", purpose: PERM_PURPOSE, status: "OK",
          value: "Read and write permissions" });
  } else {
    add({
      name: "Workflow permissions", purpose: PERM_PURPOSE, status: "WARN",
      value: "Read repository contents permission (읽기 전용)",
      detail: [
        "워크플로우가 저장소에 쓰거나 다른 워크플로우를 실행할 수 없습니다.",
        "버전 확정 커밋·릴리스 태그·후속 워크플로우 실행이 전부 실패합니다.",
        "조치: Settings > Actions > General > Workflow permissions",
        "      → 'Read and write permissions' 선택",
      ],
    });
  }

  const repo = await gh(`/repos/${slug}`, token);
  if (repo.ok) {
    const allowed = repo.data?.allow_merge_commit === true;
    add({
      name: "merge commit 허용", purpose: "릴리스 PR 자동 머지 조건",
      status: allowed ? "OK" : "WARN",
      value: allowed ? "허용됨" : "꺼져 있음",
      detail: allowed ? null : [
        "릴리스 PR 자동 머지는 merge commit 방식을 사용합니다.",
        "꺼져 있으면 자동 머지가 실패하고 PR이 열린 채 남습니다.",
        "조치: Settings > General > Pull Requests → 'Allow merge commits' 체크",
      ],
    });
  }

  if (requiredSecrets.length) {
    const sec = await gh(`/repos/${slug}/actions/secrets?per_page=100`, token);
    if (!sec.ok) {
      add({ name: "Secret 등록 여부", purpose: "배포에 필요한 값", status: "INFO",
            value: "조회 권한 없음",
            detail: ["토큰에 Secret 조회 권한이 없어 확인하지 못했습니다."] });
    } else {
      const have = new Set((sec.data?.secrets || []).map((s) => s.name));

      // AI 요약 키가 실제로 등록돼 있는지 (#569) — 있으면 어느 서비스인지까지 보여준다.
      const AI_KEYS = { GEMINI_API_KEY: "Gemini", OPENAI_API_KEY: "OpenAI", ANTHROPIC_API_KEY: "Anthropic",
                        GROQ_API_KEY: "Groq", MISTRAL_API_KEY: "Mistral", MODEL_API_KEY: "구 이름(서비스 자동 추정)" };
      const foundAi = Object.entries(AI_KEYS).filter(([n]) => have.has(n));
      rows.push({
        name: "AI 요약 키 등록", purpose: "릴리스 노트를 AI로 다듬을지 (선택)",
        status: "INFO",
        value: foundAi.length ? foundAi.map(([n, label]) => `${n} (${label})`).join(", ") : "없음 — 커밋 분석으로 동작",
        detail: foundAi.length ? null : [
          "등록하지 않아도 릴리스 노트는 정상적으로 나옵니다.",
          "AI를 쓰려면 GEMINI_API_KEY(무료)를 등록하세요 — https://aistudio.google.com/apikey",
        ],
      });
      const missing = requiredSecrets.filter((n) => !have.has(n));
      add({
        name: "Secret 등록 여부", purpose: "배포에 필요한 값",
        status: missing.length ? "WARN" : "OK",
        value: missing.length ? `${missing.length}개 미등록` : "전부 등록됨",
        detail: missing.length ? [
          ...missing.map((n) => `  ${n}`),
          "해당 워크플로우를 쓰지 않는다면 등록하지 않아도 됩니다.",
          "조치: Settings > Secrets and variables > Actions > New repository secret",
        ] : null,
      });
    }
  }

  return rows;
}

// ── 렌더 ──────────────────────────────────────────────────────────────
const ICON = { OK: "✅", WARN: "⚠️", FAIL: "❌", INFO: "ℹ️" };

export function renderRows(rows, write = (s) => process.stderr.write(s + "\n")) {
  const head = (r) => `${r.name}${r.purpose ? ` — ${r.purpose}` : ""}`;
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
    ? "확인된 문제 없음."
    : `살펴볼 항목 ${warn}건. 위 조치를 참고하세요 (쓰지 않는 기능이라면 넘어가도 됩니다).`);
  return warn;
}

// 진입점. 반환: 살펴볼 항목 수 (exit code로 쓰지 않는다 — 진단은 실패가 아니다)
export async function runDoctor({ cwd = ".", token = process.env.GITHUB_TOKEN || "" } = {}) {
  const write = (s) => process.stderr.write(s + "\n");
  write("");
  write("projectops doctor — 통합 상태 및 저장소 설정 진단");
  write("────────────────────────────────────────");
  write("");

  const rows = localChecks(cwd);
  const slug = detectSlug(cwd);
  const repoName = detectRepoName(cwd);
  rows.push({ name: "GitHub 원격", purpose: "점검 대상 저장소", status: slug ? "OK" : "INFO",
              value: slug || `origin 없음${repoName ? ` (폴더명: ${repoName})` : ""}`,
              detail: slug ? null : ["원격 저장소를 찾지 못해 저장소 설정은 점검하지 않습니다."] });

  if (slug && token) {
    const v = verifyInstall(cwd);
    rows.push(...await remoteChecks(slug, token, [...v.secrets.keys()]));
  } else if (slug) {
    rows.push({ name: "저장소 설정 점검", purpose: "권한·머지 방식·Secret", status: "INFO",
                value: "건너뜀 (토큰 없음)",
                detail: ["GITHUB_TOKEN 환경변수를 주면 저장소 설정까지 점검합니다.",
                         "  GITHUB_TOKEN=ghp_... npx projectops --mode doctor"] });
  }

  return renderRows(rows, write);
}
