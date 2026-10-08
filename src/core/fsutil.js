// 파일시스템 공용 유틸 (LF 보존 바이트 복사). 텍스트는 그대로 복사해 원본 줄바꿈 유지.
import {
  cpSync, existsSync, readFileSync, writeFileSync, mkdirSync,
  readdirSync, rmSync,
} from "node:fs";
import { dirname } from "node:path";

export const exists = (p) => existsSync(p);
export const readText = (p) => readFileSync(p, "utf8");

export function writeText(p, s) {
  mkdirSync(dirname(p), { recursive: true });
  writeFileSync(p, s);
}

// 단일 파일 복사 (부모 디렉토리 자동 생성, 바이트 그대로)
export function copyFileSync(src, dst) {
  mkdirSync(dirname(dst), { recursive: true });
  cpSync(src, dst);
}

// 디렉토리 재귀 복사 (내용을 dst 하위로)
export function copyDirSync(src, dst, { filter } = {}) {
  mkdirSync(dst, { recursive: true });
  cpSync(src, dst, { recursive: true, ...(filter ? { filter } : {}) });
}

// 파일/폴더 삭제 (없어도 무해)
export function remove(p) {
  rmSync(p, { recursive: true, force: true });
}

// 디렉토리 직하위 .yaml/.yml 파일명 목록. 하위 폴더 제외.
// 정렬 순서는 .sh의 glob `"$_dir"/*.yaml "$_dir"/*.yml` 와 일치시킨다:
// 확장자로 1차 그룹(.yaml 먼저 → .yml 나중), 각 그룹 안에서 알파벳순.
// (단순 .sort()는 확장자를 섞어 정렬해 .sh와 파일 순회 순서가 갈리고,
//  그 결과 version.yml deploy 블록의 키 순서까지 달라진다. 확장자 그룹핑으로 바이트 등가 확보.)
export function listYamlFiles(dir) {
  if (!existsSync(dir)) return [];
  const names = readdirSync(dir, { withFileTypes: true })
    .filter((e) => e.isFile() && /\.(ya?ml)$/.test(e.name))
    .map((e) => e.name);
  const yaml = names.filter((n) => n.endsWith(".yaml")).sort();
  const yml = names.filter((n) => n.endsWith(".yml")).sort();
  return [...yaml, ...yml];
}
