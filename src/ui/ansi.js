// Shared ANSI helpers — shared by banner/status-cards (independent of readline-engine's internal helpers, zero dependencies)
const E = "\x1b[";
export const A = {
  reset: `${E}0m`,
  bold: `${E}1m`,
  dim: `${E}2m`,
  cyan: `${E}36m`,
  green: `${E}32m`,
  yellow: `${E}33m`,
  magenta: `${E}35m`,
  gray: `${E}90m`,
};
export const paint = (s, color) => `${color}${s}${A.reset}`;

// Approximate display width (CJK 2 cells · ANSI sequences 0) — for aligning the box's right edge
export function visualWidth(s) {
  const plain = String(s).replace(/\x1b\[[0-9;]*m/g, "");
  let w = 0;
  for (const ch of plain) {
    const cp = ch.codePointAt(0);
    // Korean, CJK and emoji are roughly 2 cells (terminal convention)
    w += (cp >= 0x1100 && (cp <= 0x115f || (cp >= 0x2e80 && cp <= 0xa4cf) || (cp >= 0xac00 && cp <= 0xd7a3)
      || (cp >= 0xf900 && cp <= 0xfaff) || (cp >= 0xff00 && cp <= 0xff60) || cp >= 0x1f300)) ? 2 : 1;
  }
  return w;
}

// Pad with spaces on the right by visual width (CJK 2 cells) — for aligning columns of mixed Korean/English labels.
// JS's built-in String.padEnd counts characters, so columns drift when Korean is mixed in.
export function padEndVisual(s, targetWidth) {
  const pad = targetWidth - visualWidth(s);
  return pad > 0 ? String(s) + " ".repeat(pad) : String(s);
}
