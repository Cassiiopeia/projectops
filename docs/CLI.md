# CLI 레퍼런스

`npx projectops`는 기존 프로젝트에 워크플로우, 이슈·PR 템플릿, Agent Skills를 설치하고 업데이트하는 **유일한 공식 경로**입니다. Node.js 20.12 이상만 있으면 별도 설치 없이 실행됩니다. (macOS · Linux · Windows 공통)

## 한눈에 보기

| 하고 싶은 일 | 실행할 것 |
|--------------|-----------|
| 질문에 답하며 설치한다 | `npx projectops` |
| 질문 없이 한 줄로 설치한다 | `npx projectops --mode full --type spring --force` |
| Agent Skills만 설치한다 | `npx projectops --mode skills` |
| 설치 상태를 점검한다 (읽기 전용) | `npx projectops --mode doctor` |

## 대화형 마법사

프로젝트 폴더에서 `npx projectops`만 실행하면 됩니다. 아래는 샘플 Spring 프로젝트에서 **실제로 실행한 화면**입니다.

![npx projectops 대화형 마법사 실행 화면](./images/cli-wizard.gif)

마법사는 이 순서로 묻습니다. 대부분 기본값이 추천값이라 Enter만 눌러도 끝납니다.

| 순서 | 질문 | 무엇을 정하나 |
|------|------|---------------|
| 1 | 무엇을 설치할까요? | 전체 설치, 버전 관리, 워크플로우, 이슈·PR 템플릿, AI 스킬 중 선택 |
| 2 | (자동) 프로젝트 감지 | `build.gradle`, `pubspec.yaml` 같은 마커 파일로 타입(spring, flutter, react 등)과 버전, 브랜치를 알아냅니다 |
| 3 | 프로젝트 성격 | 서버·앱을 배포하는지, 라이브러리를 배포하는지에 따라 이후 질문을 줄입니다 |
| 4 | 실행물 배포 방식 | Docker + SSH 서버 배포(기본), Vercel, 배포 안 함 |
| 5 | PR 댓글 방식 | 변경 요약, 코드 리뷰(CodeRabbit), 둘 다, 사용 안 함 |
| 6 | 개발(릴리스 소스) 브랜치 | 개발을 모아 기본 브랜치로 올리는 브랜치(기본 `develop`). 없으면 만들고 원격 push까지 제안합니다 |
| 7 | Secret 서버 백업 워크플로우 | 포함 여부 |
| 8 | 배포 환경 값 | 서비스 이름, 도메인, JDK 버전 등. "기본값 그대로 전부 설치"를 고를 수 있습니다 |
| 9 | AI 에이전트 스킬 | Claude Code, Cursor, Gemini CLI, Codex CLI, PI에 함께 설치할지 |

선택한 값은 전부 `version.yml`의 `metadata.template.options.*`에 저장되어, 다음 실행(업데이트) 때 다시 묻지 않습니다.

## 한 줄 실행 (비대화형)

CI나 스크립트에서는 `--force`로 모든 확인을 건너뛰고 기본값을 씁니다. 설치가 끝난 뒤 `--mode doctor`로 상태를 확인하는 흐름입니다.

![비대화형 설치와 doctor 진단 실행 화면](./images/cli-oneshot.gif)

```bash
npx projectops --mode full --type spring,react --force
npx projectops --mode workflows --type flutter --paths "flutter=app"
npx projectops --deploy docker-ssh --publish nexus,npm
npx projectops --intent library
```

## 모드

`--mode` 값은 무엇을 설치하느냐를 정합니다. 생략하면 대화형으로 실행됩니다.

| 모드 | 하는 일 |
|------|---------|
| `full` | 워크플로우 + `version.yml` + 이슈·PR 템플릿 + Skills 전체 통합 |
| `version` | `version.yml`만 |
| `workflows` | 워크플로우만 |
| `issues` | 이슈·PR 템플릿만 |
| `skills` | Agent Skills만 |
| `doctor` | 통합 상태와 저장소 설정 진단 (읽기 전용, 아무것도 바꾸지 않음) |

## 옵션

| 옵션 | 설명 |
|------|------|
| `-m, --mode MODE` | 위 모드 중 하나. 기본은 대화형 |
| `-t, --type CSV` | 프로젝트 타입. 예: `spring,react,python`. 지원: `spring` `flutter` `react` `react-native` `react-native-expo` `node` `python` `basic` (`next`는 `react`로 흡수됨 — Next.js는 `react`) |
| `--project-version V` | 통합 대상의 초기 버전(예: `1.0.0`). 생략하면 자동 감지 |
| `--paths "t=p,..."` | 타입별 프로젝트 경로(모노레포). 예: `flutter=app,react=client` |
| `--intent KIND` | 프로젝트 성격: `app` `library` `both` `none` `manual`. 생략하면 `--deploy`/`--publish`에서 추정. `library`/`none`은 배포 질문을, `app`/`none`은 publish 질문을 건너뜁니다 |
| `--deploy TARGET` | 배포 방식 택1: `docker-ssh`(기본) `vercel` `none` |
| `--publish CSV` | publish 대상: `nexus,npm,github-packages` (기본 없음) |
| `--deploy-branch NAME` | 릴리스 PR의 head 브랜치(기본 `develop`). 기본(배포) 브랜치와는 별개입니다 |
| `--secret-backup` / `--no-secret-backup` | Secret 백업 워크플로우 포함 / 제외 |
| `--ai-summary` / `--no-ai-summary` | PR 변경 요약 워크플로우 포함 / 제외 |
| `--force` | 모든 확인을 생략하고 비대화형 기본값 사용 |
| `-v, --version` | projectops 버전 출력 |
| `-h, --help` | 도움말 |

`--nexus`, `--npm-publish`는 더 이상 쓰지 않는 옵션입니다. 각각 `--publish nexus`, `--publish npm`을 쓰세요.

> 모바일 앱 타입(`flutter`, `react-native`, `react-native-expo`)은 스토어 배포 워크플로우가 타입에 이미 포함돼 있어서 배포·publish 질문 자체를 건너뜁니다. 자세한 규칙은 [NPX 마법사 가이드](/NPX-WIZARD)를 보세요.

## 진단 — `doctor`

`--mode doctor`는 파일을 쓰지 않고 상태만 점검합니다.

- 이 폴더에 템플릿이 설치돼 있는지, 설치된 워크플로우가 몇 개인지
- 치환되지 않은 값(`__APPLICATION_YML_DIR__` 같은 자리)이 남아 배포 때 실패할 곳은 없는지
- 설치된 워크플로우가 요구하는 Secret 목록
- 워크플로우 `permissions` 선언 여부

`GITHUB_TOKEN` 환경변수를 주면 저장소 설정(권한, 머지 방식, Secret)까지 점검합니다.

```bash
GITHUB_TOKEN=ghp_... npx projectops --mode doctor
```

## 다시 실행하면 (업데이트)

이미 통합한 프로젝트에서 다시 실행하면 업데이트로 동작합니다.

- **내가 고친 워크플로우는 덮어쓰지 않습니다.** 건너뛰고, 새 템플릿을 `.github/.projectops/incoming/`에 저장한 뒤 비교 명령을 안내합니다.
- **실행 기록이 남습니다.** `.github/.projectops/logs/`에 로그와 이벤트, 마이그레이션 가이드가 쌓이고 이 폴더는 git 추적에서 자동으로 제외됩니다. 문제가 생기면 AI 에이전트에게 "실행 로그 확인해줘"라고 요청하면 됩니다.
- 이름이 바뀐 옛 워크플로우는 자동으로 정리됩니다. 자세한 정책은 [NPX 마법사 가이드](/NPX-WIZARD)의 마이그레이션 절을 보세요.

> 구 `template_integrator.sh` / `.ps1`은 지원이 종료되어 저장소에서 제거됐습니다. `npx projectops`를 쓰세요. ([상세](/TEMPLATE-INTEGRATOR))
