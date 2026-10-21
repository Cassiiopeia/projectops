// 문서 URL 규칙 단일 원본: 영어 = 루트, 한국어 = /ko/ (#976)
// 파일 위치는 그대로 둔다 (docs/*.md 경로를 코드·CLAUDE.md가 참조)
//   docs/en/cli.md  > /cli
//   docs/CLI.md     > /ko/cli   (두 언어 slug 동일 > 언어 전환이 같은 쪽으로 이동)

// docs/ 최상위에 있지만 한국어가 아닌 문서 (영어 원문)
const ENGLISH_TOP_LEVEL_FILES = new Set(['TRANSLATING.md'])

/**
 * 원본 파일 경로(srcDir 기준) > 사이트 경로 (VitePress rewrites)
 */
export function toSitePath(sourcePath: string): string {
  if (sourcePath.startsWith('en/')) return sourcePath.slice('en/'.length)
  if (sourcePath.includes('/')) return sourcePath
  if (ENGLISH_TOP_LEVEL_FILES.has(sourcePath)) return sourcePath.toLowerCase()
  return `ko/${sourcePath.toLowerCase()}`
}

/**
 * 옛 URL(base 제외 경로) > 새 경로, 해당 없으면 null
 * 옛 영어 /en/cli > /cli, 옛 한국어 /CLI > /ko/cli
 */
export function toLegacyRedirectPath(pathname: string): string | null {
  const path = pathname.replace(/\.html$/, '')
  if (path === '/en' || path.startsWith('/en/')) return path.slice('/en'.length) || '/'
  // 옛 한국어 문서명: 대문자·숫자·하이픈 한 단계 (예: /SSH-DOCKER-DEPLOYMENT-GUIDE)
  const legacyKoreanPage = path.match(/^\/([A-Z][A-Z0-9-]*)$/)
  if (!legacyKoreanPage) return null
  const fileName = `${legacyKoreanPage[1]}.md`
  return `/${toSitePath(fileName).replace(/\.md$/, '')}`
}
