import { t } from "../i18n/index.js";

// Turns unexpected exceptions into a readable one-line error + action hint (#672).
// A stack trace is not something users can fix, so it is shown only when the DEBUG env var is set.

// err → { message, hint }. Classified by the err.code / message format Node throws.
export function describeError(err) {
  const msg = String(err?.message || err);
  const code = err?.code;

  // git is not on PATH — spawn-family calls throw ENOENT
  if (code === "ENOENT" && /\bgit\b/.test(`${err?.path ?? ""} ${err?.syscall ?? ""} ${msg}`)) {
    return { message: t("errors.git.message"), hint: t("errors.git.hint") };
  }
  // Template download failed — execFileSync throws "Command failed: git clone ..."
  if (/Command failed: git clone/.test(msg)) {
    // Windows path length limit — blaming the network would send people to the wrong place
    if (/Filename too long|cannot stat/i.test(msg)) {
      return { message: t("errors.clone.pathTooLong.message"), hint: t("errors.clone.pathTooLong.hint") };
    }
    return {
      message: t("errors.clone.message"),
      hint: t("errors.clone.hint"),
    };
  }
  // Permission / read-only filesystem
  if (code === "EACCES" || code === "EPERM" || code === "EROFS") {
    const where = err?.path ? ` (${err.path})` : "";
    return {
      message: t("errors.write.message", { where }),
      hint: t("errors.write.hint"),
    };
  }
  if (code === "ENOSPC") {
    return { message: t("errors.disk.message"), hint: t("errors.disk.hint") };
  }
  return { message: t("errors.unexpected.message", { msg }), hint: t("errors.unexpected.hint") };
}

// Print the error to stderr. The caller just returns a non-zero exit code.
export function reportFatal(err, { env = process.env, write = (s) => process.stderr.write(s) } = {}) {
  const { message, hint } = describeError(err);
  write(`❌ ${message}\n`);
  if (hint) write(`   ${hint}\n`);
  if (env.DEBUG) write(`\n${err?.stack || err}\n`);
}
