// Shared IDE adapter contract (the core of the extension point).
//
// To support a new IDE (editor/agent CLI), create one object satisfying this shape
// in src/core/ide/adapters/<name>.js and add it to the registry.js array — that is all.
// The orchestrator (commands/skills.js) knows only adapter fields, nothing about individual IDE logic.
//
// @typedef {Object} IdeStatus
//   installed: boolean       whether it is installed
//   version:   string|null   installed version (if known)
//   cliMissing: boolean      whether install is impossible because the dedicated CLI is missing (notice only)
//   note:      string        short note appended to the status line (optional)
//
// @typedef {Object} IdeAdapter
//   id:      string   internal unique key (e.g. "claude"). Used for routing and preselect
//   label:   string   name shown to people (e.g. "Claude Code")
//   order:   number   status/menu display order (smaller first)
//   detect(io): IdeStatus                     current install status
//   apply(io, ctx): boolean                   install or update (idempotent). true on success
//   remove(io, ctx): boolean                  remove (no-op if not installed, true)
//   manualHint(io): string                    manual install command shown when the CLI is missing (optional)
//
// io = runner.defaultIo() or a test stub: { which, run, home, log, projectopsHome? (default home/.projectops) }
// ctx = { templateVersion, sourceSkillsDir } — shared context such as version display and the Cursor copy source
//
// Rules:
//  - apply/remove/detect never throw (absorbed internally). Failure is expressed as log + false.
//  - A missing CLI is not an error but a cliMissing state + manualHint notice.
//  - Adapters interact with the outside only through io (no direct spawnSync/console) — for testability.

// Helper that checks during development that adapters keep the minimum contract (runtime guard).
export function assertAdapter(a) {
  for (const k of ["id", "label", "detect", "apply", "remove"]) {
    if (a[k] == null) throw new Error(`IDE adapter '${a?.id || "?"}' is missing required field '${k}'`);
  }
  return a;
}
