// Wizard run trace (#494) — Layer 2 (JSONL events) + Layer 3 (terminal mirror) of the 3-layer record.
// Records every wizard decision and action as one event line, so people and AI agents can later trace
// "everything the wizard did to this file" in time order with one file name grep (automates the v4.2.15 manual log-copy diagnosis).
// Layer 1 (curated guide) is migration-guide.js — it consumes this module's events as the single source.
import { join } from "node:path";
import { writeText } from "./fsutil.js";
import { getLang } from "../i18n/index.js";

// Diagnostic log location (#561). Kept outside the tracked docs/ — this record is not a document for people
// but material for agents to check "what happened in the last run".
// A .gitignore is written inside the folder so it carries its own rule (root .gitignore untouched).
// The sibling .github/.projectops/baseline.json is shared with the team, so it stays tracked.
export const MIGRATION_DIR = ".github/.projectops/logs";
export const LOGS_GITIGNORE = [
  "# projectops run diagnostic logs — not tracked in the repository.",
  "# The wizard writes a record here on every run; nothing here is meant to be committed.",
  "*",
  "!.gitignore",
  "",
].join("\n");
export const TRACE_SCHEMA = 1;

// Sensitive value guard — PATs, tokens, secrets and passwords never go into any event (#494 safety rule).
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

// Step duration. Omitted when a fixed clock is injected (tests) so results stay stable.
function elapsed(t0, clockIso) {
  return clockIso ? {} : { ms: Date.now() - t0 };
}

// Turn an event into one server-log style line (#561).
//   [time] LEVEL phase/action  target  key=value ...
// The level is inferred from action — only what needs action (unreplaced, cancelled, failed) should stand out.
// Levels split by "what to look at first".
//   ERROR — failure. Must be acted on.
//   WARN  — may fail later if left as is, or needs a user decision.
//   INFO  — the main flow of the run. Step boundaries and settled decisions.
//   DEBUG — per-item detail (one file, one substitution). Default is INFO, but everything goes to the file.
//
// Why DEBUG goes to the file: after a problem hits, "if only DEBUG had been on" is useless.
// Keep the screen quiet but write everything to the file.
const ERROR_ACTIONS = new Set(["error", "failed"]);
const WARN_ACTIONS = new Set([
  "unresolved", "cancelled", "skipped-conflict", "leftover-old-gen",
  "neutralized", "detected", "replaced-bak", "incoming-failed", "baseline-failed",
  "branch-synced", "not-applied", "not-recorded", // #1248 typed branch values
]);
const DEBUG_ACTIONS = new Set([
  "copied", "skipped-unchanged", "excluded", "substituted", "branch-substituted",
  "required-key", "project-path", "upstream-updated", "template-added",
  "scripts", "config", "util", "templates",
]);
export function levelOf(action) {
  if (ERROR_ACTIONS.has(action)) return "ERROR";
  if (WARN_ACTIONS.has(action)) return "WARN";
  if (DEBUG_ACTIONS.has(action)) return "DEBUG";
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

// Strip color and cursor control sequences (#561). Log files are read by editors and agents, so leftover
// escapes get in the way. Terminal output itself is untouched (only the copy is cleaned).
// eslint-disable-next-line no-control-regex
const ANSI_RE = /\u001b\[[0-9;]*[A-Za-z]/g;
export function stripAnsi(text) {
  return String(text).replace(ANSI_RE, "");
}

// now("YYYY-MM-DD HH:MM:SS") → file name stamp "YYYYMMDD_HHMMSS". Falls back to "run" if not in that format (safe for test-injected clocks).
export function stampFromNow(now) {
  const digits = String(now ?? "").replace(/[^0-9]/g, "");
  if (digits.length < 14) return "run";
  return `${digits.slice(0, 8)}_${digits.slice(8, 14)}`;
}

// Trace factory. clockIso can be injected (test determinism) — default is the real UTC.
export function createRunTrace({ clockIso = null } = {}) {
  const events = [];
  const lines = [];
  let restore = null;
  let finalized = false;
  let signalsArmed = false;

  const nowIso = () => clockIso ?? new Date().toISOString().replace(/\.\d+Z$/, "Z");

  return {
    events,
    lines,

    // Record one event. detail is stored after scrubbing sensitive keys.
    // Also writes it as a human-readable log line (#561) — internal behavior not shown in the terminal
    // must be traceable in time order in the one .log file so problems can be handled right away.
    event(phase, action, target = "", detail = null) {
      const e = { ts: nowIso(), phase, action, target };
      const d = scrubDetail(detail);
      if (d != null && (typeof d !== "object" || Object.keys(d).length > 0)) e.detail = d;
      events.push(e);
      lines.push(formatLogLine(e));
      return e;
    },

    // Start the terminal output mirror — wraps stdout/stderr write and collects a copy (output itself passes through).
    // Enabled only in a real CLI run (not called on the test stub io path).
    mirrorStart() {
      if (restore) return;
      const so = process.stdout.write; // Keep the original reference — identity is kept on restore
      const se = process.stderr.write;
      // The run log is always English (agents read it later, and it must not change with the user's locale).
      // When the screen is in another language the raw terminal text is not copied; the caller appends an
      // English rendering of the completion screen with appendText() instead.
      const capture = (chunk) => {
        if (getLang() !== "en") return;
        try {
          const s = typeof chunk === "string" ? chunk : chunk.toString("utf8");
          lines.push(stripAnsi(s));
        } catch { /* A mirror failure does not affect the run */ }
      };
      process.stdout.write = function (chunk, ...rest) { capture(chunk); return so.apply(process.stdout, [chunk, ...rest]); };
      process.stderr.write = function (chunk, ...rest) { capture(chunk); return se.apply(process.stderr, [chunk, ...rest]); };
      restore = () => { process.stdout.write = so; process.stderr.write = se; };
    },

    // Add already-rendered text (e.g. the English completion screen) to the log.
    appendText(text) {
      lines.push(stripAnsi(String(text)));
    },

    mirrorStop() {
      if (restore) { restore(); restore = null; }
    },

    // Step wrapper (#561) — records "where it entered, when it left and how long it took" automatically,
    // like a server log. Scattering start/done over call sites always misses some.
    // On an exception, records failed and rethrows — never swallows.
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

    // async version — for interactive steps (including waits for answers).
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

    // Leave a record even on forced exit (Ctrl+C) (#561).
    // If SIGINT's default kills the process, finally never runs — yet when the user cuts it off is exactly when
    // "how far did it get" matters most, so missing it here halves the log's value.
    // The handler only records, then exits as before (behavior unchanged).
    armSignals(opts = {}) {
      if (signalsArmed) return () => {};
      signalsArmed = true;
      const self = this;
      const handlers = [];
      for (const sig of ["SIGINT", "SIGTERM"]) {
        const h = () => {
          self.event("run", "cancelled", sig, { reason: "user forced exit (signal received)" });
          self.finalize(opts);
          process.removeListener(sig, h);
          process.kill(process.pid, sig);   // Hand over to the original exit behavior
        };
        process.on(sig, h);
        handlers.push([sig, h]);
      }
      return () => {
        for (const [sig, h] of handlers) process.removeListener(sig, h);
        signalsArmed = false;
      };
    },

    // Leave a record however it ends (#561) — normal finish, mid-run cancel, exception, forced exit.
    // When the user cuts it off midway is exactly when "how far did it get" matters most,
    // so a record kept only on a full run is half as useful.
    //
    // Writes once even if called twice (normal path + duplicate call in finally). Failures are swallowed —
    // a recording failure must not block exit.
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

    // Only computes the record file paths (no write). Capturing the finish screen means delaying write until after screen output,
    // but the guide entry needs the traceFile path before that, so the two are separated.
    paths({ fromVersion = "", toVersion = "", now = "" } = {}) {
      const stamp = stampFromNow(now);
      const from = String(fromVersion || "new").replace(/[^0-9a-zA-Z.-]/g, "");
      const to = String(toVersion || "unknown").replace(/[^0-9a-zA-Z.-]/g, "");
      const base = `${stamp}_v${from}_to_v${to}`;
      return { base, traceFile: `${MIGRATION_DIR}/${base}.jsonl`, logFile: `${MIGRATION_DIR}/${base}.log` };
    },

    // Layer 2/3 file record — .github/.projectops/logs/{stamp}_v{from}_to_v{to}.{jsonl,log}
    // Returns { traceFile, logFile } (relative to targetRoot — used as guide meta pointers).
    // Writes nothing when there are 0 events (avoids polluting no-op runs) — returns null.
    write({ targetRoot = ".", fromVersion = "", toVersion = "", now = "" } = {}) {
      if (events.length === 0) return null;
      const from = String(fromVersion || "new").replace(/[^0-9a-zA-Z.-]/g, "");
      const to = String(toVersion || "unknown").replace(/[^0-9a-zA-Z.-]/g, "");
      const planned = this.paths({ fromVersion, toVersion, now });
      // Ensure the folder rule every time — stays untracked even if the user deleted it or the folder is new.
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
