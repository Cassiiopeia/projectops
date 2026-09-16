// 완료 요약 출력 (.sh print_summary L5438~5626 등가). 전부 stderr.
// ctx: { mode, types:[], version, counters:{ workflows, utilModules } }
import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { WORKFLOW_COMMON_PREFIX } from "../core/paths.js";

const SEPARATOR = "────────────────────────────────────────";

export function printSummary(ctx, targetRoot = ".") {
  const { mode, types = [], version = "", counters = {} } = ctx || {};
  const deployBranchName = ctx?.deployBranch || "develop"; // #477 — 설정된 배포 브랜치명으로 안내
  const deployBranchReady = ctx?.deployBranchReady === true; // #490 — 마법사가 이번 실행에서 존재/생성 확인함
  const err = (s = "") => process.stderr.write(`${s}\n`);
  // 색상은 TTY일 때만 (.sh YELLOW/CYAN/NC 등가)
  const isTty = !!process.stderr.isTTY;
  const BOLD = isTty ? "\u001b[1m" : "";
  const YELLOW = isTty ? "\x1b[1;33m" : "";
  const CYAN = isTty ? "\x1b[0;36m" : "";
  const NC = isTty ? "\x1b[0m" : "";
  const utilModulesCopied = counters.utilModules ?? 0;

  err("");
  err(SEPARATOR);
  err("");
  err("✨ projectops Setup Complete!");
  err("");
  err(SEPARATOR);
  err("");
  err("통합된 기능:");

  // 모드별 체크리스트 (.sh L5449~5481)
  switch (mode) {
    case "full":
      err("  ✅ 버전 관리 시스템 (version.yml)");
      err("  ✅ README.md 자동 버전 업데이트");
      err("  ✅ GitHub Actions 워크플로우");
      if (utilModulesCopied > 0) err(`  ✅ 유틸리티 모듈 (${utilModulesCopied} 개)`);
      err("  ✅ 이슈/PR/Discussion 템플릿");
      err("  ✅ CodeRabbit AI 리뷰 설정");
      err("  ✅ .gitignore 필수 항목");
      err("  ✅ 템플릿 설정 가이드 (SETUP-GUIDE.md)");
      break;
    case "version":
      err("  ✅ 버전 관리 시스템 (version.yml)");
      err("  ✅ README.md 자동 버전 업데이트");
      err("  ✅ .gitignore 필수 항목");
      err("  ✅ 템플릿 설정 가이드 (SETUP-GUIDE.md)");
      break;
    case "workflows":
      err("  ✅ GitHub Actions 워크플로우");
      if (utilModulesCopied > 0) err(`  ✅ 유틸리티 모듈 (${utilModulesCopied} 개)`);
      err("  ✅ 템플릿 설정 가이드 (SETUP-GUIDE.md)");
      break;
    case "issues":
      err("  ✅ 이슈/PR/Discussion 템플릿");
      break;
    case "skills":
      err("  ✅ Agent Skill 설치 (Claude, Cursor, Gemini, Codex, PI)");
      break;
  }

  // skills 모드: 파일/워크플로우 추가 없으므로 간결하게 종료 (.sh L5484~5491)
  if (mode === "skills") {
    err("");
    err("  📖 TEMPLATE REPO: https://github.com/Cassiiopeia/projectops");
    err("");
    err(SEPARATOR);
    err("");
    return;
  }

  err("");
  err("추가된 파일:");
  err(`  📄 version.yml (버전: ${version}, 타입: ${types.join(",")})`);
  err("  📝 README.md (버전 섹션 추가)");
  err("");
  err("추가된 워크플로우:");

  // 실제 복사·교체된 파일 목록만 출력 (#473 — 디렉토리 스캔은 존재 파일 전부를 "새로 설치됨"으로
  // 오표기했고 카운터와 소스가 달라 (0개) 불일치가 났다. 복사 엔진의 copiedFiles가 유일한 소스.)
  const copiedFiles = counters.workflowFiles ?? [];
  const commonWorkflows = copiedFiles.filter((f) => f.startsWith(`${WORKFLOW_COMMON_PREFIX}-`));
  const typeWorkflows = copiedFiles.filter((f) => !f.startsWith(`${WORKFLOW_COMMON_PREFIX}-`));

  if (copiedFiles.length > 0) {
    err(`  📦 새로 설치·갱신됨 (${copiedFiles.length}개):`);
    for (const wf of commonWorkflows) err(`     📌 ${wf}`);
    for (const wf of typeWorkflows) err(`     🎯 ${wf}`);
  } else {
    err("  📦 새로 설치·갱신된 워크플로우 없음 — 모두 최신 상태");
  }

  err("");
  err("  🔧 .github/scripts/");
  err("     ├─ version_manager.sh");
  err("     └─ changelog_manager.py");
  err("");

  // util 모듈 목록 (.sh L5566~5581) — 타입별 .github/util/{type}/*/ 스캔
  if (utilModulesCopied > 0) {
    err("  🧙 유틸리티 모듈:");
    for (const t of types) {
      const utilDir = join(targetRoot, ".github/util", t);
      if (!existsSync(utilDir)) continue;
      let entries = [];
      try { entries = readdirSync(utilDir, { withFileTypes: true }); } catch { /* 무시 */ }
      for (const e of entries) {
        if (e.isDirectory()) err(`     ├─ ${e.name} (${t})`);
      }
    }
    err("");
  }

  // 프로젝트 타입별 안내 (.sh L5583~5599)
  if (types.includes("spring")) {
    err("  💡 Spring 프로젝트 추가 설정:");
    err("     • build.gradle의 버전 정보가 자동 동기화됩니다");
    err("     • CI/CD 워크플로우에서 GitHub Secrets 설정이 필요합니다");
    err("     • 자세한 설정 방법: .github/workflows/project-types/spring/README.md");
    err("");
  }
  if (types.includes("flutter") && utilModulesCopied > 0) {
    err("  💡 Flutter 배포 마법사 사용법:");
    err("     • iOS TestFlight: .github/util/flutter/testflight-wizard/testflight-wizard.html");
    err("     • Android Play Store: .github/util/flutter/playstore-wizard/playstore-wizard.html");
    err("     • Firebase App Distribution: .github/util/flutter/firebase-wizard/firebase-wizard.html");
    err("     • 브라우저에서 열어 필요한 정보 입력 후 파일 생성");
    err("");
  }

  err("  📖 TEMPLATE REPO: https://github.com/Cassiiopeia/projectops");
  err("  📚 워크플로우 가이드: .github/workflows/project-types/README.md");
  // #493 — 이번 실행의 마이그레이션 기록. "뭐가 남았고 AI에게 어떻게 시키는지"가 바로 보이게 행동 유도형으로 안내.
  // 실행 기록 위치 (#561) — 무슨 일이 있었는지 나중에 확인할 자리를 알린다.

  // 설치 후 검증 결과 (#549) — 문제가 있을 때만 펼치고, 정상이면 한 줄로 압축한다.
  const verification = ctx?.verification;
  if (verification) {
    const unresolved = verification.unresolved || [];
    err(SEPARATOR);
    err("");
    if (unresolved.length === 0) {
      err("✅ 설치 검증: 치환되지 않은 값 없음");
    } else {
      err(`${YELLOW}⚠️  설치 검증: 치환되지 않은 값 ${unresolved.length}건${NC}`);
      err("");
      err("   아래 위치에 템플릿 값이 그대로 남아 있습니다. 그대로 두면 배포 시점에 실패합니다.");
      err("   (프로젝트 구조를 자동으로 찾지 못한 경우입니다 — 직접 값을 채워주세요)");
      err("");
      for (const u of unresolved.slice(0, 10)) {
        err(`   ${u.filename}:${u.line}  ${u.token}`);
      }
      if (unresolved.length > 10) err(`   … 외 ${unresolved.length - 10}건`);
    }
    err("");

    // 필요한 Secret 목록 — 설치된 워크플로우 기준이라 "이 레포에 실제로 필요한 것"만 나온다.
    const secrets = verification.secrets;
    if (secrets && secrets.size > 0) {
      err(`${CYAN}🔑 등록이 필요한 GitHub Secret (${secrets.size}개)${NC}`);
      err("   → Repository Settings > Secrets and variables > Actions");
      err("");
      for (const [name, users] of secrets) {
        const where = users.length > 2 ? `${users.slice(0, 2).join(", ")} 외 ${users.length - 2}개` : users.join(", ");
        err(`   ${name}`);
        err(`     └ ${where}`);
      }
      err("");
      err("   💡 등록 전까지 해당 워크플로우는 실패합니다. 쓰지 않는 워크플로우라면 무시해도 됩니다.");
      err("");
    }
  }

  // 필수 3가지 작업 안내 (.sh L5605~5625 — 원문 유지)
  err(SEPARATOR);
  err("");
  err(`${YELLOW}⚠️  다음 작업을 확인해주세요:${NC}`);
  err("");
  // #551 — PAT는 없어도 릴리스가 완주한다. 있으면 후속 자동화가 더 매끄러워질 뿐이다.
  err("  1️⃣  (선택) GitHub Personal Access Token 설정");
  err("     → 없어도 릴리스는 정상 동작합니다. 등록하면 릴리스 후 후속 워크플로우가");
  err("        더 확실하게 이어지고, 브랜치 보호 규칙이 있어도 자동 머지가 가능합니다.");
  err("     → Repository Settings > Secrets > Actions");
  err("     → Secret Name: _GITHUB_PAT_TOKEN / Scopes: repo, workflow");
  err("");
  // #490 — 마법사가 브랜치를 직접 생성(또는 존재 확인)했으면 같은 작업을 재지시하지 않는다
  if (deployBranchReady) {
    err(`  2️⃣  ✅ ${deployBranchName} 브랜치 준비 완료: 마법사가 확인 및 생성했습니다 (추가 작업 불필요)`);
  } else {
    err(`  2️⃣  ${deployBranchName} 브랜치 생성 (아직 없다면)`);
    err(`     → git checkout -b ${deployBranchName} && git push -u origin ${deployBranchName}`);
  }
  err("");
  // #569 — 선택한 것만 안내한다. 끈 기능의 설정법을 보여주면 무엇을 해야 하는지 흐려진다.
  let step = 3;
  if (ctx?.aiPrSummary !== false) {
    err(`  ${step}️⃣  (선택) AI가 다듬은 릴리스 노트 받기`);
    err("     → 지금 상태로도 릴리스 노트는 나옵니다. 커밋 내용을 분석해 만들기 때문에");
    err("        아무 설정을 하지 않아도 됩니다. 아래는 문장을 더 매끄럽게 하고 싶을 때만 하세요.");
    err("");
    err("     ① Google AI Studio에서 키 발급 (무료 · 신용카드 불필요 · 2분)");
    err("        https://aistudio.google.com/apikey");
    err("     ② 이 저장소에 등록");
    err("        Settings > Secrets and variables > Actions > New repository secret");
    err(`        ${BOLD}Name: GEMINI_API_KEY${NC}   Secret: 발급받은 키(AIza... 로 시작)`);
    err("");
    err("     💡 다른 서비스를 쓴다면 이름만 바꿔 등록하면 됩니다 — 등록한 것이 자동으로 쓰입니다.");
    err("        OPENAI_API_KEY · ANTHROPIC_API_KEY · GROQ_API_KEY · MISTRAL_API_KEY");
    err("");
    step++;
  }
  if (ctx?.codeReviewCoderabbit === true) {
    err(`  ${step}️⃣  CodeRabbit 활성화`);
    err("     → https://coderabbit.ai 로그인 → GitHub 앱 설치 → 이 저장소에 접근 권한(grant access) 부여");
    err("     → 이 단계를 안 하면 워크플로우는 켜져도 PR에 리뷰 댓글이 달리지 않습니다");
    err("");
    step++;
  }
  err(SEPARATOR);
  err("");
  err(`${CYAN}📖 자세한 설정 방법은 다음 파일을 참고하세요:${NC}`);
  err("   → PROJECTOPS-SETUP-GUIDE.md");
  err("");
  // 기록 안내는 완료 화면의 맨 끝에 둔다 (#561) — Secret 목록이 길면 위쪽은 스크롤에 묻혀
  // 사용자가 "로그 얘기가 없다"고 느낀다. 문제가 생겼을 때 가장 먼저 찾는 것이므로 마지막 자리다.
  if (ctx?.logFile || ctx?.logDir || ctx?.migrationGuidePath) {
    err(`${CYAN}📁 이번 실행 기록${NC}`);
    if (ctx?.logFile || ctx?.logDir) {
      err(`   로그:   ${ctx.logFile || `${ctx.logDir}/`}`);
      if (ctx.traceFile) err(`   이벤트: ${ctx.traceFile}`);
    }
    if (ctx?.migrationGuidePath) err(`   가이드: ${ctx.migrationGuidePath}`);
    err("   무엇을 어떤 근거로 정했는지 전부 남아 있습니다 (저장소에 추적되지 않음).");
    err("   💡 문제가 생기면 AI Agent에게 \"실행 로그 확인해줘\"라고 요청하세요.");
    err("");
  }
}
