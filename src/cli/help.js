// --help text in each supported language. English is the default (see src/i18n).
//
// 이 화면은 사람보다 AI agent 가 더 많이 읽는다. 그래서 "무엇을 하는가"만이 아니라
// 언제 질문이 나오는지 · 안 주면 무엇이 되는지 · 레포에서 무엇이 바뀌는지를 적는다.
// 값 목록과 플래그별 상세는 src/core/options-schema.js 가 정본이고 `--mode options --json` 이 그대로 출력한다.
// test/cli-docs-sync.test.js 가 args.js 의 모든 플래그가 영·한 두 본문에 있는지 검사한다 — 새 플래그는 둘 다에 적는다.
import { getLang } from "../i18n/index.js";

const HELP_EN = `projectops — installs and updates GitHub automation (versioning, release notes, CI/CD, issue templates, agent skills)

Usage:
  npx projectops [options]

An AI agent or CI job should always run:   npx projectops --mode <mode> --force [flags]
and read the full option table first:      npx projectops --mode options --json

How it decides (read this before scripting)
  - No --mode, or --mode interactive: asks questions in the terminal. Needs a TTY; fails without one.
  - Any other --mode: asks NOTHING. Every value comes from the flags you pass, then the values stored in version.yml,
    then the defaults. Without a TTY, --force is also required.
  - --force: skips every confirmation (including the breaking-changes warning). It never overwrites a file you changed:
    that file is kept and a copy of the new template is saved in .github/.projectops/incoming/.
  - Running the same command twice changes nothing that is already current.

Modes  (-m, --mode MODE)
  full        everything: version.yml, workflows, scripts, issue/PR templates, setup guide (.coderabbit.yaml only with --coderabbit)
  workflows   only .github/workflows plus the scripts, config and util they use. version.yml is not rewritten
  version     only version.yml, the README version section and the version scripts
  issues      only issue and discussion templates
  skills      install or update agent skills for supported IDEs
  doctor      read-only diagnosis of the install and repository settings. Writes nothing. Exit code 0 even when it finds problems
  options     prints every flag and every version.yml key with when-to-use, effect and default (add --json). Writes nothing
  interactive asks questions (default when no --mode is given)

Options
  -t, --type CSV           project types, comma separated, first = primary (e.g. spring,react,python)
                           supported: spring flutter react react-native
                                      react-native-expo node python basic
                           omitted: auto-detected from files in the repo root (nothing found = basic)
                           (next was merged into react: use react for Next.js)
      --project-version V  initial version, only when version.yml does not exist yet (an existing value is always kept)
      --paths "t=p,..."    per-type project folders for monorepos, e.g. flutter=app,react=client. Folders must exist inside the repo
      --intent KIND        app | library | both | none | manual. Decides which deploy/publish questions exist.
                           omitted: inferred from --deploy/--publish
      --label-style STYLE  en = 'status: todo' labels, ko = legacy Korean names. New installs en, existing installs keep ko
      --language LANG      en | ko. Language of issue/PR templates, bot comments and version.yml comments written into the repo
                           (not the CLI screen — that is --lang). New installs en, existing installs keep the stored value
      --deploy TARGET      where the app is deployed, pick one: docker-ssh (SSH + Docker server workflows) | vercel | none
                           omitted: docker-ssh for server stacks; mobile types ignore it
      --publish CSV        library registries: nexus,npm,github-packages. omitted: none
      --deploy-branch NAME the DEVELOPMENT branch (head of the release PR), default develop. It is NOT the branch that deploys;
                           that is the repository default branch. This flag does not create the branch
      --secret-backup / --no-secret-backup   upload GitHub Secrets to your server over SSH (needs SERVER_* secrets). omitted: excluded
      --ai-summary / --no-ai-summary         AI change summary comment on work PRs. Works with no extra setup. omitted: included
      --coderabbit / --no-coderabbit         install .coderabbit.yaml (only --mode full). Needs the CodeRabbit GitHub app. An existing
                                             file is overwritten and saved as .bak. omitted: off, unless version.yml already stores on.
                                             This is PR code review only; release notes do not depend on it
      --projects-sync / --no-projects-sync   keep a GitHub Projects board's Status in step with issue labels. Needs the secret
                                             _GITHUB_PAT_TOKEN and variable PROJECT_URL. omitted: off for new installs, kept if installed
      --remove-legacy      rename retired old-generation workflows to .bak so they stop running next to their replacements.
                           omitted: they stay and are only listed (an old deploy workflow may be your only live deployment)
      --nexus / --npm-publish  (deprecated: use --publish nexus / --publish npm)
      --force, -y, --yes   skip every confirmation, use defaults for anything not given
      --json               with --mode options: JSON instead of text
      --lang en|ko         language of the CLI screen (default: system language, en in CI and with --force)
  -v, --version            print the projectops version
  -h, --help               show this help

Where results go
  stderr          a completion summary: files kept, retired workflows still installed, workflows not installed and why,
                  placeholders still to fill (__NAME__), secrets to register, next steps
  .github/.projectops/logs/        why each decision was made (.log for people, .jsonl for programs)
  .github/.projectops/incoming/    new template copies of files that were kept or not installed
  exit code       0 = completed, 1 = invalid arguments or a failed run (the message says which)

Examples
  npx projectops --mode options --json                         # every option, value, default and effect (read-only)
  npx projectops --mode doctor                                 # diagnose this install (read-only)
  npx projectops --mode full --force                           # install or update everything, stack auto-detected
  npx projectops --mode full --force --type spring,react       # explicit stacks
  npx projectops --mode workflows --force                      # refresh only workflows, scripts and config
  npx projectops --mode workflows --force --remove-legacy      # also retire old-generation workflows
  npx projectops --mode full --force --coderabbit              # also install the CodeRabbit review config
  npx projectops --mode workflows --type flutter --paths "flutter=app" --force
  GITHUB_TOKEN=ghp_... npx projectops --mode doctor            # include repository settings
`;

const HELP_KO = `projectops — GitHub 자동화(버전 관리, 릴리스 노트, CI/CD, 이슈 템플릿, agent 스킬)를 설치·업데이트하는 CLI

사용법:
  npx projectops [옵션]

AI agent 나 CI 는 항상 이렇게 실행한다:      npx projectops --mode <모드> --force [플래그]
그리고 먼저 전체 옵션 표를 읽는다:           npx projectops --mode options --json

어떻게 정해지는가 (스크립트를 짜기 전에 읽는다)
  - --mode 가 없거나 --mode interactive: 터미널에서 질문한다. TTY 가 필요하고 없으면 실패한다.
  - 그 밖의 --mode: **아무것도 묻지 않는다.** 모든 값은 넘긴 플래그 → version.yml 에 저장된 값 → 기본값 순으로 정해진다.
    TTY 가 없으면 --force 도 필요하다.
  - --force: 모든 확인(호환성 변경 경고 포함)을 건너뛴다. 직접 고친 파일은 **덮어쓰지 않는다** —
    그 파일은 그대로 두고 새 템플릿 사본을 .github/.projectops/incoming/ 에 남긴다.
  - 같은 명령을 두 번 돌려도 이미 최신인 것은 바꾸지 않는다.

모드  (-m, --mode MODE)
  full        전부: version.yml, 워크플로우, 스크립트, 이슈/PR 템플릿, 설정 안내서 (.coderabbit.yaml 은 --coderabbit 일 때만)
  workflows   .github/workflows 와 그것이 쓰는 스크립트·config·util 만. version.yml 은 다시 쓰지 않는다
  version     version.yml, README 버전 섹션, 버전 스크립트만
  issues      이슈·디스커션 템플릿만
  skills      지원 IDE 의 agent 스킬 설치·갱신
  doctor      통합 상태와 저장소 설정을 읽기 전용으로 진단. 아무것도 쓰지 않는다. 문제를 찾아도 종료 코드는 0
  options     모든 플래그와 version.yml 키를 언제 쓰는지·효과·기본값과 함께 출력 (--json 추가). 아무것도 쓰지 않는다
  interactive 질문하며 진행 (--mode 를 안 주면 기본)

옵션
  -t, --type CSV           프로젝트 타입 csv, 첫 항목이 primary (예: spring,react,python)
                           지원: spring flutter react react-native
                                 react-native-expo node python basic
                           생략: 레포 루트의 파일로 자동 감지 (못 찾으면 basic)
                           (next는 react로 흡수됨 — Next.js 프로젝트는 react 사용)
      --project-version V  초기 버전. version.yml 이 아직 없을 때만 쓰인다 (기존 값은 항상 유지)
      --paths "t=p,..."    타입별 프로젝트 폴더(모노레포). 예: flutter=app,react=client. 폴더는 레포 안에 있어야 한다
      --intent KIND        app | library | both | none | manual. 배포·publish 질문을 어떻게 할지 정한다.
                           생략: --deploy/--publish 에서 추정
      --label-style STYLE  en = 'status: todo' 라벨, ko = 기존 한글 이름. 신규 en, 기존 설치는 ko 유지
      --language LANG      en | ko. 레포에 쓰이는 이슈/PR 템플릿·봇 댓글·version.yml 주석의 언어
                           (CLI 화면 언어는 --lang 이다). 신규 en, 기존 설치는 저장값 유지
      --deploy TARGET      앱을 어디에 배포하나, 택1: docker-ssh(SSH + Docker 서버 워크플로우) | vercel | none
                           생략: 서버 스택은 docker-ssh, 모바일 타입은 무시
      --publish CSV        라이브러리 레지스트리: nexus,npm,github-packages. 생략: 없음
      --deploy-branch NAME **개발** 브랜치(릴리스 PR 의 head), 기본 develop. 배포가 도는 브랜치가 아니다 —
                           그것은 레포 기본 브랜치다. 이 플래그는 브랜치를 만들지 않는다
      --secret-backup / --no-secret-backup   GitHub Secret 을 SSH 로 서버에 올린다 (SERVER_* secret 필요). 생략: 제외
      --ai-summary / --no-ai-summary         작업 PR 에 AI 변경 요약 댓글. 추가 설정 없이 동작. 생략: 포함
      --coderabbit / --no-coderabbit         .coderabbit.yaml 설치 (--mode full 에서만). CodeRabbit GitHub 앱이 필요하다.
                                             이미 있으면 덮어쓰고 .bak 으로 백업. 생략: 꺼짐 (version.yml 에 켜짐이 저장돼 있으면 유지).
                                             PR 코드 리뷰 전용이며 릴리스 노트와 무관하다
      --projects-sync / --no-projects-sync   GitHub Projects 보드의 Status 를 이슈 라벨과 맞춘다. secret _GITHUB_PAT_TOKEN 과
                                             변수 PROJECT_URL 이 필요. 생략: 신규는 제외, 이미 설치돼 있으면 유지
      --remove-legacy      은퇴한 구세대 워크플로우를 .bak 으로 바꿔 신형과 함께 돌지 않게 한다.
                           생략: 그대로 두고 목록만 안내한다 (옛 배포 워크플로우가 유일한 현역 배포일 수 있다)
      --nexus / --npm-publish  (deprecated — --publish nexus / --publish npm 사용)
      --force, -y, --yes   모든 확인을 건너뛰고 주지 않은 값은 기본값 사용
      --json               --mode options 와 함께: JSON 출력
      --lang en|ko         CLI 화면 언어 (기본: 시스템 언어, CI/--force 는 en)
  -v, --version            projectops 버전 출력
  -h, --help               도움말

결과는 어디에 남나
  stderr          완료 요약: 유지한 파일, 아직 설치된 은퇴 워크플로우, 설치하지 않은 워크플로우와 이유,
                  채워야 할 자리표시자(__NAME__), 등록할 secret, 다음 할 일
  .github/.projectops/logs/        각 결정의 이유 (.log 사람용, .jsonl 프로그램용)
  .github/.projectops/incoming/    유지했거나 설치하지 않은 파일의 새 템플릿 사본
  종료 코드       0 = 완료, 1 = 잘못된 인자 또는 실패한 실행 (메시지가 어느 쪽인지 알려 준다)

예시
  npx projectops --mode options --json                         # 모든 옵션·값·기본값·효과 (읽기 전용)
  npx projectops --mode doctor                                 # 이 설치를 진단 (읽기 전용)
  npx projectops --mode full --force                           # 전부 설치·업데이트, 스택 자동 감지
  npx projectops --mode full --force --type spring,react       # 스택을 명시
  npx projectops --mode workflows --force                      # 워크플로우·스크립트·config 만 갱신
  npx projectops --mode workflows --force --remove-legacy      # 구세대 워크플로우도 정리
  npx projectops --mode full --force --coderabbit              # CodeRabbit 리뷰 설정도 설치
  npx projectops --mode workflows --type flutter --paths "flutter=app" --force
  GITHUB_TOKEN=ghp_... npx projectops --mode doctor            # 저장소 설정까지 진단
`;

export function helpText(lang = getLang()) {
  return lang === "ko" ? HELP_KO : HELP_EN;
}
