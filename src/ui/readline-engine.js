// node:readline 기반 대화형 프롬프트 엔진 (@clack/prompts 대체).
// WHY: @clack/prompts 1.7.0 이 Windows TTY 콘솔에서 Enter(return) 키를 처리하지 못하고
//   멈추는 버그가 있다(실측 확정). node:readline 의 keypress 이벤트는 Windows에서 정상 동작한다.
//   .sh/.ps1 이 자체 메뉴를 구현한 것과 동일한 접근. 외부 의존성 0 → 내부망에서도 안전.
//
// 계약: 취소(ESC/Ctrl+C)는 CANCEL 심볼 반환. 각 함수 async.
import { emitKeypressEvents } from "node:readline";
import { stdin, stdout } from "node:process";
import { visualWidth } from "./ansi.js";
import { t } from "../i18n/index.js";

export const CANCEL = Symbol("cancel");

// ── ANSI 헬퍼 (picocolors 대체 — 의존성 0) ───────────────────────────
const ESC = "\x1b[";
const c = {
  reset: `${ESC}0m`, dim: `${ESC}2m`, bold: `${ESC}1m`,
  cyan: `${ESC}36m`, green: `${ESC}32m`, gray: `${ESC}90m`, yellow: `${ESC}33m`,
};
const paint = (s, color) => `${color}${s}${c.reset}`;
const hideCursor = () => stdout.write(`${ESC}?25l`);
const showCursor = () => stdout.write(`${ESC}?25h`);

// 심볼 (clack 톤 유지)
const S_ACTIVE = paint("●", c.green);
const S_INACTIVE = paint("○", c.dim);
const S_CHECK_ON = paint("◼", c.green);
const S_CHECK_OFF = paint("◻", c.dim);
const S_BAR = paint("│", c.gray);
const S_Q = paint("◆", c.cyan);
const S_DONE = paint("◇", c.green);

// 한 논리 라인이 터미널 폭에서 차지하는 물리 줄 수 (wrap 고려).
// WHY: 긴 라벨(한글 2칸 포함)이 터미널 폭을 넘으면 터미널이 자동 줄바꿈해 물리적으로 2줄+가 된다.
//   커서 되감기(ESC[nA)는 물리 줄 기준이므로, 논리 줄 수만 세면 wrap된 만큼 덜 올라가
//   이전 출력이 안 지워지고 매 렌더마다 화면이 아래로 밀린다. (실측: Windows PowerShell 폭 80)
export function physicalRows(line, cols) {
  const w = visualWidth(line); // ANSI 시퀀스 제외 + CJK 2칸
  if (cols <= 0) return 1;
  // 빈 줄도 최소 1행. 폭의 정수배로 딱 떨어지면 wrap 안 되므로 그대로(80칸 라인@80폭 = 1행).
  if (w === 0) return 1;
  return Math.max(1, Math.ceil(w / cols));
}

// 여러 줄 지운 뒤 커서를 블록 시작으로 되돌리는 렌더러.
// 직전 렌더의 "물리 줄 수"만큼 위로 올라가 지우고 새로 그린다 (wrap 안전).
function makeRenderer() {
  let prevRows = 0; // 직전 렌더가 실제로 차지한 물리 줄 수
  return {
    render(lines) {
      if (prevRows > 0) stdout.write(`${ESC}${prevRows}A`); // 물리 줄 기준으로 위로
      stdout.write(`${ESC}0J`); // 커서 아래 전부 지우기
      stdout.write(lines.join("\n") + "\n");
      const cols = stdout.columns || 80; // 터미널 폭 (파이프 등으로 없으면 80 가정)
      prevRows = lines.reduce((sum, l) => sum + physicalRows(l, cols), 0);
    },
    reset() { prevRows = 0; },
  };
}

// raw keypress 세션 공통 래퍼. onKey(str,key) → true 반환 시 종료.
// 반환값은 finalize()가 만든다. 취소 시 CANCEL.
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
      // 취소: Ctrl+C / ESC
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
    renderFn(); // 최초 렌더
  });
}

// ── 단일 선택 (방향키 + Enter) ───────────────────────────────────────
// options: [{value,label,hint?}]. 반환: 선택 value 또는 CANCEL.
export async function select({ message, options, initialIndex = 0 }) {
  if (!stdin.isTTY) {
    // 비-TTY: 기본값(첫 항목) 반환 — 파이프 환경 방어
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
    // 숫자 점프 (1-9)
    if (/^[1-9]$/.test(str || "")) {
      const n = Number(str) - 1;
      if (n < options.length) { idx = n; return; }
      return;
    }
    if (key.name === "return" || key.name === "enter") return options[idx].value;
    return; // 그 외 키: 무시하고 계속
  });

  // 확정 화면 다시 그리기 (◇ 완료 심볼 + 선택값)
  if (result !== CANCEL) {
    const chosen = options.find((o) => o.value === result);
    r.render([S_BAR, `${S_DONE}  ${paint(message, c.dim)}`, `${S_BAR}  ${paint(chosen?.label ?? "", c.dim)}`]);
  }
  return result;
}

// ── 다중 선택 (Space 토글 + Enter) ──────────────────────────────────
// options: [{value,label,hint?,disabled?}]. 반환: 선택 value 배열 또는 CANCEL.
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

// ── 텍스트 입력 (Enter 확정, 빈 입력=기본값) ─────────────────────────
// 반환: 입력 문자열(빈 입력 시 defaultValue) 또는 CANCEL.
export async function text({ message, defaultValue = "" }) {
  if (!stdin.isTTY) return defaultValue;
  return new Promise((resolve) => {
    const wasRaw = stdin.isTTY ? stdin.isRaw : false;
    emitKeypressEvents(stdin);
    if (stdin.isTTY) stdin.setRawMode(true);
    stdin.resume();
    let buf = "";

    const prompt = () => {
      stdout.write(`\r${ESC}0K`); // 줄 초기화
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
      // 일반 문자 (제어문자 제외)
      if (str && !key.ctrl && !key.meta && str.length === 1 && str >= " ") { buf += str; prompt(); return; }
    };
    stdin.on("keypress", handler);
    prompt();
  });
}

// ── Y/N 확인 (←→ 또는 y/n, Enter 확정) ──────────────────────────────
// 반환: true/false 또는 CANCEL.
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

// ── 출력 헬퍼 (clack intro/outro/note/cancel 대체) ──────────────────
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
