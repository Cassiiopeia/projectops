// --help text in each supported language. English is the default (see src/i18n).
import { getLang } from "../i18n/index.js";

const HELP_EN = `projectops — GitHub project automation template installer

Usage:
  npx projectops [options]

Options:
  -m, --mode MODE          Mode (full | version | workflows | issues | skills | doctor)
                           doctor: diagnose the installation and repository settings (read-only)
                           default: interactive
  -t, --type CSV           Project types, comma separated (e.g. spring,react,python)
                           supported: spring flutter react react-native
                                      react-native-expo node python basic
                           (next was merged into react: use react for Next.js)
      --project-version V  Initial version of the target project (e.g. 1.0.0). Detected if omitted
      --paths "t=p,..."    Per-type project paths for monorepos. e.g. flutter=app,react=client
      --intent KIND        Project kind: app | library | both | none | manual
                           (inferred from --deploy/--publish if omitted)
      --label-style STYLE  Status label names: en (status: todo) | ko (legacy 작업전)
      --language LANG      Language of the issue and PR templates written into your repo: en | ko
      --deploy TARGET      Deployment, pick one: docker-ssh (default) | vercel | none
      --publish CSV        Publish targets: nexus,npm,github-packages (default: none)
      --deploy-branch NAME Head branch of the release PR (default: develop). Not the default branch
      --secret-backup / --no-secret-backup   Include / exclude the secret backup workflow
      --ai-summary / --no-ai-summary         Include / exclude the PR summary workflow
      --projects-sync / --no-projects-sync   Include / exclude the GitHub Projects status sync workflow (default: off for new installs)
      --nexus / --npm-publish  (deprecated: use --publish nexus / --publish npm)
      --force, -y, --yes   Skip every confirmation and use non-interactive defaults
      --lang en|ko         Display language (default: system language, pinned to en in CI and with --force)
  -v, --version            Print the projectops version
  -h, --help               Show this help

Examples:
  npx projectops --mode full --force --type spring,react
  npx projectops --mode workflows --type flutter --paths "flutter=app"
  npx projectops --mode doctor                       # diagnose settings
  GITHUB_TOKEN=ghp_... npx projectops --mode doctor  # include repository settings
`;

const HELP_KO = `projectops — GitHub 프로젝트 자동화 템플릿 통합 CLI

사용법:
  npx projectops [옵션]

옵션:
  -m, --mode MODE          통합 모드 (full | version | workflows | issues | skills | doctor)
                           doctor: 통합 상태·저장소 설정 진단 (읽기 전용)
                           기본: interactive (대화형)
  -t, --type CSV           프로젝트 타입 csv (예: spring,react,python)
                           지원: spring flutter react react-native
                                 react-native-expo node python basic
                           (next는 react로 흡수됨 — Next.js 프로젝트는 react 사용)
      --project-version V  통합 대상의 초기 버전 (예: 1.0.0). 미지정 시 자동 감지
      --paths "t=p,..."    타입별 프로젝트 경로 (모노레포). 예: flutter=app,react=client
      --intent KIND        프로젝트 성격(#485): app | library | both | none | manual
                           (미지정 시 --deploy/--publish에서 역추론. library/none→deploy 제외, app/none→publish 제외)
      --label-style STYLE  상태 라벨 표기: en (status: todo) | ko (기존 작업전)
      --language LANG      레포에 쓰이는 이슈/PR 템플릿 언어: en | ko
      --deploy TARGET      배포 방식 택1: docker-ssh(기본) | vercel | none
      --publish CSV        publish 타겟 csv: nexus,npm,github-packages (기본: 없음)
      --deploy-branch NAME 릴리스 PR head 브랜치 (#456, 기본: develop). default_branch와 별개
      --secret-backup / --no-secret-backup   Secret 백업 워크플로우 포함/제외
      --ai-summary / --no-ai-summary         PR 변경 요약 워크플로우 포함/제외
      --projects-sync / --no-projects-sync   GitHub Projects 상태 동기화 워크플로우 포함/제외 (신규 설치 기본 제외)
      --nexus / --npm-publish  (deprecated — --publish nexus / --publish npm 사용)
      --force, -y, --yes   모든 확인 생략, 비대화형 기본값 사용
      --lang en|ko         화면 언어 (기본: 시스템 언어, CI/--force 는 en 고정)
  -v, --version            projectops 버전 출력
  -h, --help               이 도움말 표시

예시:
  npx projectops --mode full --force --type spring,react
  npx projectops --mode workflows --type flutter --paths "flutter=app"
  npx projectops --mode doctor                       # 설정 진단
  GITHUB_TOKEN=ghp_... npx projectops --mode doctor  # 저장소 설정까지 진단
`;

export function helpText(lang = getLang()) {
  return lang === "ko" ? HELP_KO : HELP_EN;
}
