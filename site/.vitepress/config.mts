import { defineConfig } from 'vitepress'
import { createRequire } from 'node:module'
import { dirname, join, posix, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { cpSync, existsSync, readFileSync, writeFileSync } from 'node:fs'
import { toSitePath } from './locale-paths.mts'

// srcDir is outside site/ (../docs), so vue files imported by md can't be found in site/node_modules.
// Pin resolution to site/ and expose it via an alias.
const require = createRequire(import.meta.url)
const vueDir = dirname(require.resolve('vue/package.json'))

// The only docs source is the repo's docs/ (no copied content). site/ holds build config only.
// English = root (docs/en/*), Korean = /ko/ (docs/*). URL rules live in locale-paths.mts (#976)
// To add a locale (zh-CN, ja), add an entry to locales and create docs/<code>/ plus a toSitePath rule.

const GITHUB = 'https://github.com/Cassiiopeia/projectops'
const SITE_URL = 'https://cassiiopeia.github.io/projectops'
const SOCIAL_IMAGE = `${SITE_URL}/images/og.png`
const DESCRIPTION_MAX_LENGTH = 158
const SITE_DESCRIPTION: Record<'en' | 'ko', string> = {
  en: 'Open-source GitHub automation. One npx install sets up semantic versioning, changelogs, release PRs, CI/CD and AI agent skills for Spring, Flutter, React and Python.',
  ko: '오픈소스 GitHub 자동화. npx 한 번으로 시맨틱 버전, 체인지로그, 릴리스 PR, CI/CD, AI 에이전트 스킬을 Spring, Flutter, React, Python 프로젝트에 설치합니다.',
}

// Docs source folder (same as srcDir)
const DOCS_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'docs')

/**
 * Relative .md link between docs (relative to the source file) > absolute site path (rewrites applied), else null
 * e.g. ./NPX-WIZARD.md in docs/CLI.md > /ko/npx-wizard.md (left as is it breaks as /ko/NPX-WIZARD)
 */
function toSiteLinkHref(sourceRelativePath: string, href: string): string | null {
  // External URLs, schemes, anchors and absolute paths stay as is
  if (/^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith('#') || href.startsWith('/')) return null
  const hashIndex = href.indexOf('#')
  const linkPath = hashIndex < 0 ? href : href.slice(0, hashIndex)
  const hash = hashIndex < 0 ? '' : href.slice(hashIndex)
  if (!linkPath.endsWith('.md')) return null
  const resolvedPath = posix.normalize(posix.join(posix.dirname(sourceRelativePath), linkPath))
  // Links pointing outside docs/ are left alone (so the dead link check catches them)
  if (resolvedPath.startsWith('../')) return null
  return `/${toSitePath(resolvedPath)}${hash}`
}

// First paragraph of a doc > search result description (when frontmatter has no description)
// Heading id characters: VitePress default, with two GitHub-style changes (keep underscores · no _ prefix for leading digits)
// Doc links are written as GitHub anchors, so GitHub and the site must use the same ids
const HEADING_CONTROL_CHARACTERS = /[\u0000-\u001f]/g
const HEADING_SPECIAL_CHARACTERS = /[\s~`!@#$%^&*()\-+=[\]{}|\\;:"'“”‘’<>,.?/]+/g
const HEADING_COMBINING_MARKS = /[\u0300-\u036F]/g

/** Heading > id: strip accents then recompose NFC (keeps Hangul syllables), keep underscores, leading digits as is */
function toHeadingSlug(title: string): string {
  return title.normalize('NFKD').replace(HEADING_COMBINING_MARKS, '').replace(HEADING_CONTROL_CHARACTERS, '')
    .replace(HEADING_SPECIAL_CHARACTERS, '-').replace(/-{2,}/g, '-').replace(/^-+|-+$/g, '')
    .toLowerCase().normalize('NFC')
}

function firstParagraph(markdown: string): string {
  const body = markdown.replace(/\r\n/g, '\n').replace(/^---[\s\S]*?\n---\n/, '')
  const paragraph = body.split(/\n\s*\n/).find((block) => /^[^#|<>!`\-\s*]/.test(block.trim()) || /^\*\*/.test(block.trim())) ?? ''
  const plain = paragraph
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/[*`_]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  return plain.length > DESCRIPTION_MAX_LENGTH ? `${plain.slice(0, DESCRIPTION_MAX_LENGTH - 3).trimEnd()}...` : plain
}

function toPageUrl(slug: string): string {
  return `${SITE_URL}/${slug}`.replace(/\/$/, '/')
}

// Site path (ko/cli.md) > language and the slug shared by both languages
function parsePagePath(relativePath: string): { lang: 'en' | 'ko'; slug: string } {
  const path = relativePath.replace(/(^|\/)index\.md$/, '$1').replace(/\.md$/, '')
  return path === 'ko' || path.startsWith('ko/')
    ? { lang: 'ko', slug: path.replace(/^ko\/?/, '') }
    : { lang: 'en', slug: path }
}

// Single list for sidebar and top nav: slug shared by both languages (en > /slug, ko > /ko/slug)
const SECTIONS = [
  {
    en: 'Guide',
    ko: '시작하기',
    pages: [
      { slug: 'getting-started', en: 'Getting started', ko: '시작하기' },
      { slug: 'compare', en: 'Compared with other tools', ko: '다른 도구와 비교' },
      { slug: 'npx-wizard', en: 'NPX wizard', ko: 'NPX 마법사' },
      { slug: 'readme', en: 'Docs index', ko: '문서 인덱스' },
    ],
  },
  {
    en: 'CLI',
    ko: 'CLI',
    pages: [{ slug: 'cli', en: 'CLI reference', ko: 'CLI 레퍼런스' }],
  },
  {
    en: 'Agent Skills',
    ko: 'Skills',
    pages: [{ slug: 'skills', en: 'Skills guide', ko: 'Agent Skills 가이드' }],
  },
  {
    en: 'Workflows',
    ko: '워크플로우',
    pages: [
      { slug: 'version-control', en: 'Versioning', ko: '버전 관리', inNav: true },
      { slug: 'changelog-automation', en: 'Changelog automation', ko: '체인지로그 자동화', inNav: true },
      { slug: 'pr-preview', en: 'PR Preview', ko: 'PR Preview', inNav: true },
      { slug: 'issue-automation', en: 'Issue automation', ko: '이슈 자동화', inNav: true },
      { slug: 'ssh-docker-deployment-guide', en: 'SSH + Docker deploy', ko: 'SSH + Docker 배포', inNav: true },
      { slug: 'flutter-cicd-overview', en: 'Flutter CI/CD', ko: 'Flutter CI/CD 전체', inNav: true },
      { slug: 'flutter-testflight-wizard', en: 'TestFlight wizard', ko: 'TestFlight 마법사' },
      { slug: 'flutter-playstore-wizard', en: 'Play Store wizard', ko: 'Play Store 마법사' },
      { slug: 'flutter-firebase-wizard', en: 'Firebase wizard', ko: 'Firebase 마법사' },
      { slug: 'flutter-oauth-wizard', en: 'OAuth login wizard', ko: 'OAuth 로그인 마법사' },
      { slug: 'flutter-test-build-trigger', en: 'Test build trigger', ko: '테스트 빌드 트리거' },
      { slug: 'react-native-expo-cicd', en: 'React Native Expo CI/CD', ko: 'React Native Expo CI/CD', inNav: true },
      { slug: 'projects-sync', en: 'Projects sync', ko: 'Projects 동기화', inNav: true },
      { slug: 'github-projects-sync-wizard', en: 'Projects sync wizard', ko: 'Projects 동기화 마법사' },
    ],
  },
  {
    en: 'Help',
    ko: '설정 / 문제 해결',
    pages: [
      { slug: 'troubleshooting', en: 'Troubleshooting', ko: '문제 해결' },
      { slug: 'template-integrator', en: 'Integrator scripts (removed)', ko: '통합 스크립트(EOF 안내)' },
    ],
  },
  {
    en: 'Contributors',
    ko: '기여자용',
    pages: [
      { slug: 'contributing-guide', en: 'Contributing', ko: '기여하기' },
      { slug: 'branch-convention', en: 'Branch naming', ko: '브랜치 네이밍 규칙' },
      { slug: 'workflow-comment-guidelines', en: 'Workflow comment style', ko: '워크플로우 주석 표준' },
      // Docs that exist only in English (locale-paths.mts ENGLISH_TOP_LEVEL_FILES) > both languages link to the English path
      { slug: 'translating', en: 'Translating', ko: 'Translating (영문)', isEnglishOnly: true },
    ],
  },
]

type Lang = 'en' | 'ko'

// Link prefix per language (en root, ko /ko)
const LINK_PREFIX: Record<Lang, string> = { en: '', ko: '/ko' }

function toPageLink(lang: Lang, slug: string): string {
  return `${LINK_PREFIX[lang]}/${slug}`
}

// Sidebar/nav item > link (English-only docs use the English path regardless of language)
function toSectionPageLink(lang: Lang, page: (typeof SECTIONS)[number]['pages'][number]): string {
  return toPageLink('isEnglishOnly' in page && page.isEnglishOnly ? 'en' : lang, page.slug)
}

function buildSidebar(lang: Lang) {
  return SECTIONS.map((section) => ({
    text: section[lang],
    items: section.pages.map((page) => ({ text: page[lang], link: toSectionPageLink(lang, page) })),
  }))
}

// Top nav: Getting started · CLI · Skills · Workflows (inNav) · Troubleshooting · Contributors
function buildNav(lang: Lang) {
  const sectionOf = (english: string) => SECTIONS.find((section) => section.en === english)!
  const toItems = (pages: (typeof SECTIONS)[number]['pages']) =>
    pages.map((page) => ({ text: page[lang], link: toSectionPageLink(lang, page) }))
  const workflows = sectionOf('Workflows')
  const contributors = sectionOf('Contributors')
  return [
    { text: lang === 'en' ? 'Getting started' : '시작하기', link: toPageLink(lang, 'getting-started') },
    { text: 'CLI', link: toPageLink(lang, 'cli') },
    { text: 'Skills', link: toPageLink(lang, 'skills') },
    { text: workflows[lang], items: toItems(workflows.pages.filter((page) => 'inNav' in page && page.inNav)) },
    { text: lang === 'en' ? 'Troubleshooting' : '문제 해결', link: toPageLink(lang, 'troubleshooting') },
    { text: contributors[lang], items: toItems(contributors.pages) },
  ]
}

export default defineConfig({
  // Files referenced by absolute path in frontmatter (/images/..., like the hero image) are deployed only from public.
  // To keep docs/images as the single source, copy them into the output at build end. (Body images use relative paths)
  buildEnd(siteConfig) {
    const from = join(siteConfig.srcDir, 'images')
    if (existsSync(from)) cpSync(from, join(siteConfig.outDir, 'images'), { recursive: true })
    // Guidance file for AI search. Crawlers read robots.txt only at the domain root, so a subpath is useless
    cpSync(join(siteConfig.root, '..', 'llms.txt'), join(siteConfig.outDir, 'llms.txt'))
  },
  sitemap: { hostname: `${SITE_URL}/` },
  transformPageData(pageData, { siteConfig }) {
    if (pageData.frontmatter.description || pageData.frontmatter.layout === 'home') return
    const source = join(siteConfig.srcDir, pageData.filePath)
    const description = existsSync(source) ? firstParagraph(readFileSync(source, 'utf8')) : ''
    if (description) return { description }
  },
  transformHead({ pageData, siteData }) {
    if (pageData.isNotFound) return []
    const { lang, slug } = parsePagePath(pageData.relativePath)
    const englishUrl = toPageUrl(slug)
    const koreanUrl = toPageUrl(slug ? `ko/${slug}` : 'ko/')
    const url = lang === 'en' ? englishUrl : koreanUrl
    const description = pageData.frontmatter.description || pageData.description || SITE_DESCRIPTION[lang]
    const title = pageData.frontmatter.titleTemplate === false
      ? pageData.title
      : `${pageData.title} | ${siteData.title}`
    const head: [string, Record<string, string>, string?][] = [
      ['link', { rel: 'canonical', href: url }],
      ['link', { rel: 'alternate', hreflang: 'en', href: englishUrl }],
      ['link', { rel: 'alternate', hreflang: 'ko', href: koreanUrl }],
      ['link', { rel: 'alternate', hreflang: 'x-default', href: englishUrl }],
      ['meta', { property: 'og:type', content: slug ? 'article' : 'website' }],
      ['meta', { property: 'og:site_name', content: siteData.title }],
      ['meta', { property: 'og:title', content: title }],
      ['meta', { property: 'og:description', content: description }],
      ['meta', { property: 'og:url', content: url }],
      ['meta', { property: 'og:image', content: SOCIAL_IMAGE }],
      ['meta', { property: 'og:locale', content: lang === 'en' ? 'en_US' : 'ko_KR' }],
      ['meta', { name: 'twitter:card', content: 'summary_large_image' }],
      ['meta', { name: 'twitter:title', content: title }],
      ['meta', { name: 'twitter:description', content: description }],
      ['meta', { name: 'twitter:image', content: SOCIAL_IMAGE }],
    ]
    if (!slug) {
      head.push(['script', { type: 'application/ld+json' }, JSON.stringify({
        '@context': 'https://schema.org',
        '@type': 'SoftwareApplication',
        name: siteData.title,
        description: SITE_DESCRIPTION[lang],
        url,
        applicationCategory: 'DeveloperApplication',
        operatingSystem: 'Windows, macOS, Linux',
        license: 'https://opensource.org/licenses/MIT',
        sameAs: [GITHUB, 'https://www.npmjs.com/package/projectops'],
        offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
      })])
    }
    return head
  },
  title: 'Projectops',
  base: '/projectops/',
  srcDir: '../docs',
  rewrites: toSitePath,
  // Internal work output, translated READMEs and internal design docs are not published on the site.
  srcExclude: [
    'projectops/**',
    'superpowers/**',
    'qa/**',
    'suh-template/**',
    'i18n/**',
    'architecture/**',
    'HARNESS-PATTERNS.md',
    'recording/**',
  ],
  cleanUrls: true,
  vite: {
    resolve: {
      alias: [
        { find: /^vue\/server-renderer$/, replacement: `${vueDir}/server-renderer/index.mjs` },
        { find: /^vue$/, replacement: `${vueDir}/dist/vue.runtime.esm-bundler.js` },
      ],
    },
  },
  lastUpdated: false,
  // Repo file links are written as absolute GitHub URLs in docs > a broken relative link fails the build
  ignoreDeadLinks: false,
  markdown: {
    // Heading id: VitePress default rule + NFC recompose at the end — the default leaves Hangul as jamo (NFKD), breaking Korean anchor links in docs
    anchor: { slugify: toHeadingSlug },
    config(md) {
      // Rewrite relative .md links to site paths before link render (VitePress then handles base, cleanUrls and the dead link check)
      md.core.ruler.push('projectops-site-links', (state) => {
        const realPath: string | undefined = state.env?.realPath ?? state.env?.path
        if (!realPath) return
        const sourceRelativePath = relative(DOCS_DIR, realPath).split(sep).join('/')
        for (const blockToken of state.tokens) {
          for (const inlineToken of blockToken.children ?? []) {
            if (inlineToken.type !== 'link_open') continue
            const siteHref = toSiteLinkHref(sourceRelativePath, inlineToken.attrGet('href') ?? '')
            if (siteHref) inlineToken.attrSet('href', siteHref)
          }
        }
      })
    },
  },
  head: [['link', { rel: 'icon', href: '/projectops/images/hero.webp' }]],
  themeConfig: {
    search: {
      provider: 'local',
      options: {
        locales: {
          ko: {
            translations: {
              button: { buttonText: '검색', buttonAriaLabel: '검색' },
              modal: {
                noResultsText: '결과가 없습니다',
                resetButtonTitle: '지우기',
                footer: { selectText: '선택', navigateText: '이동', closeText: '닫기' },
              },
            },
          },
        },
      },
    },
    socialLinks: [{ icon: 'github', link: GITHUB }],
    outline: { level: [2, 3] },
  },
  locales: {
    root: {
      label: 'English',
      lang: 'en',
      description: SITE_DESCRIPTION.en,
      themeConfig: {
        nav: buildNav('en'),
        sidebar: buildSidebar('en'),
      },
    },
    ko: {
      label: '한국어',
      lang: 'ko',
      link: '/ko/',
      description: SITE_DESCRIPTION.ko,
      themeConfig: {
        nav: buildNav('ko'),
        sidebar: buildSidebar('ko'),
        outlineTitle: '이 페이지 목차',
        docFooter: { prev: '이전', next: '다음' },
        darkModeSwitchLabel: '테마',
        sidebarMenuLabel: '메뉴',
        returnToTopLabel: '맨 위로',
      },
    },
  },
})
