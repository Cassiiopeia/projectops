// Start screen banner (layer 1). Classic boxed title, kept from the original wizard.
import { A, paint, visualWidth } from "./ansi.js";
import { t, getLang, getLangSource } from "../i18n/index.js";

const INNER = 56; // inner width of the box

function boxLine(out, content = "") {
  const pad = Math.max(0, INNER - visualWidth(content));
  out(paint("║", A.cyan) + content + " ".repeat(pad) + paint("║", A.cyan) + "\n");
}

// Interactive banner: boxed title + meta lines. The language line says which language is used and why,
// so a different locale on a teammate's machine is never a surprise.
export function printBanner({ version, modeLabel }, out = (s) => process.stdout.write(s)) {
  out("\n");
  out(paint(`╔${"═".repeat(INNER)}╗`, A.cyan) + "\n");
  boxLine(out);
  boxLine(out, `      ${paint("✦", A.yellow)}  ${paint("P R O J E C T O P S", A.bold)}  ${paint("✦", A.yellow)}`);
  boxLine(out);
  out(paint(`╚${"═".repeat(INNER)}╝`, A.cyan) + "\n");
  out(`     🌙 Version : ${paint(`v${version}`, A.green)}\n`);
  out(`     🐵 Author  : Cassiiopeia\n`);
  out(`     🪐 Mode    : ${modeLabel}\n`);
  out(`     🌐 Language: ${getLang()} (${t(`cli.langSource.${getLangSource()}`)})\n`);
  out(`     📦 Repo    : ${paint("github.com/Cassiiopeia/projectops", A.dim)}\n`);
  out("\n");
}

// One-line banner for non-interactive runs (--force / CI): keeps logs short but still shows the version.
export function printBannerCompact({ version, mode }, out = (s) => process.stdout.write(s)) {
  out(`${paint("✦", A.yellow)} ${paint("projectops", A.bold)} v${version} ${t("banner.compactMode", { mode })}\n`);
}
