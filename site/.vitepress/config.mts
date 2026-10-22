import { defineConfig } from 'vitepress'
import { createRequire } from 'node:module'
import { dirname, join } from 'node:path'
import { cpSync, existsSync } from 'node:fs'
import { toSitePath } from './locale-paths.mts'

// srcDir 이 site/ 밖(../docs)이라 md 가 import 하는 vue 를 site/node_modules 에서 못 찾는다.
// 해석 기준을 site/ 로 고정해 alias 로 알려 준다.
const require = createRequire(import.meta.url)
const vueDir = dirname(require.resolve('vue/package.json'))

// 문서 원본은 저장소의 docs/ 하나뿐이다(내용 복제 금지). site/ 는 빌드 설정만 가진다.
// 영어 = 루트(docs/en/*), 한국어 = /ko/(docs/*). URL 규칙은 locale-paths.mts (#976)
// 로케일 추가(zh-CN, ja)는 locales 에 항목을 더하고 docs/<코드>/ 와 toSitePath 규칙을 만들면 된다.

const GITHUB = 'https://github.com/Cassiiopeia/projectops'

// 사이드바·상단 메뉴 단일 목록: slug 는 두 언어 공통 (en > /slug, ko > /ko/slug)
const SECTIONS = [
  {
    en: 'Guide',
    ko: '시작하기',
    pages: [
      { slug: 'getting-started', en: 'Getting started', ko: '시작하기' },
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
      { slug: 'branch-convention', en: 'Branch naming', ko: '브랜치 네이밍 규칙' },
      { slug: 'workflow-comment-guidelines', en: 'Workflow comment style', ko: '워크플로우 주석 표준' },
    ],
  },
]

type Lang = 'en' | 'ko'

// 언어별 링크 접두사 (en 루트, ko /ko)
const LINK_PREFIX: Record<Lang, string> = { en: '', ko: '/ko' }

function toPageLink(lang: Lang, slug: string): string {
  return `${LINK_PREFIX[lang]}/${slug}`
}

function buildSidebar(lang: Lang) {
  return SECTIONS.map((section) => ({
    text: section[lang],
    items: section.pages.map((page) => ({ text: page[lang], link: toPageLink(lang, page.slug) })),
  }))
}

// 상단 메뉴: 시작하기 · CLI · Skills · 워크플로우(inNav) · 문제 해결 · 기여자용
function buildNav(lang: Lang) {
  const sectionOf = (english: string) => SECTIONS.find((section) => section.en === english)!
  const toItems = (pages: (typeof SECTIONS)[number]['pages']) =>
    pages.map((page) => ({ text: page[lang], link: toPageLink(lang, page.slug) }))
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
  // hero 이미지처럼 frontmatter 에서 절대경로(/images/...)로 부르는 파일은 public 만 배포된다.
  // 원본을 docs/images 하나로 유지하려고 빌드 끝에 결과물로 복사한다. (본문 이미지는 상대경로로 쓴다)
  buildEnd(siteConfig) {
    const from = join(siteConfig.srcDir, 'images')
    if (existsSync(from)) cpSync(from, join(siteConfig.outDir, 'images'), { recursive: true })
  },
  title: 'Projectops',
  base: '/projectops/',
  srcDir: '../docs',
  rewrites: toSitePath,
  // 내부 작업 산출물·번역 README·내부 설계 문서는 사이트에 싣지 않는다.
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
  // 문서가 저장소 파일(.github/..., ../README.md)을 가리키는 링크는 사이트 안에 없다.
  ignoreDeadLinks: true,
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
      description: 'GitHub project automation template — from issue to deploy',
      themeConfig: {
        nav: buildNav('en'),
        sidebar: buildSidebar('en'),
      },
    },
    ko: {
      label: '한국어',
      lang: 'ko',
      link: '/ko/',
      description: 'GitHub 프로젝트 자동화 템플릿 — 이슈부터 배포까지',
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
