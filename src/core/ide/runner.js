// 외부 CLI 실행·감지 래퍼.
// 전부 주입 가능 — 테스트는 stub runner/which/home 를 넘겨 실제 CLI 없이 검증한다.
import { spawnSync } from "node:child_process";
import { delimiter, join } from "node:path";
import { existsSync } from "node:fs";
import { homedir } from "node:os";

// which(cmd) → 실행 파일 절대경로 or null. PATH를 직접 스캔 (execa 없이 내장만).
// Windows는 PATHEXT 확장자(.cmd/.exe/.bat 등)까지 시도.
export function which(cmd) {
  const paths = (process.env.PATH || "").split(delimiter).filter(Boolean);
  const exts = process.platform === "win32"
    ? (process.env.PATHEXT || ".COM;.EXE;.BAT;.CMD").split(";").filter(Boolean)
    : [""];
  for (const dir of paths) {
    for (const ext of exts) {
      const full = join(dir, cmd + ext);
      if (existsSync(full)) return full;
    }
  }
  return null;
}

// run(cmd, args, opts) → {code, stdout, stderr}. 동기 실행.
// opts.cwd, opts.env 지원. 실행 자체 실패(파일 없음 등)면 code=127.
//
// Windows: claude/gemini/codex/pi 는 .cmd/.ps1 셸 런처라 spawnSync가 직접 못 띄운다.
// shell:true + args 배열은 DEP0190(인자 미이스케이프) 경고 → cmd.exe에 안전 인용한 단일
// 명령 문자열을 넘긴다. args는 우리가 만든 하드코딩 값 + URL/scope뿐이라 신뢰 가능하지만,
// 그래도 큰따옴표로 감싸 공백·특수문자를 방어한다.
export function run(cmd, args = [], opts = {}) {
  const common = { cwd: opts.cwd, env: opts.env || process.env, encoding: "utf8", windowsHide: true };
  let r;
  if (process.platform === "win32") {
    const line = [cmd, ...args].map(winQuote).join(" ");
    r = spawnSync(line, { ...common, shell: true });
  } else {
    r = spawnSync(cmd, args, common); // POSIX는 shell 불필요(안전)
  }
  if (r.error) return { code: 127, stdout: "", stderr: String(r.error.message || r.error) };
  return { code: r.status ?? 0, stdout: r.stdout || "", stderr: r.stderr || "" };
}

// cmd.exe용 인용: 이미 안전한 토큰(영숫자·경로·URL 문자)이면 그대로, 아니면 "..." 로 감싸고 내부 " 이스케이프.
function winQuote(s) {
  if (/^[A-Za-z0-9_./:@=-]+$/.test(s)) return s;
  return '"' + String(s).replace(/"/g, '\\"') + '"';
}

// IDE 실행 컨텍스트 기본값. 테스트는 이 shape을 스텁으로 대체.
//   which(cmd)→path|null, run(cmd,args)→{code,stdout,stderr}, home()→string, log(msg)
export function defaultIo() {
  return {
    which,
    run,
    home: () => homedir(),
    // 파이썬 stable_entry 와 같은 규칙: PROJECTOPS_HOME > ~/.projectops
    projectopsHome: () => process.env.PROJECTOPS_HOME || join(homedir(), ".projectops"),
    log: (msg) => console.error(msg), // 안내는 stderr로 (stdout 파이프 오염 방지)
  };
}
