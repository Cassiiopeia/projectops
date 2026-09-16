// 설치 시점 baseline (#557) — 업데이트에서 "누가 바꿨는지"를 가르는 기준점.
//
// 왜 필요한가: isUnchanged()는 템플릿(theirs)과 설치본(ours)을 2-way로 비교한다.
// base가 없으니 업스트림이 한 글자만 고쳐도 사용자가 손대지 않은 파일이 changed로 떨어지고,
// 결국 "전부 skip(업데이트 못 받음)" 아니면 "전부 overwrite(사용자 수정 전멸)" 둘 중 하나만
// 고를 수 있게 된다. 정작 가려내야 할 진짜 충돌이 나머지에 묻힌다.
//
// 파일 사본이 아니라 해시만 남긴다 — 분류가 목적이지 자동 병합이 목적이 아니다.
//
// 해시를 두 개 두는 이유: env 치환으로 사용자 값이 들어간 파일은 디스크 내용과 "기본값으로
// 렌더한 결과"가 애초에 다르다. 하나로는 두 질문에 동시에 답할 수 없다.
//   - installed : 설치 시점 우리가 디스크에 쓴 내용     → "사용자가 그 뒤에 손댔는가"
//   - rendered  : 그 시점 템플릿을 기본값 치환한 결과   → "업스트림이 그 뒤에 바뀌었는가"
//
// installed는 우리가 실제로 쓴 파일에만 채운다. 사용자 수정본을 installed로 기록하면
// "우리가 쓴 것"이라고 거짓말하는 셈이고, 다음 업데이트에서 그 파일이 조용히 덮인다.
import { createHash } from "node:crypto";
import { join } from "node:path";
import { existsSync, readFileSync } from "node:fs";
import { writeText } from "./fsutil.js";

export const BASELINE_DIR = ".github/.projectops";
export const BASELINE_PATH = ".github/.projectops/baseline.json";

export function sha256(text) {
  return "sha256:" + createHash("sha256").update(String(text), "utf8").digest("hex");
}

// 없거나 깨졌으면 null — 호출부는 "base 미상"으로 폴백한다(조용히 빈 baseline을 쓰지 않는다.
// 빈 baseline은 "기록이 없다"가 아니라 "전부 삭제됐다"로 오해될 수 있다).
export function readBaseline(targetRoot = ".") {
  const p = join(targetRoot, BASELINE_PATH);
  if (!existsSync(p)) return null;
  try {
    const data = JSON.parse(readFileSync(p, "utf8"));
    if (!data || typeof data !== "object" || typeof data.files !== "object" || data.files === null) return null;
    return data;
  } catch {
    return null; // 손상된 baseline은 없는 것으로 취급 — 업데이트를 막지 않는다
  }
}

// entries: Map<filename, {installed?:string|null, rendered:string}>
// 기존 baseline은 병합 대상이다 — 이번 실행에서 건드리지 않은 파일의 기준점을 잃지 않는다.
export function writeBaseline(targetRoot, { templateVersion, installedAt, entries, previous = null }) {
  const files = { ...(previous?.files || {}) };
  for (const [filename, entry] of entries) {
    const prev = files[filename] || {};
    files[filename] = {
      // installed는 이번에 실제로 쓴 경우에만 갱신. 유지(skip)한 파일은 예전 기준점을 지킨다.
      installed: entry.installed ?? prev.installed ?? null,
      rendered: entry.rendered,
    };
  }
  const out = {
    templateVersion: templateVersion || "unknown",
    installedAt: installedAt || "",
    files,
  };
  writeText(join(targetRoot, BASELINE_PATH), JSON.stringify(out, null, 2) + "\n");
  return out;
}

// 사용자가 이 파일을 설치 후 손댔는가.
// baseline이 없거나 그 파일 기록이 없으면 null — "모른다"이지 "안 건드렸다"가 아니다.
// 호출부는 null을 현행 2-way 판정으로 폴백시켜야 한다.
export function isUserModified(baseline, filename, installedContent) {
  const rec = baseline?.files?.[filename];
  if (!rec || !rec.installed) return null;
  return rec.installed !== sha256(installedContent);
}

// baseline에는 있는데 디스크에 없는 파일 = 사용자가 지운 것.
// 별도의 삭제 이력 파일이 필요 없다는 것이 이 설계의 부산물이다.
// candidates: 템플릿이 이번에 설치하려는 파일명 목록 (그 밖의 baseline 항목은 관심 없다)
export function detectRemoved(baseline, candidates, workflowsDir) {
  if (!baseline) return [];
  const removed = [];
  for (const filename of candidates) {
    if (!baseline.files[filename]) continue;      // 우리가 설치한 적 없는 파일 — 판단 근거 없음
    if (existsSync(join(workflowsDir, filename))) continue;
    removed.push(filename);
  }
  return removed;
}
