// 마법사 실행 트레이스 (#494) — 3계층 기록의 Layer 2(JSONL 이벤트) + Layer 3(터미널 미러).
// 마법사의 모든 결정·행동을 이벤트 한 줄씩 남겨, 나중에 사람·AI Agent가 파일명 grep 한 번으로
// "이 파일에 마법사가 한 모든 일"을 시간순 추적할 수 있게 한다 (v4.2.15 수동 로그 복사 진단의 자동화).
// Layer 1(큐레이션 가이드)은 migration-guide.js — 이 모듈의 events를 단일 소스로 소비한다.
import { join } from "node:path";
import { writeText } from "./fsutil.js";

// 진단 로그 위치 (#561). docs/ 아래(추적 대상)에서 옮겼다 — 이 기록은 사람이 읽는 문서가
// 아니라 Agent가 "지난 실행에서 무슨 일이 있었나"를 확인하는 자료다.
// 폴더 안에 .gitignore를 함께 써서 폴더가 자기 규칙을 들고 다닌다(루트 .gitignore 무수정).
// 형제인 .github/.projectops/baseline.json은 팀원 공유 자산이라 계속 추적된다.
export const MIGRATION_DIR = ".github/.projectops/logs";
export const LOGS_GITIGNORE = [
  "# projectops 실행 진단 로그 — 저장소에 추적하지 않습니다.",
  "# 이 폴더는 마법사가 실행할 때마다 기록을 남기며, 커밋 대상이 아닙니다.",
  "*",
  "!.gitignore",
  "",
].join("\n");
export const TRACE_SCHEMA = 1;

// 민감값 가드 — PAT·토큰·시크릿·비밀번호는 어떤 이벤트에도 남기지 않는다 (#494 안전 규칙).
const SENSITIVE_KEY_RE = /pat|token|secret|password|credential/i;
export function scrubDetail(detail) {
  if (detail == null || typeof detail !== "object" || Array.isArray(detail)) return detail;
  const out = {};
  for (const [k, v] of Object.entries(detail)) {
    if (SENSITIVE_KEY_RE.test(k)) continue;
    out[k] = (v != null && typeof v === "object" && !Array.isArray(v)) ? scrubDetail(v) : v;
  }
  return out;
}

// 단계 소요 시간. 시계를 고정 주입한 경우(테스트)는 생략해 결과가 흔들리지 않게 한다.
function elapsed(t0, clockIso) {
  return clockIso ? {} : { ms: Date.now() - t0 };
}

// 이벤트를 서버 로그 스타일 한 줄로 만든다 (#561).
//   [시각] 레벨 phase/action  대상  key=value ...
// 레벨은 action에서 유추한다 — 조치가 필요한 것(미치환·취소·실패)만 눈에 띄어야 한다.
const WARN_ACTIONS = new Set(["unresolved", "cancelled", "skipped-conflict", "leftover-old-gen", "neutralized"]);
const ERROR_ACTIONS = new Set(["error", "failed"]);  // step/failed 포함
export function levelOf(action) {
  if (ERROR_ACTIONS.has(action)) return "ERROR";
  if (WARN_ACTIONS.has(action)) return "WARN";
  return "INFO";
}
export function formatLogLine(e) {
  const time = String(e.ts || "").replace(/^.*T/, "").replace(/Z$/, "");
  const level = levelOf(e.action).padEnd(5);
  const tag = `${e.phase}/${e.action}`.padEnd(24);
  const parts = [`[${time}] ${level} ${tag} ${e.target || ""}`.trimEnd()];
  if (e.detail && typeof e.detail === "object") {
    const kv = Object.entries(e.detail)
      .filter(([, v]) => v !== null && v !== undefined)
      .map(([k, v]) => `${k}=${Array.isArray(v) ? (v.join("|") || "[]") : v}`);
    if (kv.length) parts.push(`  ${kv.join(" ")}`);
  }
  return parts.join("") + "\n";
}

// 색상·커서 제어 시퀀스 제거 (#561). 로그 파일은 에디터·Agent가 읽으므로 이스케이프가
// 그대로 남으면 판독을 방해한다. 터미널 출력 자체는 건드리지 않는다(사본만 정제).
// eslint-disable-next-line no-control-regex
const ANSI_RE = /\u001b\[[0-9;]*[A-Za-z]/g;
export function stripAnsi(text) {
  return String(text).replace(ANSI_RE, "");
}

// now("YYYY-MM-DD HH:MM:SS") → 파일명 스탬프 "YYYYMMDD_HHMMSS". 형식이 아니면 "run" 폴백(테스트 주입 clock 안전).
export function stampFromNow(now) {
  const digits = String(now ?? "").replace(/[^0-9]/g, "");
  if (digits.length < 14) return "run";
  return `${digits.slice(0, 8)}_${digits.slice(8, 14)}`;
}

// 트레이스 팩토리. clockIso 주입 가능(테스트 결정성) — 기본은 실제 UTC.
export function createRunTrace({ clockIso = null } = {}) {
  const events = [];
  const lines = [];
  let restore = null;
  let finalized = false;

  const nowIso = () => clockIso ?? new Date().toISOString().replace(/\.\d+Z$/, "Z");

  return {
    events,
    lines,

    // 이벤트 1건 기록. detail은 민감키 스크럽 후 저장.
    // 같은 내용을 사람이 읽는 로그 라인으로도 남긴다 (#561) — 터미널에 보이지 않는 내부
    // 동작까지 .log 한 파일에서 시간순으로 따라갈 수 있어야, 문제가 생겼을 때 바로 대응된다.
    event(phase, action, target = "", detail = null) {
      const e = { ts: nowIso(), phase, action, target };
      const d = scrubDetail(detail);
      if (d != null && (typeof d !== "object" || Object.keys(d).length > 0)) e.detail = d;
      events.push(e);
      lines.push(formatLogLine(e));
      return e;
    },

    // 터미널 출력 미러 시작 — stdout/stderr write를 감싸 사본만 수집(출력 자체는 그대로 통과).
    // 실제 CLI 실행에서만 켠다 (테스트 스텁 io 경로는 호출하지 않음).
    mirrorStart() {
      if (restore) return;
      const so = process.stdout.write; // 원본 참조 보관 — 복원 시 identity 유지
      const se = process.stderr.write;
      const capture = (chunk) => {
        try {
          const s = typeof chunk === "string" ? chunk : chunk.toString("utf8");
          lines.push(stripAnsi(s));
        } catch { /* 미러 실패는 실행에 영향 없음 */ }
      };
      process.stdout.write = function (chunk, ...rest) { capture(chunk); return so.apply(process.stdout, [chunk, ...rest]); };
      process.stderr.write = function (chunk, ...rest) { capture(chunk); return se.apply(process.stderr, [chunk, ...rest]); };
      restore = () => { process.stdout.write = so; process.stderr.write = se; };
    },

    mirrorStop() {
      if (restore) { restore(); restore = null; }
    },

    // 단계 실행 래퍼 (#561) — 서버 로그처럼 "어디에 들어갔다 언제 나왔고 얼마 걸렸는지"를
    // 자동으로 남긴다. 개별 호출부에 start/done을 흩뿌리면 빠뜨리는 자리가 생긴다.
    // 예외가 나면 failed로 기록하고 그대로 던진다 — 삼키지 않는다.
    step(name, fn, detail = null) {
      this.event("step", "start", name, detail);
      const t0 = Date.now();
      try {
        const out = fn();
        this.event("step", "done", name, elapsed(t0, clockIso));
        return out;
      } catch (err) {
        this.event("step", "failed", name, { ...elapsed(t0, clockIso), message: err?.message || String(err) });
        throw err;
      }
    },

    // async 버전 — 대화형 단계(질문 대기 포함)에 쓴다.
    async stepAsync(name, fn, detail = null) {
      this.event("step", "start", name, detail);
      const t0 = Date.now();
      try {
        const out = await fn();
        this.event("step", "done", name, elapsed(t0, clockIso));
        return out;
      } catch (err) {
        this.event("step", "failed", name, { ...elapsed(t0, clockIso), message: err?.message || String(err) });
        throw err;
      }
    },

    // 어떤 경로로 끝나든 기록을 남긴다 (#561) — 정상 완주·중간 취소·예외·강제 종료.
    // 사용자가 중간에 끊었을 때야말로 "어디까지 갔는지"가 가장 궁금한 순간이라,
    // 완주했을 때만 남기는 기록은 쓸모가 절반이다.
    //
    // 두 번 불려도 한 번만 쓴다(정상 경로 + finally 중복 호출 대비). 실패는 삼킨다 —
    // 기록 실패가 종료를 막아선 안 된다.
    finalize(opts = {}) {
      if (finalized) return null;
      finalized = true;
      try {
        this.mirrorStop();
        return this.write(opts);
      } catch {
        return null;
      }
    },

    // 기록 파일 경로만 계산한다 (쓰지 않음). 완료 화면까지 캡처하려면 write를 화면 출력 뒤로
    // 미뤄야 하는데, 가이드 엔트리는 그 전에 traceFile 경로를 참조해야 해서 둘을 분리했다.
    paths({ fromVersion = "", toVersion = "", now = "" } = {}) {
      const stamp = stampFromNow(now);
      const from = String(fromVersion || "new").replace(/[^0-9a-zA-Z.-]/g, "");
      const to = String(toVersion || "unknown").replace(/[^0-9a-zA-Z.-]/g, "");
      const base = `${stamp}_v${from}_to_v${to}`;
      return { base, traceFile: `${MIGRATION_DIR}/${base}.jsonl`, logFile: `${MIGRATION_DIR}/${base}.log` };
    },

    // Layer 2/3 파일 기록 — .github/.projectops/logs/{stamp}_v{from}_to_v{to}.{jsonl,log}
    // 반환: { traceFile, logFile } (targetRoot 기준 상대 경로 — 가이드 메타 포인터용).
    // 이벤트가 0건이면 기록하지 않는다(no-op 실행 오염 방지) — null 반환.
    write({ targetRoot = ".", fromVersion = "", toVersion = "", now = "" } = {}) {
      if (events.length === 0) return null;
      const from = String(fromVersion || "new").replace(/[^0-9a-zA-Z.-]/g, "");
      const to = String(toVersion || "unknown").replace(/[^0-9a-zA-Z.-]/g, "");
      const planned = this.paths({ fromVersion, toVersion, now });
      // 폴더 규칙을 매번 보장한다 — 사용자가 지웠거나 폴더가 새로 생겨도 추적되지 않게.
      writeText(join(targetRoot, `${MIGRATION_DIR}/.gitignore`), LOGS_GITIGNORE);
      const header = JSON.stringify({ schema: TRACE_SCHEMA, kind: "projectops-migration-trace", from, to, started: events[0]?.ts ?? "" });
      writeText(join(targetRoot, planned.traceFile), [header, ...events.map((e) => JSON.stringify(e))].join("\n") + "\n");
      let logFile = null;
      if (lines.length > 0) {
        logFile = planned.logFile;
        writeText(join(targetRoot, logFile), lines.join(""));
      }
      return { traceFile: planned.traceFile, logFile };
    },
  };
}
