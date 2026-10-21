// 고정 진입점 설치: ~/.projectops/bin/{projectops_cli.py, launch_cli.py} (#942·#897)
// SKILL.md 는 이 진입점을 먼저 부른다. 파이썬 쪽은 CLI 를 한 번 실행해야 진입점을 깔므로,
// 홈 복사 설치(Cursor·Copilot)는 첫 호출부터 길을 찾도록 설치 때 깐다 (#200).
// 규칙은 파이썬 refresh_stable_entrypoint 와 같다: 소스 RESOLVER_REVISION 이 깔린 것보다 높을 때만 덮는다.
import { join } from "node:path";
import { existsSync, readFileSync, mkdirSync, writeFileSync, chmodSync, renameSync } from "node:fs";

const REVISION_PATTERN = /^RESOLVER_REVISION = (\d+)/m;
// 진입점 권한: 직접 실행 가능 (rwxr-xr-x)
const STABLE_ENTRYPOINT_MODE = 0o755;
// 진입점 2종: (설치 이름, 소스 경로 계산)
const STABLE_ENTRYPOINTS = [
  { name: "projectops_cli.py", source: ({ scriptsSrc }) => scriptsSrc && join(scriptsSrc, "projectops_cli.py") },
  { name: "launch_cli.py", source: ({ skillsSrc }) => skillsSrc && join(skillsSrc, "pro-launch", "scripts", "launch_resolver.py") },
];

// 파일 > 내용 번호 (없거나 못 읽으면 -1)
function readRevision(file) {
  try {
    const match = REVISION_PATTERN.exec(readFileSync(file, "utf8"));
    return match ? Number(match[1]) : -1;
  } catch { return -1; }
}

/**
 * 진입점 갱신: 소스 번호 > 깔린 번호일 때만 임시 파일 > 권한 > 교체
 * 바꾼 진입점 이름 목록 반환. 실패는 예외로 올린다.
 */
export function refreshStableEntrypoints(projectopsHome, sources) {
  const binDir = join(projectopsHome, "bin");
  const updatedNames = [];
  for (const entry of STABLE_ENTRYPOINTS) {
    const sourceFile = entry.source(sources);
    if (!sourceFile || !existsSync(sourceFile)) continue;
    const target = join(binDir, entry.name);
    if (readRevision(sourceFile) <= readRevision(target)) continue;
    mkdirSync(binDir, { recursive: true });
    // 다른 세션이 동시에 읽어도 반쯤 쓴 파일을 보지 않게
    const temporary = `${target}.${process.pid}.tmp`;
    writeFileSync(temporary, readFileSync(sourceFile, "utf8"));
    chmodSync(temporary, STABLE_ENTRYPOINT_MODE);
    renameSync(temporary, target);
    updatedNames.push(entry.name);
  }
  return updatedNames;
}

// projectops 홈: io 가 주면 그 값 (테스트 격리), 아니면 ~/.projectops
export function projectopsHomeOf(io) {
  return typeof io.projectopsHome === "function" ? io.projectopsHome() : join(io.home(), ".projectops");
}
