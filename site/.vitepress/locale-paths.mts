// Single source of doc URL rules: English = root, Korean = /ko/ (#976)
// File locations stay as they are (code and CLAUDE.md reference docs/*.md paths)
//   docs/en/cli.md  > /cli
//   docs/CLI.md     > /ko/cli   (same slug in both languages > language switch lands on the same page)

// Docs at the top of docs/ that are not Korean (English originals)
const ENGLISH_TOP_LEVEL_FILES = new Set(['TRANSLATING.md'])

/**
 * Source file path (relative to srcDir) > site path (VitePress rewrites)
 */
export function toSitePath(sourcePath: string): string {
  if (sourcePath.startsWith('en/')) return sourcePath.slice('en/'.length)
  if (sourcePath.includes('/')) return sourcePath
  if (ENGLISH_TOP_LEVEL_FILES.has(sourcePath)) return sourcePath.toLowerCase()
  return `ko/${sourcePath.toLowerCase()}`
}

/**
 * Old URL (path without base) > new path, else null
 * Old English /en/cli > /cli, old Korean /CLI > /ko/cli
 */
export function toLegacyRedirectPath(pathname: string): string | null {
  const path = pathname.replace(/\.html$/, '')
  if (path === '/en' || path.startsWith('/en/')) return path.slice('/en'.length) || '/'
  // Old Korean doc names: one segment of uppercase, digits, hyphens (e.g. /SSH-DOCKER-DEPLOYMENT-GUIDE)
  const legacyKoreanPage = path.match(/^\/([A-Z][A-Z0-9-]*)$/)
  if (!legacyKoreanPage) return null
  const fileName = `${legacyKoreanPage[1]}.md`
  return `/${toSitePath(fileName).replace(/\.md$/, '')}`
}
