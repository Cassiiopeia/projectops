// English messages (source of truth). Keys are grouped by area: <area>.<name>.
export default {
  // prompt engine hints
  "engine.hint.select": "↑/↓ move · Enter confirm · ESC cancel",
  "engine.hint.multiselect": "↑/↓ move · Space toggle · a all · Enter confirm · ESC cancel",
  "engine.hint.confirm": "←/→ or y/n · Enter confirm · ESC cancel",
  "engine.yes": "Yes",
  "engine.no": "No",
  "engine.none": "(none)",
  "engine.disabled": "This item cannot be selected.",
  "engine.required": "Select at least one.",
  "engine.cancelled": "Cancelled.",

  // main menu
  "mode.prompt": "What would you like to install?",
  "mode.update": "Update ({range})",
  "mode.full": "Full install (versioning + workflows + templates)",
  "mode.version": "Versioning only (automation system)",
  "mode.workflows": "Workflows only (GitHub Actions build and deploy)",
  "mode.issues": "Issue/PR templates only",
  "mode.skills": "AI skills only (Claude, Cursor, Gemini, Codex, PI)",

  // confirm and edit menus
  "confirm.prompt": "Continue with these settings?",
  "confirm.continue": "Yes, continue",
  "confirm.edit": "Edit",
  "confirm.cancel": "No, cancel",
  "edit.prompt": "Which setting do you want to change?",
  "edit.type": "Project type",
  "edit.version": "Version",
  "edit.branch": "Default branch",
  "edit.intent": "Project kind (deployment style)",
  "edit.deploy": "Deployment (server artifact)",
  "edit.publish": "Library publish targets",
  "edit.codeReview": "CodeRabbit code review",
  "edit.changelog": "Release notes (changelog) generator",
  "edit.releaseBranch": "Release source (development) branch",
  "edit.secret": "Include secret backup",
  "edit.done": "All correct, continue",
  "types.prompt": "Select project types (Space to toggle, Enter to confirm)",

  // help and errors
  "cli.nonTty": "Interactive input is not available. Pass --mode <full|version|workflows|issues> and --force.",
  "cli.needForce": "The --force option is required in a non-interactive environment.",
  "cli.langInvalid": "--lang must be one of: {values} (got '{value}')",
  "cli.langLine": "Language: {lang} ({source})",
  "cli.langSource.flag": "--lang",
  "cli.langSource.env": "PROJECTOPS_LANG",
  "cli.langSource.ci": "fixed for CI/--force",
  "cli.langSource.system": "system",
  "cli.langSource.default": "default",
};
