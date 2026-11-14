// node:readline based interactive prompt engine (replaces @clack/prompts).
// WHY: @clack/prompts 1.7.0 fails to handle the Enter (return) key in Windows TTY consoles
//   and freezes (confirmed by measurement). node:readline keypress events work fine on Windows.
//   Zero external dependencies → safe on internal networks too.
//
// Contract: cancel (ESC/Ctrl+C) returns the CANCEL symbol. Every function is async.
import { emitKeypressEvents } from "node:readline";
import { stdin, stdout } from "node:process";
import { visualWidth } from "./ansi.js";
import { t } from "../i18n/index.js";

export const CANCEL = Symbol("cancel");

// ── ANSI helpers (replaces picocolors — zero dependencies) ───────────────────────────
const ESC = "\x1b[";
const c = {
  reset: `${ESC}0m`, dim: `${ESC}2m`, bold: `${ESC}1m`,
  cyan: `${ESC}36m`, green: `${ESC}32m`, gray: `${ESC}90m`, yellow: `${ESC}33m`,
};
const paint = (s, color) => `${color}${s}${c.reset}`;
const hideCursor = () => stdout.write(`${ESC}?25l`);
const showCursor = () => stdout.write(`${ESC}?25h`);

// Symbols (keeps the clack look)
const S_ACTIVE = paint("●", c.green);
const S_INACTIVE = paint("○", c.dim);
const S_CHECK_ON = paint("◼", c.green);
const S_CHECK_OFF = paint("◻", c.dim);
const S_BAR = paint("│", c.gray);
const S_Q = paint("◆", c.cyan);
const S_DONE = paint("◇", c.green);

// Number of physical rows a logical line takes at the terminal width (accounts for wrapping).
// WHY: when a long label (with 2-cell Korean) exceeds the terminal width, the terminal wraps it into 2+ physical rows.
//   Cursor rewind (ESC[nA) counts physical rows, so counting only logical lines rewinds too little by the wrapped amount,
//   leaving old output and pushing the screen down on every render. (Measured: Windows PowerShell width 80)
export function physicalRows(line, cols) {
  const w = visualWidth(line); // Excludes ANSI sequences + CJK 2 cells
  if (cols <= 0) return 1;
  // Even an empty line takes at least 1 row. An exact multiple of the width does not wrap, so as is (80-cell line @ width 80 = 1 row).
  if (w === 0) return 1;
  return Math.max(1, Math.ceil(w / cols));
}

// Renderer that clears several lines and returns the cursor to the block start.
// Moves up by the "physical row count" of the previous render, clears and redraws (wrap safe).
function makeRenderer() {
  let prevRows = 0; // Physical rows actually taken by the previous render
  return {
    render(lines) {
      if (prevRows > 0) stdout.write(`${ESC}${prevRows}A`); // Up by physical rows
      stdout.write(`${ESC}0J`); // Clear everything below the cursor
      stdout.write(lines.join("\n") + "\n");
      const cols = stdout.columns || 80; // Terminal width (assume 80 when missing, e.g. a pipe)
      prevRows = lines.reduce((sum, l) => sum + physicalRows(l, cols), 0);
    },
    reset() { prevRows = 0; },
  };
}

// Shared wrapper for raw keypress sessions. onKey(str,key) returning true ends it.
// The return value is built by finalize(). CANCEL on cancel.
function keySession(renderFn, onKey) {
  return new Promise((resolve) => {
    const wasRaw = stdin.isTTY ? stdin.isRaw : false;
    emitKeypressEvents(stdin);
    if (stdin.isTTY) stdin.setRawMode(true);
    stdin.resume();
    hideCursor();

    const cleanup = () => {
      stdin.removeListener("keypress", handler);
      if (stdin.isTTY) stdin.setRawMode(wasRaw);
      stdin.pause();
      showCursor();
    };

    const handler = (str, key) => {
      key = key || {};
      // Cancel: Ctrl+C / ESC
      if ((key.ctrl && key.name === "c") || key.name === "escape") {
        cleanup();
        resolve(CANCEL);
        return;
      }
      const done = onKey(str, key);
      if (done !== undefined) {
        cleanup();
        resolve(done);
      } else {
        renderFn();
      }
    };
    stdin.on("keypress", handler);
    renderFn(); // First render
  });
}

// ── Single select (arrow keys + Enter) ───────────────────────────────────────
// options: [{value,label,hint?}]. Returns the selected value or CANCEL.
export async function select({ message, options, initialIndex = 0 }) {
  if (!stdin.isTTY) {
    // Non-TTY: return the default (first item) — guards pipe environments
    return options[initialIndex]?.value;
  }
  const r = makeRenderer();
  let idx = Math.max(0, Math.min(initialIndex, options.length - 1));

  const draw = () => {
    const lines = [S_BAR, `${S_Q}  ${paint(message, c.bold)}`];
    options.forEach((o, i) => {
      const sel = i === idx;
      const marker = sel ? S_ACTIVE : S_INACTIVE;
      const label = sel ? paint(o.label, c.cyan) : o.label;
      const hint = o.hint && sel ? paint(`  (${o.hint})`, c.dim) : "";
      lines.push(`${S_BAR}  ${marker} ${label}${hint}`);
    });
    lines.push(paint(`└  ${t("engine.hint.select")}`, c.gray));
    r.render(lines);
  };

  const result = await keySession(draw, (str, key) => {
    if (key.name === "up" || key.name === "k") { idx = (idx - 1 + options.length) % options.length; return; }
    if (key.name === "down" || key.name === "j") { idx = (idx + 1) % options.length; return; }
    // Number jump (1-9)
    if (/^[1-9]$/.test(str || "")) {
      const n = Number(str) - 1;
      if (n < options.length) { idx = n; return; }
      return;
    }
    if (key.name === "return" || key.name === "enter") return options[idx].value;
    return; // Any other key: ignore and continue
  });

  // Redraw the confirmed screen (◇ done symbol + selected value)
  if (result !== CANCEL) {
    const chosen = options.find((o) => o.value === result);
    r.render([S_BAR, `${S_DONE}  ${paint(message, c.dim)}`, `${S_BAR}  ${paint(chosen?.label ?? "", c.dim)}`]);
  }
  return result;
}

// ── Multi select (Space toggles + Enter) ──────────────────────────────────
// options: [{value,label,hint?,disabled?}]. Returns an array of selected values or CANCEL.
export async function multiselect({ message, options, initialValues = [], required = false }) {
  if (!stdin.isTTY) {
    return initialValues.length ? [...initialValues] : (required ? [options[0]?.value].filter(Boolean) : []);
  }
  const r = makeRenderer();
  let idx = 0;
  const chosen = new Set(initialValues);
  let warn = "";

  const draw = () => {
    const lines = [S_BAR, `${S_Q}  ${paint(message, c.bold)}`];
    options.forEach((o, i) => {
      const cur = i === idx;
      const box = chosen.has(o.value) ? S_CHECK_ON : S_CHECK_OFF;
      const pointer = cur ? paint("❯", c.cyan) : " ";
      const label = cur ? paint(o.label, c.cyan) : (o.disabled ? paint(o.label, c.dim) : o.label);
      const hint = o.hint ? paint(`  (${o.hint})`, c.dim) : "";
      lines.push(`${S_BAR} ${pointer} ${box} ${label}${hint}`);
    });
    if (warn) lines.push(paint(`   ${warn}`, c.yellow));
    lines.push(paint(`└  ${t("engine.hint.multiselect")}`, c.gray));
    r.render(lines);
  };

  const result = await keySession(draw, (str, key) => {
    warn = "";
    if (key.name === "up" || key.name === "k") { idx = (idx - 1 + options.length) % options.length; return; }
    if (key.name === "down" || key.name === "j") { idx = (idx + 1) % options.length; return; }
    if (key.name === "space" || str === " ") {
      const o = options[idx];
      if (o.disabled) { warn = t("engine.disabled"); return; }
      if (chosen.has(o.value)) chosen.delete(o.value); else chosen.add(o.value);
      return;
    }
    if (str === "a") {
      // Select all; if everything is already selected, clear instead (like a toggle).
      const selectable = options.filter((o) => !o.disabled).map((o) => o.value);
      const allOn = selectable.every((v) => chosen.has(v));
      for (const v of selectable) { if (allOn) chosen.delete(v); else chosen.add(v); }
      return;
    }
    if (key.name === "return" || key.name === "enter") {
      if (required && chosen.size === 0) { warn = t("engine.required"); return; }
      return [...chosen];
    }
    return;
  });

  if (result !== CANCEL) {
    const labels = options.filter((o) => chosen.has(o.value)).map((o) => o.label).join(", ") || t("engine.none");
    r.render([S_BAR, `${S_DONE}  ${paint(message, c.dim)}`, `${S_BAR}  ${paint(labels, c.dim)}`]);
  }
  return result;
}

// ── Text input (Enter confirms, empty input = default) ─────────────────────────
// Returns the input string (defaultValue on empty input) or CANCEL.
export async function text({ message, defaultValue = "" }) {
  if (!stdin.isTTY) return defaultValue;
  return new Promise((resolve) => {
    const wasRaw = stdin.isTTY ? stdin.isRaw : false;
    emitKeypressEvents(stdin);
    if (stdin.isTTY) stdin.setRawMode(true);
    stdin.resume();
    let buf = "";

    const prompt = () => {
      stdout.write(`\r${ESC}0K`); // Reset the line
      const shown = buf.length ? buf : paint(defaultValue || "", c.dim);
      stdout.write(`${S_Q}  ${paint(message, c.bold)} ${shown}`);
    };

    const cleanup = () => {
      stdin.removeListener("keypress", handler);
      if (stdin.isTTY) stdin.setRawMode(wasRaw);
      stdin.pause();
      stdout.write("\n");
    };

    const handler = (str, key) => {
      key = key || {};
      if ((key.ctrl && key.name === "c") || key.name === "escape") { cleanup(); resolve(CANCEL); return; }
      if (key.name === "return" || key.name === "enter") {
        cleanup();
        resolve(buf.length ? buf : defaultValue);
        return;
      }
      if (key.name === "backspace") { buf = buf.slice(0, -1); prompt(); return; }
      // Regular characters (excluding control characters)
      if (str && !key.ctrl && !key.meta && str.length === 1 && str >= " ") { buf += str; prompt(); return; }
    };
    stdin.on("keypress", handler);
    prompt();
  });
}

// ── Y/N confirm (←→ or y/n, Enter confirms) ──────────────────────────────
// Returns true/false or CANCEL.
export async function confirm({ message, initialValue = true }) {
  if (!stdin.isTTY) return initialValue;
  const r = makeRenderer();
  let val = initialValue;

  const draw = () => {
    const yes = val ? paint(`● ${t("engine.yes")}`, c.green) : paint(`○ ${t("engine.yes")}`, c.dim);
    const no = !val ? paint(`● ${t("engine.no")}`, c.green) : paint(`○ ${t("engine.no")}`, c.dim);
    r.render([S_BAR, `${S_Q}  ${paint(message, c.bold)}`, `${S_BAR}  ${yes}   ${no}`,
      paint(`└  ${t("engine.hint.confirm")}`, c.gray)]);
  };

  const result = await keySession(draw, (str, key) => {
    if (key.name === "left" || key.name === "right" || key.name === "tab") { val = !val; return; }
    if ((str || "").toLowerCase() === "y") { val = true; return; }
    if ((str || "").toLowerCase() === "n") { val = false; return; }
    if (key.name === "return" || key.name === "enter") return val;
    return;
  });

  if (result !== CANCEL) {
    r.render([S_BAR, `${S_DONE}  ${paint(message, c.dim)}`, `${S_BAR}  ${paint(result ? t("engine.yes") : t("engine.no"), c.dim)}`]);
  }
  return result;
}

// ── Output helpers (replace clack intro/outro/note/cancel) ──────────────────
export function intro(text) { stdout.write(`\n${paint("┌", c.gray)}  ${paint(text, c.bold)}\n`); }
export function outro(text) { stdout.write(`${paint("└", c.gray)}  ${paint(text, c.green)}\n\n`); }
export function cancelMessage(text = t("engine.cancelled")) { stdout.write(`${paint("■", c.yellow)}  ${paint(text, c.yellow)}\n`); }
export function note(text, title = "") {
  const lines = String(text).split("\n");
  stdout.write(`${paint("○", c.cyan)} ${paint(title, c.bold)}\n`);
  for (const l of lines) stdout.write(`${S_BAR}  ${l}\n`);
  stdout.write(`${S_BAR}\n`);
}
export function log(text = "") { stdout.write(`${text}\n`); }
