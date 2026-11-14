// IDE skills interactive prompts.
// Uses an in-house node:readline engine (@clack/prompts was removed because of the Windows TTY Enter bug).
import * as engine from "./readline-engine.js";
import { t } from "../i18n/index.js";

export const CANCEL = engine.CANCEL;

// Action choice: install/update · remove · leave as is. Cancel = skip.
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

// IDE multiselect. choices=[{id,label,disabled}], preselect=[id...], action.
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
