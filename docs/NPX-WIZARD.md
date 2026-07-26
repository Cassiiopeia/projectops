# NPX 마법사 가이드 (npx projectops)

기존 프로젝트에 템플릿을 통합·업데이트하는 유일한 공식 경로입니다. 구 `template_integrator.sh`/`.ps1`은 v4.3.0에서 지원 종료(EOF)되었습니다 ([상세](TEMPLATE-INTEGRATOR.md)).

- **요구사항**: Node.js 20.12 이상
- macOS / Linux / Windows 공통 단일 경로

---

## 기본 사용법

```bash
# 대화형 마법사
npx projectops

# 비대화형 (CI 등)
npx projectops --mode full --type spring,react --force

# Agent Skills만 설치
npx projectops --mode skills

# 전체 옵션
npx projectops --help
```

| 모드 | 기능 |
|------|------|
| `full` | 워크플로우 + version.yml + 이슈 템플릿 + Skills 전체 통합 |
| `version` | version.yml만 |
| `workflows` | 워크플로우만 |
| `issues` | 이슈/PR 템플릿만 |
| `skills` | Agent Skills만 |

선택 값은 전부 `version.yml`의 `metadata.template.options.*`에 저장되어, 다음 업데이트 시 재질문 없이 재사용됩니다.

---

## 프로젝트 성격(intent) 우선 질문 (#485)

두 개의 배포 축을 낱개로 물으면 "이게 나한테 해당되나?"를 판단하기 어렵습니다. 그래서 마법사는 타입 확정 직후 **프로젝트 성격을 먼저 한 번** 묻고, 그 답이 아래 두 축을 유도합니다.

| 선택 | 뜻 | 배포(deploy) 질문 | publish 질문 |
|------|-----|------------------|-------------|
| `app` | 실행물을 서비스한다 | 물음 | **스킵** (`publish=[]`) |
| `library` | 라이브러리/패키지를 배포한다 | **스킵** (`deploy=none`) | 물음 |
| `both` | 둘 다 | 물음 | 물음 |
| `none` | 둘 다 아니다 | **스킵** (`none`) | **스킵** (`[]`) |
| `manual` | 직접 고르겠다 | 물음 | 물음 |

- 저장 위치: `version.yml`의 `metadata.template.options.intent`
- 비대화형: `--intent app|library|both|none|manual`
- 구 version.yml처럼 `intent` 키가 없으면 저장된 `deploy`/`publish` 값에서 **자동 역추론**합니다 (하위호환). `--intent`를 지정하고 해당 축 플래그를 생략하면 intent가 그 축을 유도합니다.
- 수정 메뉴에는 "프로젝트 성격" 항목과 개별 축 항목이 함께 있습니다. 성격을 바꾸면 축이 재유도되고, 개별 축 항목은 그 축만 세밀 조정합니다.

---

## 배포/publish 2축 (#439)

배포는 서로 독립인 **두 개의 축**으로 표현됩니다. 위 intent 질문의 답에 따라 물어볼 축이 결정됩니다.

| 축 | 의미 | 다중성 | 값 | version.yml 키 |
|----|------|--------|-----|---------------|
| **deploy** | 실행물(서버/앱)을 어디에 올리나 | **택1** | `docker-ssh`(기본) · `vercel` · `none` | `options.deploy` |
| **publish** | 라이브러리/패키지를 어느 레지스트리에 내나 | **0..n 공존** | `nexus` · `npm` · `github-packages` | `options.publish` 배열 |

```bash
# 비대화형 지정
npx projectops --deploy docker-ssh --publish nexus,npm
```

### 축별로 포함되는 워크플로우

| 선택 | 포함되는 워크플로우 | 원본 위치 |
|------|-------------------|----------|
| `--deploy docker-ssh` | 각 타입의 서버 배포 세트 (Spring: SIMPLE/NONSTOP-TRAEFIK/NONSTOP-NGINX/PR-PREVIEW, Python: SIMPLE-CICD/PR-PREVIEW) | `project-types/<type>/server-deploy/` |
| `--deploy vercel` | `PROJECT-COMMON-VERCEL-DEPLOY` (VERCEL_TOKEN·VERCEL_ORG_ID·VERCEL_PROJECT_ID secret 필요) | `project-types/common/deploy/vercel/` |
| `--deploy none` | 서버 배포 워크플로우 제외 | - |
| `--publish nexus` | `PROJECT-SPRING-NEXUS-CI` / `-NEXUS-PUBLISH` | `project-types/spring/publish/nexus/` |
| `--publish npm` | `PROJECT-NODE-NPM-PUBLISH` (NPM_TOKEN secret) | `project-types/node/publish/npm/` |
| `--publish github-packages` | `PROJECT-SPRING-GITHUB-PACKAGES-PUBLISH` | `project-types/spring/publish/github-packages/` |
| `--secret-backup` | `PROJECT-COMMON-SECRET-FILE-UPLOAD` (opt-in) | `project-types/common/secret-backup/` |

### 타입별 축 적용성 (#498)

두 축은 **타입에 따라 적용 자체가 안 될 수 있습니다.** 선택한 타입 집합의 합집합만 선택지로 노출됩니다.

| 타입 | deploy | publish |
|------|--------|---------|
| `spring` · `react` · `node` · `python` | `docker-ssh` · `vercel` | `nexus` · `npm` · `github-packages` |
| `flutter` · `react-native` · `react-native-expo` | 없음 | 없음 |
| `basic` | 없음 | 없음 |

- **두 축이 모두 빈 타입만 골랐다면 intent 질문까지 통째로 스킵**하고 `deploy=none`·`publish=[]`로 조용히 확정합니다. 모바일 앱 타입은 스토어 배포(Play Store/TestFlight/Firebase) 워크플로우가 타입 자체에 항상 포함되므로 서버 deploy 축과 무관하고, 레지스트리 publish 개념도 없습니다.
- 저장값이나 CLI 값이 적용 불가한 타입이면 **경고 없이 조용히 정리**됩니다 (구버전에서 flutter 단독인데 `deploy: docker-ssh`가 저장된 레포도 업데이트 시 `none`으로 정리됨 — 복사 결과는 어차피 동일).
- 수정 메뉴도 적용 불가한 축 항목("프로젝트 성격"·"배포 방식"·"publish 타겟")을 숨깁니다. 타입을 바꾸면 다음 진입부터 다시 노출됩니다.

### 알아둘 규칙
- **구 플래그 deprecated**: `--nexus`/`--npm-publish`는 각각 `--publish nexus`/`--publish npm`으로 해석되며 경고가 출력됩니다 (`--nexus`는 추가로 `--deploy none` 함의). 1 minor 유지 후 제거 예정.
- version.yml의 구 키(`nexus`/`npm_publish`)는 업데이트 시 신 축으로 자동 변환·기록됩니다.

---

## 모노레포 경로 (`project_paths`)

타입별 프로젝트가 서브폴더에 있으면 경로를 지정합니다. 상세는 [버전 관리](VERSION-CONTROL.md) 참조.

```bash
npx projectops --paths "flutter=app,react=client"
```

---

## 레거시 워크플로우 자동 마이그레이션 (#470)

`full`/`workflows` 모드로 통합·업데이트하면 마법사가 대상 레포의 **구세대 템플릿 워크플로우 잔재를 자동 감지**합니다. 구 워크플로우가 신 워크플로우와 공존하면 릴리스 PR 이중 처리·CI 중복 실행 같은 실해가 발생하기 때문입니다.

### 2티어 안전 정책

| 티어 | 판정 기준 | 조치 |
|------|----------|------|
| **safe** | 순수 리네임·대체 (공존 시 중복 실행 실해) | 대화형: 확인 1회 후 `.bak` 무해화 / 비대화형(`--force`): 자동 무해화 |
| **confirm** | 배포 파이프라인일 수 있음 (그 레포의 유일한 현역 배포 가능성) | **자동 조치 없음** — 안내만 출력. `--force`에서도 건드리지 않음 |

### 보장 사항

- **커스텀 워크플로우 불가침**: 레지스트리는 정확한 파일명 매칭만 사용합니다 (글롭 금지). 사용자가 직접 만든 워크플로우는 절대 건드리지 않습니다.
- **복원 가능**: safe 조치는 삭제가 아니라 `.bak` 확장자 무해화입니다. 되돌리려면 `.bak`을 제거하면 됩니다.
  ```bash
  mv .github/workflows/PROJECT-OLD-NAME.yaml.bak .github/workflows/PROJECT-OLD-NAME.yaml
  ```
- **멱등**: 같은 명령을 다시 실행해도 이미 처리된 항목은 재조치되지 않습니다.

### 감지 대상 (v4.3.x 스냅샷)

전체 목록의 SSOT는 `src/core/migrations/registry.js`입니다 (총 55항목). 요약:

| 분류 | 수 | 내용 |
|------|-----|------|
| **workflow / safe** | 18 | 1세대 리네임(`PROJECT-VERSION-CONTROL` 등), 구명칭 릴리스 워크플로우(`PROJECT-AUTO-CHANGELOG-CONTROL`·`PROJECT-COMMON-AUTO-CHANGELOG-CONTROL` → `PROJECT-COMMON-RELEASE-CHANGELOG`), 리브랜딩 리네임(`PROJECT-FLUTTER-SUH-LAB-APP-BUILD-TRIGGER` → `PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER`), next 타입 폐지(`PROJECT-NEXT-CI`/`-CICD` → `PROJECT-REACT-*`), 구 확장자(.yml) CI 등 |
| **workflow / confirm** | 22 | SYNOLOGY 세대 배포 7종, 1세대 Spring/Python/Android/iOS 배포, AUTO-FILE-UPLOAD 계열, 구 Nexus publish 계열 등 — 전부 "현역 배포일 수 있음"이라 안내만 |
| **util-file / safe** | 12 | `.github/util/` 모듈 안의 폐기 파일 (Flutter 마법사 스크립트 Python 단일화 등). util 복사는 overlay라 구 파일을 지우지 않으므로 registry가 유일한 정리 경로 |
| **root-file / safe** | 2 | `SUH-DEVOPS-TEMPLATE-SETUP-GUIDE.md`·`SETUP-GUIDE.md` → `PROJECTOPS-SETUP-GUIDE.md` (구 설치 가이드 잔재) |
| **legacy-dir / ask** | 1 | `docs/suh-template/` → `docs/projectops/` (스킬 산출물 폴더 구명칭 — 사용자 문서 보존 이동) |

### 고아 워크플로우 정리 (#487) — 레거시 마이그레이션과 다릅니다

레지스트리는 **리네임·폐기 전용**입니다. **타입 선택을 해제해서 남는 워크플로우**는 레지스트리가 아니라 `src/core/orphan-workflows.js`가 **템플릿 인벤토리 대조**로 동적 감지합니다.

- 예: `--type spring,flutter`로 통합했다가 `--type spring`으로 바꾸면, 남아 있는 `PROJECT-FLUTTER-*`가 고아로 감지됩니다.
- 판정은 **정확한 파일명 일치**만 사용합니다 (글롭·prefix 매칭 금지 → 사용자 커스텀 워크플로우 불가침).
- 대화형은 확인 후 `.bak` 무해화, **비대화형은 안내만 출력**하고 건드리지 않습니다.
- `common/`은 타입이 아니므로 고아 판정 대상에서 제외됩니다.

### 마이그레이션 실행 기록 (#493·#494)

`full`/`workflows` 마법사가 끝나면 **대상 레포**의 `docs/projectops/migration/`에 실행 기록 3계층이 남습니다. 무엇이 왜 바뀌었는지 사후 추적할 수 있습니다.

| 계층 | 파일 | 내용 |
|------|------|------|
| 1 | `PROJECTOPS-MIGRATION-GUIDE.md` | 고정 헤더(AI 해석 가이드라인) + 실행 엔트리 append-only. 동적 체크리스트, 통과한 breaking change 전문, yaml 메타 |
| 2 | `{stamp}_v{from}_to_v{to}.jsonl` | 파일별 결정·env 치환 전후값 이벤트 (파일명 grep으로 인과 추적) |
| 3 | `{stamp}_..._.log` | 터미널 출력 원문 미러 |

- 가이드의 워크플로우 목록·env 값은 2계층 이벤트에서 **파생**됩니다 (단일 소스).
- 민감값(PAT·token·secret·password 키)은 이벤트 기록 시 **자동 제거**됩니다.

### 기여자 가이드라인 — 워크플로우를 리네임/삭제할 때

템플릿에서 워크플로우나 루트 파일, `.github/util/` 안의 파일을 리네임·폐기하면 **반드시 구 이름을 `src/core/migrations/registry.js`에 한 줄 추가**합니다. 이것이 기존 통합 레포의 구 파일을 자동 정리하는 유일한 경로입니다 (레거시 마이그레이션은 전부 이 레지스트리 한 곳에서 관리).

1. 항목 스키마: `id`(kebab-case) · `category`(`"workflow"` | `"root-file"` | `"util-file"` | `"legacy-dir"`) · `tier` · `file`(정확한 파일명·경로, 글롭 금지) · `replacedBy`(없으면 null) · `since` · `reason` · `contentMarker`(선택 — 파일명이 범용적일 때 오탐 방지) · `settingsExtractor`(선택 — 무해화 직전 사용자 커스텀 설정을 version.yml로 이관)
2. **tier 판단 기준**: 실해로 고른다 —
   - `safe`: 신형이 같은 기능을 완전 대체(순수 리네임). 공존 시 이중 트리거가 실해
   - `confirm`: 배포 파이프라인일 수 있음. 오살하면 그 레포의 배포가 끊긴다 → 자동 조치 금지
3. `test/migrations.test.js`가 레지스트리 항목이 **현행 배포 세트와 겹치지 않는지**(살아있는 워크플로우 오살 방지) 자동 검증한다. 등록 후 `npm test`로 확인.

---

## 관련 문서

- [Template Integrator EOF 안내](TEMPLATE-INTEGRATOR.md) — 구 스크립트 → npx 플래그 대응표
- [버전 관리](VERSION-CONTROL.md) — version.yml·모노레포 project_paths
- [체인지로그 자동화](CHANGELOG-AUTOMATION.md#릴리스-노트-provider-사다리) — 릴리스 노트 provider 사다리
