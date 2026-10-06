// IDE Skills 설치 오케스트레이터 (.sh offer_ide_tools_install 등가).
// 레지스트리 기반 — 개별 IDE를 이름으로 알지 않고 ADAPTERS 배열만 순회한다.
// 새 IDE는 adapters/ 에 파일 추가 + registry 등록만으로 여기 수정 없이 동작한다.
import { ADAPTERS } from "../core/ide/registry.js";
import { versionTag } from "../core/ide/util.js";
import { defaultIo } from "../core/ide/runner.js";
import * as skillsPrompts from "../ui/skills-prompts.js";
import { t } from "../i18n/index.js";

// 상태 수집 → [{adapter, status}]. optional 어댑터는 감지 불가(cliMissing)면 목록에서 제외.
export function collectStatuses(io) {
  const rows = [];
  for (const a of ADAPTERS) {
    const status = safe(() => a.detect(io), { installed: false, version: null, cliMissing: true });
    if (a.optional && status.cliMissing) continue; // harness 등 조건부 항목은 불가 시 숨김
    rows.push({ adapter: a, status });
  }
  return rows;
}

// 상태 표시 문자열 목록 (표시용, 순수).
export function formatStatuses(rows, templateVersion) {
  return rows.map(({ adapter, status }) => {
    const label = adapter.label.padEnd(12);
    if (status.cliMissing) return `${label}: ${status.note || t("skills.status.noCli")}`;
    if (status.installed) {
      const v = status.version ? ` (v${status.version})` : "";
      return `${label}: ${t("skills.status.installed")}${v}${versionTag(status.version, templateVersion)}`;
    }
    return `${label}: ${status.note || t("skills.status.notInstalled")}`;
  });
}

// 대화형/비대화형 공통 진입. opts: {io, templateVersion, sourceSkillsDir, tempDir, interactive, ui, installedOnly}
// installedOnly(#502 — 업데이트 모드): 비대화형 apply를 이미 설치된 어댑터로 한정한다.
// 미설치 IDE에 새로 설치하지 않는다 — 업데이트는 "있는 것을 최신으로"가 계약.
export async function runSkills(opts = {}) {
  const io = opts.io || defaultIo();
  const ui = opts.ui || skillsPrompts;
  const ctx = { templateVersion: opts.templateVersion || "", sourceSkillsDir: opts.sourceSkillsDir, tempDir: opts.tempDir };

  const rows = collectStatuses(io);
  io.log("");
  io.log(t("skills.statusTitle"));
  for (const line of formatStatuses(rows, ctx.templateVersion)) io.log(line);
  io.log("");

  // 비대화형: 감지된(=관리 가능) 모든 어댑터에 apply(설치/업데이트) 순차 실행.
  // installedOnly면 설치된 어댑터만 (업데이트 모드 — 미설치 IDE는 건드리지 않음).
  if (!opts.interactive) {
    for (const { adapter, status } of rows) {
      if (opts.installedOnly && !status.installed) continue;
      safe(() => adapter.apply(io, ctx), false);
    }
    return 0;
  }

  // 대화형: 동작 선택 → IDE 멀티셀렉트 → 실행.
  const action = await ui.selectAction();
  if (action == null || action === skillsPrompts.CANCEL || action === "skip") {
    io.log(t("skills.unchanged"));
    return 0;
  }

  const choices = rows.map(({ adapter, status }) => ({
    id: adapter.id, label: adapter.label,
    disabled: action === "apply" && status.cliMissing, // 설치는 CLI 있어야, 제거는 무조건 후보
  }));
  const preselect = rows
    .filter(({ status }) => action === "apply" ? !status.cliMissing : true)
    .map(({ adapter }) => adapter.id);

  const targets = await ui.selectTargets(choices, preselect, action);
  if (targets == null || targets === skillsPrompts.CANCEL || !targets.length) {
    io.log(t("skills.noneSelected"));
    return 0;
  }

  const selected = new Set(targets);
  for (const { adapter } of rows) {
    if (!selected.has(adapter.id)) continue;
    io.log("");
    io.log(t(action === "apply" ? "skills.header.apply" : "skills.header.remove", { label: adapter.label }));
    safe(() => (action === "apply" ? adapter.apply(io, ctx) : adapter.remove(io, ctx)), false);
  }
  return 0;
}

function safe(fn, fallback) { try { return fn(); } catch { return fallback; } }
