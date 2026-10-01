// 예기치 못한 예외를 사용자가 읽을 수 있는 한 줄 오류 + 조치 안내로 바꾼다 (#672).
// 스택 트레이스는 사용자가 고칠 수 있는 정보가 아니므로 DEBUG 환경변수가 있을 때만 노출한다.

// err → { message, hint }. 분류 근거는 Node 가 던지는 err.code / 메시지 형식이다.
export function describeError(err) {
  const msg = String(err?.message || err);
  const code = err?.code;

  // PATH 에 git 이 없음 — spawn 계열이 ENOENT 를 던진다
  if (code === "ENOENT" && /\bgit\b/.test(`${err?.path ?? ""} ${err?.syscall ?? ""} ${msg}`)) {
    return { message: "git 을 실행할 수 없습니다.", hint: "git 이 설치되어 있고 PATH 에 있는지 확인하세요." };
  }
  // 템플릿 내려받기 실패 — execFileSync 가 "Command failed: git clone ..." 를 던진다
  if (/Command failed: git clone/.test(msg)) {
    return {
      message: "템플릿을 내려받지 못했습니다.",
      hint: "네트워크·프록시 설정과 GitHub 접근 가능 여부를 확인한 뒤 다시 실행하세요.",
    };
  }
  // 권한/읽기 전용 파일시스템
  if (code === "EACCES" || code === "EPERM" || code === "EROFS") {
    const where = err?.path ? ` (${err.path})` : "";
    return {
      message: `파일을 쓸 수 없습니다${where}.`,
      hint: "프로젝트 폴더와 .github 폴더의 쓰기 권한(읽기 전용 여부)을 확인하세요.",
    };
  }
  if (code === "ENOSPC") {
    return { message: "디스크 공간이 부족합니다.", hint: "공간을 확보한 뒤 다시 실행하세요." };
  }
  return { message: `예기치 못한 오류: ${msg}`, hint: "자세한 내용은 DEBUG=1 로 다시 실행하면 볼 수 있습니다." };
}

// 오류를 stderr 로 출력한다. 호출부는 비0 종료코드를 돌려주면 된다.
export function reportFatal(err, { env = process.env, write = (s) => process.stderr.write(s) } = {}) {
  const { message, hint } = describeError(err);
  write(`❌ ${message}\n`);
  if (hint) write(`   ${hint}\n`);
  if (env.DEBUG) write(`\n${err?.stack || err}\n`);
}
