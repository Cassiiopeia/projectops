// @wizard env 토큰 엔진 (.sh configure_workflow_env / _wf_set_env / _wf_is_unchanged 등가).
// ⚠️ YAML 파싱/재직렬화 금지 — 라인 단위 문자열 처리 (포맷·주석 보존이 unchanged 판정 전제).
// 실측 기준: template_integrator.sh 3282~3360, 3003~3012.
import { substituteBranches } from "./branch-sub.js";

// KEY 정규식: .sh는 [A-Z_]+ (대문자+언더스코어만). ask/auto 마커가 있는 라인만 대상.
const MARKER_RE = /#\s*@wizard\s+(ask|auto):(.*)$/;
const KEY_RE = /^(\s*)([A-Z_]+):/;
const PATHS_ANCHOR_RE = /#\s*@wizard\s+paths-anchor/;

// 한 라인을 파싱해 {indent,key,action,arg} 반환. ask/auto 마커 없으면 null.
export function parseWizardLine(line) {
  const marker = line.match(MARKER_RE);
  if (!marker) return null;
  const km = line.match(KEY_RE);
  if (!km) return null; // KEY: 형식 아니면 (예: paths-anchor 주석) 무시
  return { indent: km[1], key: km[2], action: marker[1], arg: marker[2].trim() };
}

// .sh _wf_set_env 등가: `KEY: "..."` 따옴표 안 값 치환 + 그 줄 끝 `# @wizard ...` 주석 제거.
// 라인 하나에 대해 수행. value가 빈문자면 (.sh는 [ -n "$_val" ] 가드) 치환 스킵.
export function setEnvLine(line, key, value) {
  if (value === "" || value == null) return line;
  // CRLF 안전: 라인 끝 \r을 분리해 처리 후 복원 (autocrlf 프로젝트 대응)
  const cr = line.endsWith("\r") ? "\r" : "";
  const body = cr ? line.slice(0, -1) : line;
  // 값 치환: KEY: "기존값" → KEY: "value"
  let out = body.replace(
    new RegExp(`^(\\s*${key}:\\s*")[^"]*(")`),
    (_m, p1, p2) => `${p1}${value}${p2}`,
  );
  // 그 줄 끝 # @wizard ... 주석 제거 (앞 공백째)
  out = out.replace(/(\S)[^\S\r\n]*#[^\S\r\n]*@wizard[^\S\r\n].*$/, "$1");
  return out + cr;
}

// 설치본에서 env 실값 추출 (#502 — 업데이트 모드 carryover).
// 치환 시 @wizard 주석은 제거되지만 `KEY: "값"` 라인은 남는다(setEnvLine) — 그 값을 걷어온다.
// 템플릿 지식 불필요: substituteEnv가 values를 ask 키에만 참조하므로 무관 키가 섞여도 무해하다.
// 빈 값("")은 제외 — substituteEnv도 빈 chosen을 무시하고 기본값을 쓴다 (동일 규칙).
export function extractEnvValues(installedContent) {
  const values = new Map();
  for (const raw of String(installedContent || "").split(/\r?\n/)) {
    const m = raw.match(/^\s*([A-Z_]+):\s*"([^"]*)"/);
    if (m && m[2] !== "") values.set(m[1], m[2]);
  }
  return values;
}

// 예시용 기본값 (#810) — 그대로 배포되면 남의 도메인으로 요청이 간다.
// 사용자가 값을 고르지 않은 경로(--force·기본값 사용)에서는 채우지 않고 __KEY__ 를 남긴다.
// 그러면 설치 후 검증(verify.js)이 미치환으로 잡아 완료 화면에 "직접 채울 것"으로 보여준다.
export function isPlaceholderDefault(value) {
  return /(^|\.)example\.(com|org|net)$/i.test(String(value || "").trim());
}

// resolver — .sh resolve_token 등가. 값 계산은 주입된 resolvers로 위임(순수성 유지).
// resolvers: { repo, "spring-app-yml-dir"(type), "spring-app-yml-path"(type), "flutter-root" }
export function resolveToken(name, type, resolvers = {}) {
  const fn = resolvers[name];
  return typeof fn === "function" ? (fn(type) ?? "") : "";
}

// 잔여 전역 토큰 치환 (.sh 3347~3351) — 파일 본문·수집값(#489)·카드 표시가 전부 같은 규칙을 쓴다.
// 파일에 실제 써지는 값과 version.yml deploy 블록 기억값이 어긋나지 않게 하는 단일 지점.
export function resolveGlobalTokens(s, repoName = "") {
  if (typeof s !== "string" || (!s.includes("__PROJECT_NAME__") && !s.includes("__APP_ARTIFACT_NAME__"))) return s;
  return s.replaceAll("__PROJECT_NAME__", repoName).replaceAll("__APP_ARTIFACT_NAME__", repoName);
}

// 파일 전체 치환 (configure_workflow_env 등가).
// content: 원본 워크플로우 텍스트. 반환: 치환된 텍스트.
// opts:
//   type          - 프로젝트 타입 (resolver·값 조회용)
//   values        - Map<key,value>: ask 키의 사용자 선택값 (없으면 기본값=arg 또는 resolver)
//   useDefaults   - true면 ask도 기본값 사용 (WF_USE_DEFAULTS=true, unchanged 비교의 전제)
//   resolvers     - resolveToken용
//   repoName      - __PROJECT_NAME__/__APP_ARTIFACT_NAME__ 치환값
//   projectPath   - paths-anchor 치환용 ('.'이면 anchor 미변경)
//   collectSubs   - 배열이면 치환 1건당 {key, action, before, after}를 push (#494 트레이스용)
export function substituteEnv(content, opts = {}) {
  const { type = "", values = new Map(), useDefaults = true, resolvers = {}, repoName = "", projectPath = ".", collectAsks = null, collectSubs = null } = opts;
  if (!content.includes("@wizard")) return content;

  // CRLF 안전: EOL을 분리해 LF 기준으로 파싱·치환하고, 원래 EOL 스타일을 복원한다.
  // (JS 정규식의 `.`은 \r을 매칭하지 않아 `(.*)$` 마커 파싱이 CRLF에서 실패하기 때문.)
  const usesCRLF = content.includes("\r\n");
  const lines = content.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const p = parseWizardLine(lines[i]); // 이미 \r 제거된 라인
    if (!p) continue;
    let val = "";
    if (p.action === "auto") {
      val = resolveToken(p.arg, type, resolvers);
    } else { // ask
      let def = p.arg.startsWith("@") ? resolveToken(p.arg.slice(1), type, resolvers) : p.arg;
      const chosen = values.get(p.key);
      if (chosen != null && chosen !== "" && !useDefaults) val = chosen;
      else if (isPlaceholderDefault(def)) continue; // 예시값은 쓰지 않는다 — 토큰·마커 그대로 (#810)
      else val = def;
      // ask 키만 수집 (.sh wf_deploy_set — auto는 저장 안 함). deploy 블록용.
      // #489 — 파일 본문은 아래 전역 토큰 치환을 거치므로 수집값도 동일 치환해
      //        version.yml deploy 블록이 설치본과 항상 바이트 일치하게 한다.
      if (collectAsks) collectAsks.set(p.key, resolveGlobalTokens(val, repoName));
    }
    // #494 트레이스 — 치환 전후값 기록 (after는 파일 최종형과 동일하게 전역 토큰까지 해석)
    if (Array.isArray(collectSubs) && val !== "" && val != null) {
      const before = (lines[i].match(/:\s*"([^"]*)"/) || [])[1] ?? "";
      collectSubs.push({ key: p.key, action: p.action, before, after: resolveGlobalTokens(val, repoName) });
    }
    lines[i] = setEnvLine(lines[i], p.key, val);
  }
  let out = lines.join(usesCRLF ? "\r\n" : "\n");

  // 잔여 전역 토큰 (.sh 3347~3351)
  out = resolveGlobalTokens(out, repoName);

  // paths-anchor (.sh 3353~3360): 경로가 '.'이 아니면 주석 라인 전체를 paths 라인으로 교체
  if (PATHS_ANCHOR_RE.test(out) && projectPath && projectPath !== ".") {
    const eol = out.includes("\r\n") ? "\r\n" : "\n";
    out = out.split(/\r?\n/).map((line) => {
      if (PATHS_ANCHOR_RE.test(line)) {
        const indent = (line.match(/^(\s*)/) || ["", ""])[1];
        return `${indent}paths: ['${projectPath}/**']`;
      }
      return line;
    }).join(eol);
  }
  return out;
}

// .sh _wf_is_unchanged 등가: 원본을 "기본값으로 가상 치환한 최종형"과 설치본을 바이트 비교.
export function isUnchanged(templateContent, installedContent, opts = {}) {
  // 브랜치 치환(#477)도 가상 비교에 포함 — 치환 설치본이 "변경됨"으로 오판되어 매 업데이트마다
  // 재복사(.bak churn)되는 것을 막는다. opts.branches 미지정/표준값이면 no-op.
  const virtual = substituteBranches(
    substituteEnv(templateContent, { ...opts, useDefaults: true }),
    opts.branches ?? null,
  );
  return virtual === installedContent;
}
