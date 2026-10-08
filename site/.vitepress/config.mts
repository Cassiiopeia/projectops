import { defineConfig } from 'vitepress'
import { createRequire } from 'node:module'
import { dirname, join } from 'node:path'
import { cpSync, existsSync } from 'node:fs'

// srcDir 이 site/ 밖(../docs)이라 md 가 import 하는 vue 를 site/node_modules 에서 못 찾는다.
// 해석 기준을 site/ 로 고정해 alias 로 알려 준다.
const require = createRequire(import.meta.url)
const vueDir = dirname(require.resolve('vue/package.json'))

// 문서 원본은 저장소의 docs/ 하나뿐이다(내용 복제 금지). site/ 는 빌드 설정만 가진다.
// 로케일 추가(zh-CN, ja)는 아래 locales 에 항목을 더하고 docs/<코드>/ 를 만들면 된다.

const GITHUB = 'https://github.com/Cassiiopeia/projectops'

const koSidebar = [
  {
    text: '시작하기',
    items: [
      { text: '시작하기', link: '/GETTING-STARTED' },
      { text: 'NPX 마법사', link: '/NPX-WIZARD' },
      { text: '문서 인덱스', link: '/README' },
    ],
  },
  {
    text: 'CLI',
    items: [{ text: 'CLI 레퍼런스', link: '/CLI' }],
  },
  {
    text: 'Skills',
    items: [{ text: 'Agent Skills 가이드', link: '/SKILLS' }],
  },
  {
    text: '워크플로우',
    items: [
      { text: '버전 관리', link: '/VERSION-CONTROL' },
      { text: '체인지로그 자동화', link: '/CHANGELOG-AUTOMATION' },
      { text: 'PR Preview', link: '/PR-PREVIEW' },
      { text: '이슈 자동화', link: '/ISSUE-AUTOMATION' },
      { text: 'SSH + Docker 배포', link: '/SSH-DOCKER-DEPLOYMENT-GUIDE' },
      { text: 'Flutter CI/CD 전체', link: '/FLUTTER-CICD-OVERVIEW' },
      { text: 'TestFlight 마법사', link: '/FLUTTER-TESTFLIGHT-WIZARD' },
      { text: 'Play Store 마법사', link: '/FLUTTER-PLAYSTORE-WIZARD' },
      { text: 'Firebase 마법사', link: '/FLUTTER-FIREBASE-WIZARD' },
      { text: '테스트 빌드 트리거', link: '/FLUTTER-TEST-BUILD-TRIGGER' },
      { text: 'Projects 동기화', link: '/PROJECTS-SYNC' },
      { text: 'Projects 동기화 마법사', link: '/GITHUB-PROJECTS-SYNC-WIZARD' },
    ],
  },
  {
    text: '설정 / 문제 해결',
    items: [
      { text: '문제 해결', link: '/TROUBLESHOOTING' },
      { text: '통합 스크립트(EOF 안내)', link: '/TEMPLATE-INTEGRATOR' },
    ],
  },
  {
    text: '기여자용',
    items: [
      { text: '브랜치 네이밍 규칙', link: '/BRANCH-CONVENTION' },
      { text: '워크플로우 주석 표준', link: '/WORKFLOW-COMMENT-GUIDELINES' },
    ],
  },
]

const enSidebar = [
  {
    text: 'Guide',
    items: [
      { text: 'Getting started', link: '/en/getting-started' },
      { text: 'CLI summary', link: '/en/cli' },
    ],
  },
  {
    text: 'Workflows',
    items: [
      { text: 'Versioning', link: '/en/version-control' },
      { text: 'Changelog automation', link: '/en/changelog-automation' },
      { text: 'Issue automation', link: '/en/issue-automation' },
    ],
  },
  {
    text: 'Help',
    items: [{ text: 'Troubleshooting', link: '/en/troubleshooting' }],
  },
]

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
  // 내부 작업 산출물과 번역 README 는 사이트에 싣지 않는다.
  srcExclude: [
    'projectops/**',
    'superpowers/**',
    'qa/**',
    'suh-template/**',
    'i18n/**',
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
    search: { provider: 'local' },
    socialLinks: [{ icon: 'github', link: GITHUB }],
    outline: { level: [2, 3] },
  },
  locales: {
    root: {
      label: '한국어',
      lang: 'ko',
      description: 'GitHub 프로젝트 자동화 템플릿 — 이슈부터 배포까지',
      themeConfig: {
        nav: [
          { text: '시작하기', link: '/GETTING-STARTED' },
          { text: 'CLI', link: '/CLI' },
          { text: 'Skills', link: '/SKILLS' },
          {
            text: '워크플로우',
            items: [
              { text: '버전 관리', link: '/VERSION-CONTROL' },
              { text: '체인지로그', link: '/CHANGELOG-AUTOMATION' },
              { text: 'PR Preview', link: '/PR-PREVIEW' },
              { text: '이슈 자동화', link: '/ISSUE-AUTOMATION' },
              { text: 'SSH + Docker 배포', link: '/SSH-DOCKER-DEPLOYMENT-GUIDE' },
              { text: 'Flutter CI/CD', link: '/FLUTTER-CICD-OVERVIEW' },
              { text: 'Projects 동기화', link: '/PROJECTS-SYNC' },
            ],
          },
          { text: '문제 해결', link: '/TROUBLESHOOTING' },
          {
            text: '기여자용',
            items: [
              { text: '브랜치 네이밍 규칙', link: '/BRANCH-CONVENTION' },
              { text: '워크플로우 주석 표준', link: '/WORKFLOW-COMMENT-GUIDELINES' },
            ],
          },
        ],
        sidebar: koSidebar,
        outlineTitle: '이 페이지 목차',
        docFooter: { prev: '이전', next: '다음' },
        darkModeSwitchLabel: '테마',
        sidebarMenuLabel: '메뉴',
        returnToTopLabel: '맨 위로',
        search: {
          provider: 'local',
          options: {
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
    en: {
      label: 'English',
      lang: 'en',
      link: '/en/',
      description: 'GitHub project automation template — from issue to deploy',
      themeConfig: {
        nav: [
          { text: 'Getting started', link: '/en/getting-started' },
          { text: 'CLI', link: '/en/cli' },
          { text: '한국어 문서', link: '/GETTING-STARTED' },
        ],
        sidebar: enSidebar,
      },
    },
  },
})
