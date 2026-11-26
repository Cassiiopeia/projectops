// Screen shown when the user cuts the run off with Ctrl+C (#1275):
// says the run stopped, whether repository files were already changed, and how to review them.
import { MIGRATION_DIR } from "../core/run-trace.js";
import { t } from "../i18n/index.js";

// Trace events that mean a file in the target repository was written (install step, old workflow renamed to .bak)
const isRepoWriteEvent = (event) =>
  (event.phase === "step" && event.action === "start" && String(event.target).startsWith("install-"))
  || ((event.phase === "legacy" || event.phase === "orphan") && event.action === "neutralized");

export const hasChangedRepoFiles = (events) => events.some(isRepoWriteEvent);

export function printCancelNotice(events, write = (line) => process.stdout.write(`${line}\n`)) {
  write("");
  write(t("flow.cancelCtrlC"));
  if (hasChangedRepoFiles(events)) {
    write(t("flow.cancelPartial"));
    write(t("flow.cancelReview"));
  } else {
    write(t("flow.cancelUntouched"));
  }
  write(t("flow.cancelLog", { dir: MIGRATION_DIR }));
}
