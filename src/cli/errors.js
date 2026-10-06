import { t } from "../i18n/index.js";

// 예기치 못한 예외를 사용자가 읽을 수 있는 한 줄 오류 + 조치 안내로 바꾼다 (#672).
// 스택 트레이스는 사용자가 고칠 수 있는 정보가 아니므로 DEBUG 환경변수가 있을 때만 노출한다.

// err → { message, hint }. 분류 근거는 Node 가 던지는 err.code / 메시지 형식이다.
export function describeError(err) {
  const msg = String(err?.message || err);
  const code = err?.code;

  // PATH 에 git 이 없음 — spawn 계열이 ENOENT 를 던진다
  if (code === "ENOENT" && /\bgit\b/.test(`${err?.path ?? ""} ${err?.syscall ?? ""} ${msg}`)) {
    return { message: t("errors.git.message"), hint: t("errors.git.hint") };
  }
  // 템플릿 내려받기 실패 — execFileSync 가 "Command failed: git clone ..." 를 던진다
  if (/Command failed: git clone/.test(msg)) {
    return {
      message: t("errors.clone.message"),
      hint: t("errors.clone.hint"),
    };
  }
  // 권한/읽기 전용 파일시스템
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

// 오류를 stderr 로 출력한다. 호출부는 비0 종료코드를 돌려주면 된다.
export function reportFatal(err, { env = process.env, write = (s) => process.stderr.write(s) } = {}) {
  const { message, hint } = describeError(err);
  write(`❌ ${message}\n`);
  if (hint) write(`   ${hint}\n`);
  if (env.DEBUG) write(`\n${err?.stack || err}\n`);
}
