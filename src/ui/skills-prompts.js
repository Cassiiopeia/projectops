// IDE Skills 대화형 프롬프트 (.sh 라우터 choose_menu 등가).
// node:readline 기반 자체 엔진 사용 (@clack/prompts 는 Windows TTY Enter 버그로 제거).
import * as engine from "./readline-engine.js";
import { t } from "../i18n/index.js";

export const CANCEL = engine.CANCEL;

// 동작 선택: 설치/업데이트 · 제거 · 그대로. 취소=skip.
export async function selectAction() {
  const v = await engine.select({
    message: t("skills.action.prompt"),
    options: [
      { value: "apply", label: t("skills.action.apply") },
      { value: "remove", label: t("skills.action.remove") },
      { value: "skip", label: t("skills.action.skip") },
    ],
  });
  return v === CANCEL ? "skip" : v;
}

// IDE 멀티셀렉트. choices=[{id,label,disabled}], preselect=[id...], action.
export async function selectTargets(choices, preselect = [], action = "apply") {
  const options = choices.map((c) => ({
    value: c.id,
    label: c.label + (c.disabled ? t("skills.target.undetected") : ""),
    hint: c.disabled ? t("ide.cliMissing") : undefined,
    disabled: c.disabled,
  }));
  return engine.multiselect({
    message: t(action === "apply" ? "skills.target.promptApply" : "skills.target.promptRemove"),
    options,
    initialValues: preselect,
    required: false,
  });
}

export function note(text, title) { engine.note(text, title); }
