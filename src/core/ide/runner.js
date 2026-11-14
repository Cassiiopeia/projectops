// Wrapper for running and detecting external CLIs.
// Everything is injectable — tests pass stub runner/which/home to verify without real CLIs.
import { spawnSync } from "node:child_process";
import { delimiter, join } from "node:path";
import { existsSync } from "node:fs";
import { homedir } from "node:os";

// which(cmd) → absolute path of the executable or null. Scans PATH directly (built-ins only, no execa).
// On Windows, also tries PATHEXT extensions (.cmd/.exe/.bat, etc.).
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

// run(cmd, args, opts) → {code, stdout, stderr}. Synchronous.
// Supports opts.cwd and opts.env. If the launch itself fails (no file, etc.), code=127.
//
// Windows: claude/gemini/codex/pi are .cmd/.ps1 shell launchers that spawnSync cannot start directly.
// shell:true + an args array triggers the DEP0190 (unescaped args) warning → pass cmd.exe a single safely quoted
// command string. args are only our hardcoded values + URL/scope, so they are trusted,
// but they are still wrapped in double quotes to guard against spaces and special characters.
export function run(cmd, args = [], opts = {}) {
  const common = { cwd: opts.cwd, env: opts.env || process.env, encoding: "utf8", windowsHide: true };
  let r;
  if (process.platform === "win32") {
    const line = [cmd, ...args].map(winQuote).join(" ");
    r = spawnSync(line, { ...common, shell: true });
  } else {
    r = spawnSync(cmd, args, common); // POSIX needs no shell (safe)
  }
  if (r.error) return { code: 127, stdout: "", stderr: String(r.error.message || r.error) };
  return { code: r.status ?? 0, stdout: r.stdout || "", stderr: r.stderr || "" };
}

// Quoting for cmd.exe: tokens already safe (alphanumerics, path and URL characters) as is, else wrap in "..." and escape inner ".
function winQuote(s) {
  if (/^[A-Za-z0-9_./:@=-]+$/.test(s)) return s;
  return '"' + String(s).replace(/"/g, '\\"') + '"';
}

// Default IDE run context. Tests replace this shape with a stub.
//   which(cmd)→path|null, run(cmd,args)→{code,stdout,stderr}, home()→string, log(msg)
export function defaultIo() {
  return {
    which,
    run,
    home: () => homedir(),
    // Same rule as Python stable_entry: PROJECTOPS_HOME > ~/.projectops
    projectopsHome: () => process.env.PROJECTOPS_HOME || join(homedir(), ".projectops"),
    log: (msg) => console.error(msg), // Notices go to stderr (keeps the stdout pipe clean)
  };
}
