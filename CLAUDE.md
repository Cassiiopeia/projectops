# Projectops

완전 자동화된 GitHub 프로젝트 관리 템플릿

---

## ⚠️ 작업 브랜치 규칙 (agent 필독)

**이 프로젝트는 `develop` 브랜치에서 직접 작업하는 것을 기본값으로 한다. `main`은 프로덕션(default) — 직접 커밋·push 금지.**

- 별도 지시가 없으면 feature 브랜치를 만들지 말고 `develop`에서 작업·커밋·푸시한다.
- `develop` push 전에는 **항상 `git pull --rebase origin develop`** 으로 먼저 동기화한다 (릴리스 시 버전 확정 커밋이 develop에 추가되므로 로컬이 뒤처지기 쉽다).
- 릴리스(배포)는 develop→main PR로만 진행한다 (`/pro-changelog-deploy`). main 직접 push는 안전망(VERSION-CONTROL 가드)이 버전만 보전할 뿐 지원 경로가 아니다.
- `git push`는 **사용자가 명시적으로 요청한 경우에만** 실행한다.
- 사용자가 명시적으로 브랜치 작업을 요청한 경우에만 feature 브랜치를 사용한다.
- 커밋은 **`/pro-commit`을 사용한다.** 브랜치명에서 이슈 번호를 뽑아 컨벤션에 맞는 메시지를 만들고, 스테이징 대상도 함께 확인시켜 준다.

### 여러 에이전트가 동시에 작업한다 (agent 필독)

**여러 Claude Code 세션이 같은 `develop`에서 동시에 작업한다.** 각 세션은 서로의 존재나
작업 내용을 알지 못한다. 내가 만들지 않은 변경이 언제든 작업트리에 나타날 수 있다는
전제로 움직인다.

| 상황 | 대응 |
|---|---|
| 작업 시작 전 | `git pull --rebase origin develop`로 최신 상태를 먼저 받는다 |
| 커밋 전 | `git status`로 **내가 만들지 않은 변경**이 섞였는지 확인한다 |
| 스테이징 | `git add -A`보다 **내가 건드린 경로만** 명시해 담는다 |
| 브랜치가 바뀌어 있음 | 다른 세션이 옮긴 것일 수 있다. 임의로 되돌리지 말고 현재 브랜치를 존중한다 |
| 푸시 거부(non-fast-forward) | 강제 푸시하지 않는다. rebase로 통합한 뒤 다시 푸시한다 |

**금지**

- `git push --force` / `--force-with-lease` — 다른 세션의 커밋이 사라진다
- `git checkout .` · `git reset --hard` — 다른 세션의 미커밋 작업을 날린다
- 내 작업과 무관한 파일을 함께 커밋하는 것 — 원인 추적이 불가능해진다

의도를 모르는 변경이 작업트리에 있으면 **건드리지 말고 그대로 둔다.** 내 변경만 커밋하고
나머지는 그 세션이 처리하도록 남겨두는 것이 안전하다.

### 브랜치 3개념 (agent·마법사 필독 — #482)

혼동 주의: 프로젝트에는 브랜치가 **3개념**이 있고, version.yml 필드명이 직관과 어긋난다.

| 개념 | 뜻 | version.yml 필드 | 표준값 |
|------|-----|-----------------|--------|
| **기본(배포) 브랜치** | 레포 default·프로덕션. push되면 배포가 도는 곳 | `default_branch` | `main` |
| **개발(릴리스 소스) 브랜치** | 개발을 모아 기본 브랜치로 올리는 릴리스 PR의 head | `deploy_branch` ⚠️ | `develop` |
| 이슈 브랜치 | 작업 단위 (`YYYYMMDD_#번호_제목`) | — | — |

> ⚠️ **`deploy_branch`는 이름과 달리 "개발 브랜치"다** (릴리스 PR head). "배포 브랜치"로 읽으면 안 된다 — 배포가 도는 곳은 `default_branch`. 사용자 노출 문구에서 이 필드를 "배포 브랜치"라 부르지 말고 "개발(릴리스 소스) 브랜치"로 칭한다. (필드 개명은 파급이 커 후속 과제 — 라벨·문구만 먼저 정합화됨.)

---

## ⚠️ 이슈 처리 규칙 (agent 필독)

**이 프로젝트는 이슈가 완료되어도 이슈를 닫지(close) 않는다. 대신 라벨을 수정한다.**

- 작업이 끝나면 이슈 상태 라벨을 `작업전`/`작업중` → **`작업완료`**(또는 상황에 맞는 라벨)로 변경한다.
- **이슈를 `close` 처리하지 않는다** — 라벨(`PROJECT-COMMON-PROJECTS-SYNC-MANAGER`가 Projects 보드 상태와 동기화)이 완료를 나타내며, close는 이 흐름을 깨뜨린다.
- 사용자가 **명시적으로 "이슈 닫아줘"라고 요청한 경우에만** close한다. 구현·보고서 작성이 끝났다는 이유만으로 임의로 닫지 않는다.
- 라벨 변경은 `/pro-github`(또는 `github_cli.py set-labels`/`add-labels`/`remove-label`)로 처리한다.

---

## 프로젝트 개요

### 지원 프로젝트 타입
| 타입 | 설명 | 버전 동기화 파일 |
|------|------|-----------------|
| `spring` | Spring Boot | `build.gradle` |
| `flutter` | Flutter | `pubspec.yaml` |
| `react` | React.js / Next.js | `package.json` |
| `node` | Node.js | `package.json` |
| `python` | FastAPI/Django | `pyproject.toml` |
| `react-native` | React Native CLI | `Info.plist` + `build.gradle` |
| `react-native-expo` | Expo | `app.json` |
| `basic` | 범용 | `version.yml`만 |

> **멀티타입**: 단일 레포에 여러 타입 공존 시 `--type spring,react,python` csv로 지정. `version.yml`의 `project_types` 배열에 저장되며, 첫 항목이 primary 타입이다 (단수 `project_type` 키는 v4.1.0에서 제거됨 — SSOT).
>
> **모노레포 경로**: 타입별 프로젝트가 서브폴더에 있으면(예: `app/`, `client/`, `ai/`) `version.yml`의 `project_paths` 맵(타입 → 레포 루트 기준 상대경로)으로 지정한다. integrator가 통합 시 마커 파일(`pubspec.yaml`·`package.json`·`pyproject.toml`·`build.gradle` 등)을 자동 감지·확인하며, 키가 없으면 루트 기준(기존 동작 100% 유지). 비대화형은 `--paths "flutter=app,react=client"`(`.ps1`은 `-Paths`). `version_manager.sh`가 이 경로를 따라 서브폴더 버전 파일을 동기화하므로, `PROJECT-COMMON-VERSION-CONTROL` 워크플로우는 무수정으로 모노레포를 커버한다.

---

## 폴더 구조

```
projectops/
├── .github/
│   ├── workflows/
│   │   ├── PROJECT-TEMPLATE-INITIALIZER.yaml
│   │   ├── PROJECT-COMMON-*.yaml
│   │   └── project-types/
│   │       ├── common/          # 공통 원본 (+ secret-backup/ opt-in, deploy/vercel/ 배포타겟)
│   │       ├── flutter/         # Flutter 전용 (스토어 배포 워크플로우 루트 포함)
│   │       ├── spring/          # Spring 전용 (server-deploy/ + publish/{nexus,github-packages}/)
│   │       ├── python/          # Python 전용 (CI 루트 + server-deploy/)
│   │       ├── react/           # React/Next.js 공용 (next 타입은 v4.1.0에서 흡수됨)
│   │       └── node/            # Node 전용 (publish/npm/)
│   ├── scripts/
│   │   ├── version_manager.sh    # + version_manager.py (실 로직, #448)
│   │   ├── changelog_manager.py
│   │   ├── truncate_release_notes.sh  # + .py (실 로직, #448)
│   │   └── template_initializer.sh
│   ├── util/
│   │   ├── flutter/
│   │   │   ├── playstore-wizard/
│   │   │   ├── testflight-wizard/
│   │   │   └── firebase-wizard/
│   │   └── common/
│   │       ├── projects-sync-wizard/
│   │       ├── github-projects-sync-worker/
│   │       └── github-secrets-converter/
│   ├── ISSUE_TEMPLATE/
│   └── PULL_REQUEST_TEMPLATE.md
├── .claude-plugin/              # 플러그인 매니페스트
├── skills/                      # 플러그인 Skills (마켓플레이스 전용)
├── scripts/                     # 플러그인 Scripts (마켓플레이스 전용)
├── .cursor/skills/
├── docs/                        # 상세 문서
├── version.yml
├── CHANGELOG.md / CHANGELOG.json
├── template_integrator.sh   # EOF shim (#458 — npx 안내만)
└── template_integrator.ps1  # EOF shim (#458 — npx 안내만)
```

---

## 네이밍 컨벤션

### 워크플로우 파일
```
PROJECT-[TYPE]-[FEATURE]-[DETAIL].yaml

TYPE: TEMPLATE | COMMON | FLUTTER | SPRING | REACT
```

### 스크립트 파일
```
snake_case.sh / snake_case.py
```

---

## 핵심 워크플로우

### 공통 워크플로우

| 파일명 | 트리거 | 기능 |
|--------|--------|------|
| `PROJECT-TEMPLATE-INITIALIZER` | 저장소 생성 | 템플릿 초기화 (일회성) |
| `PROJECT-TEMPLATE-PLUGIN-VERSION-SYNC` | main 푸시 | 플러그인 매니페스트 버전 동기화 (**이 레포 전용**) |
| `PROJECT-TEMPLATE-CI` | develop 푸시/PR | npx CLI 테스트 (**이 레포 전용**) |
| `PROJECT-TEMPLATE-NPM-PUBLISH` | main 푸시 | `projectops` npm 패키지 배포 (**이 레포 전용**) |
| `PROJECT-COMMON-VERSION-CONTROL` | main 직접 푸시(안전망) | 릴리스 머지 외 push 시 patch 증가 |
| `PROJECT-COMMON-RELEASE-CHANGELOG` | main PR (develop→main) | 버전 확정 + AI 체인지로그 + automerge |
| `PROJECT-COMMON-README-VERSION-UPDATE` | main 푸시 | README 버전 동기화 |
| `PROJECT-COMMON-SUH-ISSUE-HELPER` | 이슈 생성 | 브랜치명/커밋 제안 (내부 py — `issue_helper.py`, #478 내재화) |
| `PROJECT-COMMON-QA-ISSUE-CREATION-BOT` | @projectops 멘션 | QA 이슈 자동 생성 |
| `PROJECT-COMMON-SYNC-ISSUE-LABELS` | 라벨 파일 변경 | GitHub 라벨 동기화 |
| `PROJECT-COMMON-TEMPLATE-UTIL-VERSION-SYNC` | version.json 변경 | Util HTML 버전 동기화 (util 모듈 보유 레포에만 복사 — #491) |
| `PROJECT-COMMON-PROJECTS-SYNC-MANAGER` | 이슈 라벨 변경 | Issue Label → Projects Status 동기화 |

### 마이그레이션 기록 3계층 (#493·#494 — agent 필독)

마법사(full/workflows)가 끝나면 **대상 레포**의 `docs/projectops/migration/`에 실행 기록을 남긴다:

| 계층 | 파일 | 내용 | 소스 모듈 |
|------|------|------|----------|
| 1 | `PROJECTOPS-MIGRATION-GUIDE.md` | 고정 헤더(AI 해석 가이드라인) + 실행 엔트리 append-only: 동적 체크리스트·통과한 breaking 전문·yaml 메타(`schema` 버저닝) | `src/core/migration-guide.js` |
| 2 | `{stamp}_v{from}_to_v{to}.jsonl` | 파일별 결정·env 치환 전후값 이벤트 (파일명 grep으로 인과 추적) | `src/core/run-trace.js` |
| 3 | `{stamp}_..._.log` | 터미널 출력 원문 미러 (실 CLI에서만) | 〃 |

- 엔진(copy/env/legacy/orphan)은 `hooks.trace` / `ctx.trace`로 **null-safe emit** — trace 미주입 경로(기존 테스트)는 무영향.
- 가이드의 워크플로우 목록·env 값은 trace events에서 **파생**한다 (단일 소스). 새 엔진 동작을 추가하면 이벤트 emit도 함께 추가할 것.
- 민감값(PAT·token·secret·password 키)은 `scrubDetail`이 이벤트에서 자동 제거 — 우회 금지.

### 타입별 워크플로우

#### Flutter
| 파일명 | 용도 | 위치 |
|--------|------|------|
| `PROJECT-FLUTTER-CI` | 코드 분석 + 빌드 검증 | 기본 |
| `PROJECT-FLUTTER-ANDROID-PLAYSTORE-CICD` | Play Store 배포 | 기본 |
| `PROJECT-FLUTTER-ANDROID-FIREBASE-CICD` | Firebase App Distribution | 기본 |
| `PROJECT-FLUTTER-ANDROID-TEST-APK` | 테스트 APK 빌드 | 기본 |
| `PROJECT-FLUTTER-IOS-TESTFLIGHT` | TestFlight 배포 | 기본 |
| `PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT` | 테스트 빌드 | 기본 |
| `PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER` | 댓글 트리거 빌드 | 기본 |
| `PROJECT-FLUTTER-ANDROID-SELFHOSTED-CICD` | 자체 서버(SMB) APK 배포 | 기본 |

#### ⚠️ 배포/publish 타겟 축 (#439, v4.2.0 — agent 필독)

배포는 **두 개의 독립 축**으로 표현된다. 마법사가 타입 확정 직후 물어본다 (단 `basic` 단독은 스킵 — 아래).

| 축 | 의미 | 다중성 | 값 | version.yml 키 |
|----|------|--------|-----|---------------|
| **deploy** | 실행물(서버/앱)을 어디에 올리나 | **택1** | `docker-ssh`(기본)·`vercel`·`none` | `options.deploy` |
| **publish** | 라이브러리/패키지를 어느 레지스트리에 내나 | **0..n 공존** | `nexus`·`npm`·`github-packages` | `options.publish` 배열 |

##### 🧭 intent(프로젝트 성격) 우선 분기 (#485, v4.2.14 — agent 필독)

두 축을 낱개로 묻던 구조가 사용자에게 "이게 나한테 해당되나?" 부담을 줬다. 이제 **먼저 프로젝트 성격(intent)을 한 번 묻고, 그 답이 위 두 축을 유도**한다.

| intent | deploy 질문 | publish 질문 | version.yml 키 |
|--------|------------|-------------|---------------|
| `app` | 물음 | **스킵**(`publish=[]`) | `options.intent` |
| `library` | **스킵**(`deploy=none`) | 물음 | |
| `both` | 물음 | 물음 | |
| `none` | **스킵**(`none`) | **스킵**(`[]`) | |
| `manual` | 물음 | 물음(기존 순차 질문 그대로 — 탈출구) | |

- `metadata.template.options.intent`에 저장. 구 version.yml(intent 없음)은 `deploy`/`publish` 값에서 **역추론**(`inferIntent`, `src/core/version-yml.js`)해 하위호환. deploy≠none&publish=[]→app, deploy=none&publish≠[]→library, 둘 다→both, 둘 다 없음→none.
- 비대화형 `--intent app|library|both|none|manual`. 미지정 시 `--deploy`/`--publish`에서 역추론(기존 CLI 무수정 동작). intent 명시 + 해당 축 플래그 없으면 intent가 그 축을 유도(library→deploy=none 등, `src/index.js`).
- 수정 메뉴에 "프로젝트 성격" 항목(#485) + 개별 축 항목(#483) 병존. 성격을 바꾸면 축이 재유도되고, 개별 축 항목은 그 축만 세밀 조정(`scope`).
- **`basic` 단독 타입은 intent 질문도 스킵** — `none`으로 확정.

##### 🧩 타입별 축 적용성 (#498 — agent 필독)

deploy/publish 축은 **타입에 따라 적용 자체가 안 될 수 있다.** `src/core/options-ask.js`의 `TYPE_DEPLOY_TARGETS`/`TYPE_PUBLISH_TARGETS` 선언이 타입별 적용 가능 타겟을 정의하고, `applicableTargets(types)`가 선택 타입 집합의 합집합을 산출한다.

- **모바일 앱 타입(flutter/react-native/react-native-expo)은 두 축 모두 빈 배열** — 스토어 배포(Play Store/TestFlight/Firebase 등)는 타입 워크플로우가 항상 포함되므로 서버 deploy 축과 무관하고, 레지스트리 publish 개념도 없다. basic처럼 **intent 질문까지 통째로 스킵**하고 `none`/`[]`로 조용히 확정한다 (안내 문구도 안 띄움 — 보여줄 이유가 없다).
- **저장값/CLI값이 적용 불가면 경고 없이 정리** — 구버전에서 flutter 단독에 `deploy: docker-ssh`가 저장된 레포도 업데이트 시 조용히 `none`/교집합으로 정리된다 (복사 결과 동일 — SSOT). 비대화형(`src/index.js`)도 동일 규칙.
- 수정 메뉴(`editMenu`)도 적용 불가 축 항목("프로젝트 성격"·"배포 방식"·"publish 타겟")을 숨긴다. 타입을 바꾸면 다음 진입부터 다시 노출.
- 서버형 타입(spring/react/node/python)은 현행 선택지 전체 유지 (동작 무변경 — 타입별 세분화는 후속 과제). 질문 선택지는 `applicable.*`로 필터링되므로 이후 선언만 좁히면 선택지가 자동 반영된다.
- **새 타입을 추가하면 두 선언에 항목을 반드시 넣는다** — `test/options-ask.test.js`의 정합성 테스트가 `project-types` 폴더(`server-deploy/`·`publish/<target>/`)와의 모순을 자동 검증한다. 미선언 타입은 보수적으로 전체 허용(질문 유지).

- **`basic` 단독 타입은 배포/publish 질문을 건너뛴다** — 서버·라이브러리 개념이 없는 범용 타입이라 물어보면 사용자가 당황한다. `deploy=none`·`publish=[]`로 조용히 확정하고 분석 카드에만 표시. 타입을 바꾸면(수정 메뉴 → 프로젝트 타입) 그때 질문이 등장한다. (구 js `isBasicOnly` 특례는 #498의 두-축-빈-타입 일반 판정 `noAxes`로 흡수됨 — `.sh`/`.ps1`은 #458 EOF)
- 실타입 질문 앞에는 "**왜 묻는지**" 맥락 한 줄을 붙인다 (서버 올릴 계획 있으면 고르고 없으면 넘기라는 안내).
- 비대화형: `--deploy docker-ssh|vercel|none` + `--publish nexus,npm`(csv). `.ps1`은 `-Deploy`/`-Publish`.
- **구 플래그 `--nexus`/`--npm-publish`는 deprecated**(1 minor 유지) — `--publish nexus`/`--publish npm`으로 해석되며 경고를 출력한다. `--nexus`는 추가로 `--deploy none`을 함의(구 동작 보존).
- version.yml의 구 키(`nexus`/`npm_publish`)는 통합/업데이트 시 **자동으로 신 축으로 변환·기록**된다 (SSOT — 이중 표기 금지).

#### Spring
| 파일명 | 용도 | 위치 |
|--------|------|------|
| `PROJECT-SPRING-SIMPLE-CICD` | SSH+Docker 배포 (기본, 단일 컨테이너) | spring/server-deploy/ |
| `PROJECT-SPRING-NONSTOP-TRAEFIK-CICD` | 무중단 배포 (Traefik Blue-Green) | spring/server-deploy/ |
| `PROJECT-SPRING-NONSTOP-NGINX-CICD` | 무중단 배포 (Nginx Blue-Green) | spring/server-deploy/ |
| `PROJECT-SPRING-PR-PREVIEW` | PR 프리뷰 배포 | spring/server-deploy/ |
| `PROJECT-SPRING-NEXUS-CI` / `-NEXUS-PUBLISH` | Nexus 라이브러리 배포 | spring/publish/nexus/ |
| `PROJECT-SPRING-GITHUB-PACKAGES-PUBLISH` | GitHub Packages 라이브러리 배포 | spring/publish/github-packages/ |

> 서버 배포 워크플로우(SIMPLE/NONSTOP-*/PR-PREVIEW)는 `server-deploy/`로 묶여 **`deploy=docker-ssh`일 때만 포함**된다(`vercel`/`none`이면 폴더째 제외). publish 워크플로우는 `<type>/publish/<target>/`에 있고 **선택된 publish 타겟 집합**으로 복사가 결정된다(타입은 파일 위치일 뿐 게이트 아님).
>
> **확장 규칙(agent 필독)**: 새 "서버 배포" 워크플로우는 **그 타입의 `<type>/server-deploy/`** 에 파일만 넣는다(deploy≠docker-ssh면 자동 제외). 현재 `server-deploy/`를 가진 타입은 `spring`·`python` 두 개다. **타입 폴더 직하위에 두면 `--deploy none`에서도 복사되므로 절대 그렇게 두지 않는다** (실제로 python이 이 함정에 빠져 #521에서 교정됨). 새 publish 타겟은 `<type>/publish/<target>/`에 넣고 마법사 질문 목록에 값을 추가한다. 타입 비종속 배포 타겟(Vercel 등)은 `common/deploy/<target>/`에 넣는다.
>
> **⚠️ 워크플로우를 리네임/삭제할 때 (agent 필독, #470)**: 구 이름을 `src/core/migrations/registry.js`에 반드시 추가한다 — 마법사 업데이트가 기존 통합 레포의 구 파일을 자동 무해화(.bak)하는 유일한 경로다(레거시 마이그레이션은 전부 이 레지스트리 한 곳에서 관리). tier는 `safe`(순수 리네임 — 공존 시 중복 실행 실해) / `confirm`(배포 파이프라인일 수 있음 — 자동 조치 없이 안내만) 중 실해 기준으로 고른다. `test/migrations.test.js`가 레지스트리와 현행 배포 세트의 충돌(살아있는 워크플로우 오살)을 자동 검증한다. 구 파일에 사용자 커스텀 설정이 들어있을 수 있으면 registry 항목에 `settingsExtractor`를 지정해 무해화 직전 version.yml로 자동 이관한다 (`rules/settings-extractors.js`, #478 이슈 헬퍼가 모범 사례).
> 참고: **타입 선택 해제로 남는 고아 워크플로우**는 registry가 아니라 `src/core/orphan-workflows.js`가 동적 감지한다(#487) — registry는 리네임·폐기 전용, 고아 정리는 템플릿 인벤토리 대조(정확한 파일명 일치) 방식이다. 대화형은 확인 후 .bak 무해화, 비대화형은 안내만 출력한다.
>
> **`.github/util/` 모듈 안의 파일을 리네임/폐기할 때도 동일하다 (#500)**: registry에 `category: "util-file"`(tier safe, 정확 경로)로 구 파일을 등록한다 — util 복사(`src/core/copy/util.js`)는 overlay라 구 파일을 지우지 않으므로 registry가 유일한 정리 경로다. `test/migrations.test.js`의 util-file 충돌 테스트가 현행 템플릿 파일 오살을 자동 검증한다.
>
> **⚠️ 브랜치 규칙(`YYYYMMDD_#번호_제목`)에 의존하는 워크플로우를 추가할 때 (agent 필독, #478)**:
> `.github/scripts/issue_helper.py`의 `GUIDE_LINES`에 (파일명, 안내 문구)를 추가하고,
> 워크플로우 헤더에 "⚠️ 브랜치 규칙 의존" 주석 블록을 넣는다. 상세: `docs/BRANCH-CONVENTION.md`

#### 공통 — 배포 타겟 / Secret 백업
| 파일명 | 기능 | 위치 | 조건 |
|--------|------|------|------|
| `PROJECT-COMMON-VERCEL-DEPLOY` | Vercel 프로덕션 배포 (React/Next 등) | common/deploy/vercel/ | `--deploy vercel` |
| `PROJECT-COMMON-SECRET-FILE-UPLOAD` | GitHub Secret → 서버(SSH) 업로드 | common/secret-backup/ | `--secret-backup` |

> Vercel은 `VERCEL_TOKEN`·`VERCEL_ORG_ID`·`VERCEL_PROJECT_ID` secret이 필요하다.

#### Python (FastAPI/Django)
| 파일명 | 용도 | 위치 |
|--------|------|------|
| `PROJECT-PYTHON-CI` | 빌드/검증 | 기본 |
| `PROJECT-PYTHON-SIMPLE-CICD` | SSH+Docker 배포 (단일 컨테이너) | python/server-deploy/ |
| `PROJECT-PYTHON-PR-PREVIEW` | PR 프리뷰 배포 | python/server-deploy/ |

> Spring과 동일한 SSH+Docker 엔진을 쓴다. 배포 2종은 `server-deploy/`에 있어 `deploy=docker-ssh`일 때만 포함된다 (#521에서 타입 루트 → `server-deploy/`로 이동, 그전엔 `--deploy none`에도 복사되던 버그가 있었다).

#### React (Next.js 포함)
| 파일명 | 용도 |
|--------|------|
| `PROJECT-REACT-CI` | 빌드 검증 (.next/cache 캐싱 포함) |
| `PROJECT-REACT-CICD` | Docker 빌드 및 배포 (Next.js SSR 옵션 포함) |

> `next` 타입은 v4.1.0에서 `react`로 흡수되었습니다 (PROJECT-NEXT-* 워크플로우 삭제).

#### Node — npm publish (opt-in)
| 파일명 | 용도 | 위치 |
|--------|------|------|
| `PROJECT-NODE-NPM-PUBLISH` | main push 시 version.yml 버전으로 공개 npmjs 배포 (멱등, NPM_TOKEN secret) | node/publish/npm/ |

> `--publish npm`으로 포함한다(구 `--npm-publish`는 deprecated alias). 선택 값은 `version.yml`의 `metadata.template.options.publish` 배열에 저장된다.

---

## 핵심 스크립트

### version_manager (.py가 실 로직, .sh는 위임 shim — #448)
```bash
.github/scripts/version_manager.sh get            # 또는: python .github/scripts/version_manager.py get
.github/scripts/version_manager.sh increment       # patch +1
.github/scripts/version_manager.sh set 2.0.0
.github/scripts/version_manager.sh sync
.github/scripts/version_manager.sh get-code
.github/scripts/version_manager.sh increment-code
```
> v4.2부터 로직은 `version_manager.py`(stdlib 전용 — yq/jq 불필요)에 있고 `.sh`는 Python 위임 shim이다. Windows에서는 `python .github/scripts/version_manager.py get`을 직접 실행한다. **integrator 복사 목록에 `.sh`+`.py` 한 쌍이 모두 있어야 한다** (`truncate_release_notes.*`도 동일).

### changelog_manager.py
```bash
python3 .github/scripts/changelog_manager.py update-from-summary
python3 .github/scripts/changelog_manager.py generate-md
python3 .github/scripts/changelog_manager.py export --version 1.2.3 --output release_notes.txt
```

### changelog_providers/ (릴리스 노트 생성 사다리 — 전부 .py, #455)
`RELEASE-CHANGELOG` 워크플로우의 fallback-summary job이 `ladder.py`를 호출한다.
version.yml `options.changelog.provider`에 따라 **선택 provider → `github_ai.py` → `commit.py`(안전망)** 순으로 폴백하며, 폴백 발생 시 PR 댓글로 알린다.

| provider | 스크립트 | 비고 |
|---|---|---|
| `github-ai` (신규 설치 기본) | `github_ai.py` | GitHub Models API — job `permissions: models: read` + GITHUB_TOKEN만으로 동작 (API 키 불필요) |
| `openai`/`gemini`/`claude`/`ollama` | `openai_compatible.py` | OpenAI 호환. `MODEL_API_KEY` secret 필요 (ollama는 `changelog.base_url`) |
| `commit` | `commit.py` | 커밋 분석 — AI·네트워크 무의존 최후 보루 |
| `coderabbit` (미설정 시 기본 — 기존 동작 보존) | 워크플로우 Job 1 폴링 | 무응답 시 사다리(github-ai → commit)로 폴백 |

테스트: `python -m pytest .github/scripts/test/test_changelog_providers.py`. npx 복사 엔진(`src/core/copy/simple.js`)이 5종(.py)을 사용자 프로젝트에 복사한다.

### issue_helper.py (이슈 브랜치/커밋 댓글 — #478에서 내재화)
이슈 생성/제목 수정 시 `PROJECT-COMMON-SUH-ISSUE-HELPER.yaml`이 실행. 외부 액션 의존 없음 (stdlib 전용).
설정: `version.yml` `metadata.template.options.issue_helper` (branch_prefix/commit_template/commit_type_map/timezone/show_guide 등 — 없으면 기본값).
브랜치 코어(`YYYYMMDD_#번호_제목`)와 댓글의 `Guide by SUH-LAB`·`### 브랜치` 코드블록은 불변 계약 — 소비자 목록은 `docs/BRANCH-CONVENTION.md`.
구 MODULE 워크플로우의 커스텀 설정은 마이그레이션이 자동 이관한다 (`rules/settings-extractors.js`).
테스트: `python3 -m pytest .github/scripts/test/test_issue_helper.py`

### template_integrator.sh / .ps1 — ⚠️ 지원 종료 (EOF, #458)
**두 스크립트는 v4.3.0에서 안내용 shim으로 교체되었다.** 실행하면 `npx projectops` 안내만 출력하고 종료한다(파일 직접 실행 시 exit 1). 다음 minor에서 파일 자체를 제거할 예정.
통합/업데이트/스킬 설치는 전부 **`npx projectops`** 한 경로다. 배포/publish 축·secret 백업 등 모든 옵션은 npx 마법사가 질문하며, 선택 값은 `version.yml`의 `metadata.template.options.*`에 동일하게 저장된다.

**초기화/통합 시 복사되지 않는 템플릿 전용 파일**:
```
CLAUDE.md, CONTRIBUTING.md, LICENSE
CHANGELOG.md, CHANGELOG.json
template_integrator.sh / .ps1
docs/, .github/scripts/test/, .github/workflows/test/
.claude-plugin/, .codex-plugin/, .agents/, .cursor/, skills/, scripts/
package.json, harness/         # pi 패키지 매니페스트 + Persona Harness
```

#### ⚠️ 레포 루트에 "마켓플레이스/템플릿 전용" 파일·폴더를 추가할 때 (agent 필독)

이 레포는 **두 정체성**을 동시에 가진다 — 이 점이 일반 레포와 다른 핵심이다.

1. **템플릿 레포**: GitHub "Use this template"로 새 프로젝트를 만들면 `.github/scripts/template_initializer.py`(.sh는 위임 shim)가 마켓플레이스/템플릿 전용 파일을 **삭제**한다.
2. **마법사 배포원**: `npx projectops`(src/)가 기존 프로젝트에 템플릿을 통합할 때 그 파일들을 **복사 대상에서 제외**한다 (`src/core/exclusions.js`).

따라서 레포 루트에 새 파일/폴더를 추가했는데 그게 **이 레포에서만 의미 있고 사용자 프로젝트로 흘러가면 안 되는 것**(플러그인 매니페스트, skill, pi 패키지 파일, 내부 문서 등)이라면, **아래 2곳(+필요 시 3번째)을 반드시 함께 수정**한다. 한 곳만 고치면 새 프로젝트가 오염되거나 마법사가 불필요한 파일을 복사한다 — 실제로 자주 빠뜨리는 함정이다.

| # | 파일 | 수정할 위치 | 동작 |
|---|------|------------|------|
| 1 | `.github/scripts/template_initializer.py` | 삭제 목록 튜플 배열 (`template_integrator.sh` 항목 근처) | `("파일명", "설명")` 항목 추가 (**삭제**) |
| 2 | `src/core/exclusions.js` | `DOCS_TO_REMOVE` 등 제외 배열 | 파일/폴더명 추가 (**복사 제외**) |
| 3 | `.github/workflows/PROJECT-TEMPLATE-PLUGIN-VERSION-SYNC.yaml` | 버전 동기화 step + `git add` | 버전 필드가 있는 매니페스트(`package.json` 등)면 동기화 step 추가 |

> (구 `template_integrator.sh`/`.ps1`의 `plugin_items_to_remove` 배열은 #458 EOF로 사라졌다 — 이제 npx `exclusions.js`가 유일한 복사 제외 지점이다.)
>
> **체크 순서**: 새 루트 파일 추가 → "이게 사용자 프로젝트에도 필요한가?" 자문 → **아니오면 위 1·2를 모두 수정**. 버전을 `version.yml`과 맞춰야 하는 매니페스트면 3번도 추가. 수정 후 `python -m py_compile .github/scripts/template_initializer.py`와 `npm test`로 확인한다.
>
> **반대로**, 추가한 게 사용자 프로젝트에도 같이 가야 하는 공통 자산(워크플로우·스크립트·설정)이라면 위 목록에 넣지 않는다 — 제외하면 통합 대상 프로젝트가 그 기능을 못 받는다.

#### ⚠️ macOS는 bash 3.2 + BSD 도구다 — `.sh` 작성·검증 시 절대 잊지 말 것 (agent 필독, 실측)

> **핵심: 윈도우(`.ps1`·Git Bash)에서 잘 돌아도 macOS에서 깨질 수 있다.** macOS 기본 `/bin/bash`는 라이선스 문제로 **3.2.57(2007년)에 박제**돼 있고, 기본 grep/sed도 **BSD 계열**이다. `.sh`는 항상 **`/bin/bash`(3.2) + BSD 도구**로 검증한다. "윈도우에서만 테스트했다"가 실제 사용자(macOS) 버그를 통째로 놓치게 한 주원인이다. (실측: 이슈 #415·#418 — 윈도우 정상, macOS만 깨짐.)

**bash 3.2에서 못 쓰는 것 (4+ 전용 → macOS에서 조용히 오작동)**
- **연관배열 `declare -A` 금지.** bash 3.2는 미지원 → 모든 문자열 키가 **인덱스 0으로 뭉개져** "키가 1개만 남는" 버그가 된다(실측 #418: @wizard env 키가 6개인데 1개만 수집). 동적 key-value가 필요하면 eval 동적변수 + 16진 키 인코딩 헬퍼(구 integrator의 `_kv_*` 패턴, 3.2/4 공용)를 쓴다.
- **`declare -g` 금지.** bash 3.2에서 `invalid option`. 최상위 레벨이면 어차피 전역이니 `-g` 없이 선언한다.
- `mapfile`/`readarray`, `${var,,}`/`${var^^}`(대소문자), `&>>`도 4+ 전용 → 사용 금지.

**BSD 도구 함정 (macOS 기본 grep/sed ≠ GNU)**
- **`grep -P`/`-oP`/`\K` 금지** (PCRE는 GNU 전용). `grep -E`로 라인 잡고 `sed -E`로 추출한다. (실측 #415: `grep: invalid option -- P`로 버전 감지 실패.)
- **`grep`이 매치 0건이면 `exit 1`** → `set -e`에서 `var=$(grep ...)` 단독 대입이 스크립트를 죽인다. `|| true`로 흡수하거나 `| head`/`| sed` 파이프로 끝낸다(pipefail 없으면 파이프 마지막 명령 코드만 봄). (실측 #415.)
- `sed -i`는 BSD가 `sed -i ''` / `sed -i.bak` 형태로 인자가 다르다. `readlink -f`·`date -d`·`xargs -r`도 BSD 미지원.

**`set -e` + 함수 끝 종료코드 (메뉴 아닌 일반 함수도 해당)**
- 위 "var=$(menu_fn)" 함정의 일반화: **함수의 마지막 명령이 비-0이면**, 그 함수가 호출부의 마지막 명령일 때 `set -e`가 스크립트를 통째로 죽인다. `[ -d x ] || return`(폴더 없으면 1 전파), `[ cond ] && cmd`(조건 거짓이면 1), `command -v foo && ...`(미설치면 1), `cp ... && ...`(실패면 1) 모두 위험. → early return은 `return 0` 명시, 끝줄 `조건 && 명령`은 `{ ...; } || true`로 감싼다. (실측 #415: Nexus/Secret 메뉴·interactive_mode·codex 제거·config cp 등 5곳.)

**검증 방법**: `bash -n`(문법)만으론 부족하다. **반드시 `/bin/bash`(3.2)로 실제 실행**한다. 함수만 떼어 `source` 후 호출해 실제 입력으로 **종료코드 0 완주**를 확인한다. `which bash`가 brew bash(`/opt/homebrew/bin/bash`, 4+)를 가리키면 `/bin/bash`로 명시 실행해 3.2를 강제한다.

---

## ⚠️ 워크플로우 YAML 검증 — 로컬 파서를 GitHub 실제 동작으로 착각하지 말 것 (agent 필독)

> **핵심 원칙: 로컬 YAML 검증 도구(`actionlint`·Ruby `psych`·Python `pyyaml`)가 빨갛게 떠도, 그 워크플로우가 GitHub에서 실제로 깨진다는 뜻이 아니다.** 도구가 못 읽는 것과 GitHub이 못 돌리는 것은 **다르다.** 멀쩡히 돌던 워크플로우를 "검증 도구가 오류라고 했으니" 멋대로 고치지 마라 — 이건 실측으로 확인된 함정이다.

### 왜 이런 일이 생기나 (실측 사례)

`run: |` 블록 안에서 heredoc을 **들여쓰기 0칸 본문**으로 쓰는 패턴이 대표적이다:
```yaml
        run: |
          cat > android/key.properties << EOF
storeFile=keystore/key.jks      # ← 들여쓰기 0칸
EOF
```
- `actionlint`·`psych`·`pyyaml`은 이걸 `could not find expected ':'`로 **파싱 실패** 처리한다 (블록 스칼라 경계를 들여쓰기로만 판단하는 엄격한 go-yaml/libyaml 계열).
- 하지만 **GitHub Actions의 실제 YAML 파서는 이 heredoc을 정상 처리해서 워크플로우가 success한다.** 즉 도구의 한계지 진짜 버그가 아니다.

### 진짜 깨졌는지 확인하는 올바른 순서 (추측 금지, 실측만)

1. **GitHub 실행 이력을 먼저 본다 (가장 강력한 증거).** 같은 파일/패턴이 실제 `success`한 run이 있으면 → **멀쩡한 코드 확정.** 절대 손대지 마라.
   ```bash
   PAT=$(python3 -c "import json;print(json.load(open('$HOME/.projectops/config/config.json'))['github']['global_pat'])")
   curl -s -H "Authorization: token $PAT" \
     "https://api.github.com/repos/<owner>/<repo>/actions/workflows/<file>.yaml/runs?per_page=20" \
     | python3 -c "import json,sys;from collections import Counter;d=json.load(sys.stdin);print(Counter(r['conclusion'] for r in d.get('workflow_runs',[])))"
   ```
2. **"잘 작동하는 기준 레포"와 대조한다.** 이 템플릿의 검증 기준 레포는 **`TEAM-ROMROM/RomRom-FE`(Flutter)·`TEAM-ROMROM/RomRom-BE`(Spring)** 다 — 실제 운영 중이고 빌드가 success한다. `passQL`은 **이 템플릿을 테스트하는 실험 프로젝트**라 (Flutter init도 미완) **신뢰 기준이 아니다.** passQL의 failure를 근거로 템플릿이 깨졌다고 결론짓지 마라.
3. **YAML 파싱 자체가 깨졌는지는 run annotations로 확인한다.** GitHub이 파싱에 실패하면 `syntax error` annotation을 남긴다. annotation이 없고 job이 빌드 중간 step에서 실패했으면 → **YAML은 정상, 원인은 빌드 로직(secret 누락 등)이다.**
   ```bash
   curl -s -H "Authorization: token $PAT" "https://api.github.com/repos/<owner>/<repo>/check-runs/<job_id>/annotations"
   ```

### 검증 도구를 쓸 때의 자세

- `actionlint`/`psych`/`pyyaml`은 **참고용 신호**다. 빨간불 = "확인해봐라"지 "고쳐라"가 아니다.
- 특히 **이미 운영 중인 워크플로우**(GitHub에 success 이력 있음)는 도구가 뭐라 하든 **건드리지 않는 것이 기본값**이다.
- 정 고쳐야 한다면, "잘 작동하는 RomRom이 같은 자리를 어떻게 쓰는지" 먼저 받아 대조하라. (예: key.properties는 RomRom-FE가 `echo "k=v" >> file` 방식으로 쓰며 success — 0칸 heredoc을 안 쓴다.)
- 내가 토큰화·치환 같은 **env 값만 바꾸는 작업**을 할 때, `run:`/`uses:`/`with:`/`steps:` 등 **실행 로직은 한 줄도 건드리지 않았는지** `git diff`로 자가검증하라:
  ```bash
  git diff <files> | grep "^+" | grep -v "^+++" | grep -vE "내가_의도한_변경_패턴"   # 결과 비면 실행로직 무손상
  ```

---

## 트리거 키워드

### 댓글 기반
| 키워드 | 워크플로우 | 기능 |
|--------|-----------|------|
| `@projectops create qa` | QA-ISSUE-CREATION-BOT | QA 이슈 자동 생성 |
| `@projectops build app` | PROJECTOPS-APP-BUILD-TRIGGER | Android + iOS 빌드 |
| `@projectops apk build` | PROJECTOPS-APP-BUILD-TRIGGER | Android만 빌드 |
| `@projectops ios build` | PROJECTOPS-APP-BUILD-TRIGGER | iOS만 빌드 |

### 브랜치 기반
| 브랜치 | 트리거 | 워크플로우 |
|--------|--------|-----------|
| `develop` | push | CI (버전 증가 없음) |
| `main` | PR (develop→main) | CHANGELOG-CONTROL (버전 확정 + automerge) |
| `main` | push (릴리스 머지) | README-UPDATE, PLUGIN-SYNC, NPM-PUBLISH, CICD |
| `main` | push (직접) | VERSION-CONTROL 안전망 (+CICD — 비권장 경로) |

---

## 이슈/PR 템플릿

**이슈 템플릿**: `bug_report.md` / `feature_request.md` / `design_request.md` / `qa_request.md`

**이슈 라벨**: `긴급, 문서, 작업전, 작업중, 담당자확인, 피드백, 작업완료, 보류, 취소`

---

## Skills (Claude Code 플러그인)

**플러그인명**: `projectops`

```bash
claude plugin marketplace add Cassiiopeia/projectops
claude plugin install projectops@projectops-marketplace --scope user
```

| 명령어 | 용도 |
|--------|------|
| `analyze` | 코드 분석 |
| `plan` | 계획 수립 |
| `implement` | 구현 |
| `review` | 코드 리뷰 |
| `refactor` / `refactor-analyze` | 리팩토링 |
| `test` / `testcase` | 테스트 |
| `troubleshoot` | 트러블슈팅 |
| `document` | 문서화 |
| `design` / `design-analyze` | 설계 |
| `build` | 빌드 관리 |
| `figma` | Figma 연동 |
| `ppt` | 프레젠테이션 |
| `spring-test` | Spring 테스트 생성 |
| `init-worktree` | Git worktree 생성 |
| `commit` | 이슈 기반 커밋 자동화 |
| `github` | GitHub 전반: 이슈 생성/조회/수정/댓글/라벨/담당자, PR 생성/머지/조회, 레포 탐색, Actions 로그, Secret 관리 (이슈 작성+등록 포함) |
| `report` | 구현 보고서 생성 |
| `changelog-deploy` | develop push → main으로 릴리스 PR(deploy PR) → 버전 확정 + automerge / automerge 실패 시 재트리거 |
| `synology-expose` | 시놀로지 서비스 외부 노출 가이드 |
| `ssh` | 원격 서버 SSH 접속 및 명령 실행 (AWS EC2, 시놀로지 NAS, Linux 서버 등) |
| `skill-creator` | skill 생성/리뷰/개선 (CREATE·REVIEW·IMPROVE 3모드) |

---

## Skills 개발 가이드

### 폴더 구조
```
skills/
├── {skill-name}/SKILL.md
├── config.json.example       # 전체 config 구조 예시 (모든 skill_id 섹션 포함)
└── references/
    ├── common-rules.md       # 절대 규칙, 커밋 컨벤션, 작업 시작 프로토콜(페르소나 로드 포함)
    ├── personas.md           # 5 전문가 페르소나 + 6 마인드셋 (harness/PERSONA.md single source) — 코드 스킬이 시작 시 로드
    ├── self-review-checklist.md # plan/analyze/implement 산출물 제출 전 자체검토 + Devil's Advocate 게이트
    ├── config-rules.md       # config 경로·스키마·읽기/쓰기 표준
    ├── mcp-subcommand-rules.md # suh_command 서브커맨드 MCP-style 설계 표준 (JSON+next, 코드 템플릿)
    ├── doc-output-path.md
    ├── project-detection.md
    ├── code-style-detection.md
    ├── tech-flutter.md
    ├── tech-react.md
    └── tech-spring.md
```

### 핵심 원칙

1. **config는 agent가 Read/Write tool로 직접 처리** — `config-get` CLI 호출 금지
2. **config 경로·스키마는 `references/config-rules.md` 참조** — skill 내 직접 기술 금지
3. **GitHub API는 curl 직접 호출** — `gh` CLI, Python CLI 모두 금지
4. **OS 호환성**: Python 실행 시 `PYTHON=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)` 패턴 사용
5. **skill 시작 시 필독**: `references/common-rules.md` → (코드 스킬이면) `references/personas.md`에서 자기 페르소나 로드 → (config 필요 시) `references/config-rules.md` → (기술별) `tech-*.md`
6. **Python 행동 로직은 재사용 스크립트 파일 + MCP-style 표준** — 아래 "Python 행동 스크립트 표준" 절을 따른다. SKILL.md에 긴 Python heredoc 인라인 금지.

### Python 행동 스크립트 표준 (필수)

스킬이 Python으로 외부 시스템(GitHub API, SSH 등)을 호출할 때 반드시 이 패턴을 따른다.
이 표준은 Windows Git Bash + macOS 양쪽에서 깨지지 않도록 실측 검증된 것이다.

> **`suh_command.py`에 새 서브커맨드를 추가할 때는 `skills/references/mcp-subcommand-rules.md`를 먼저 읽는다.** 입력 계약·JSON 스키마(`ok`/`verdict`/`summary`/`next`)·gh_client와 command 레이어 분리·테스트 패턴을 코드 템플릿과 체크리스트로 정리해 둔 구체적 구현 레퍼런스다. 모범 사례는 `actions`·`deploy-status` 서브커맨드.

#### 1. 로직은 재사용 스크립트 파일에 둔다

- `skills/{skill-name}/scripts/{name}.py` 에 행동 로직을 고정 파일로 저장한다.
- SKILL.md는 **호출법만** 기술한다 (서브커맨드·인자·환경변수). 긴 Python 코드를 SKILL.md에 인라인하지 않는다.
- 이유: SKILL.md는 LLM이 매번 재입력하는 문서다. redirect strip 같은 핵심 로직을 인라인하면 재입력 시 누락·오타 위험.

#### 2. MCP-style 서브커맨드 — 입력 해석은 agent, 실행은 .py

- .py는 `argparse` 서브커맨드로 **명확한 입력 계약**을 갖는다 (예: `show-run RUN_ID`, `joblog JOB_ID`, `resolve-pr PR_NUM`).
- .py는 URL 파싱·PR→run 추적 같은 **해석을 하지 않는다**. agent가 사용자 입력(URL/PR/브랜치/빈입력)을 해석해 정확한 서브커맨드·인자를 넘긴다.
- SKILL.md에 "이런 입력 → 이런 서브커맨드" 라우팅 규칙을 명시해 agent가 제대로 판단하게 한다.
- 효과: .py는 단독 실행·테스트 가능(MCP tool처럼 예측 가능), agent는 유연하게 입력 해석.

#### 3. 인자는 환경변수로 전달 — heredoc·/tmp·stdin pipe 금지

- 민감값(PAT 등)과 인자는 **환경변수**로 넘긴다. heredoc 본문 보간·`/tmp` 임시파일·`curl | python` stdin pipe 전부 금지.
- 이유 (실측):
  - `/tmp` 경로 → Windows Git Bash에서 깨짐.
  - `curl | python3` → Windows에서 Exit code 49.
  - heredoc `{변수}` 보간 → 한글·특수문자 이스케이프 깨짐.

```bash
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
GH_PAT="..." GH_OWNER="..." GH_REPO="..." \
  PYTHONIOENCODING=utf-8 "$PYTHON" "$PROJECT_ROOT/skills/{skill}/scripts/{name}.py" show-run 12345
```

#### 4. 출력은 언제나 JSON — 내부에 `next` 힌트 필드

- 모든 서브커맨드는 **항상 JSON**을 stdout으로 출력한다 (plain text 모드 없음, `--json` 옵션도 두지 않는다).
- JSON에 `ok`(성공 여부), 데이터 필드, 그리고 **`next`**(agent가 이어서 호출할 다음 서브커맨드 힌트)를 담는다.
- agent는 단일 JSON 형식만 파싱 → 다음 행동을 정확히 판단.

```json
{"ok": true, "run_id": 12345, "conclusion": "failure",
 "failed_jobs": [{"job_id": 678, "name": "build", "failed_steps": ["Flutter build"]}],
 "next": "joblog 678"}
```

#### 5. 표준 라이브러리 우선 — 진짜 목표는 mac/Windows 양쪽 동작 + 내부망 대응

- "의존성 0"이 목표가 아니다. **진짜 목표는 mac·Windows 어디서든 깨지지 않고, 내부망(폐쇄망)에서 `pip install` 불가해도 돌아가는 것**이다.
- 따라서 가능하면 표준 라이브러리(`urllib.request`/`json`/`argparse`)로 해결한다 — 추가 설치 없이 양쪽 OS·내부망에서 바로 동작하기 때문.
- 표준 라이브러리로 안 되는 일이면 **외부 패키지를 당연히 쓴다**. 다만 스크립트 내에서 설치 시도(`pip install ... -q`) + 실패 시 수동 설치 안내를 둬서 내부망에서도 우아하게 처리한다. (예: secret 암호화 PyNaCl)

#### 6. redirect 시 Authorization 헤더 strip (필수 보안·동작)

- GitHub job logs 등 일부 엔드포인트는 Azure Blob(SAS URL)로 302 redirect된다.
- urllib 기본 동작은 `Authorization` 헤더를 redirect 대상까지 전달 → Azure가 `403 AuthenticationFailed`.
- redirect 시 `Authorization` 헤더를 제거하는 핸들러를 반드시 둔다:

```python
class StripAuthRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            new.headers.pop("Authorization", None)
            new.unredirected_hdrs.pop("Authorization", None)
        return new
opener = urllib.request.build_opener(StripAuthRedirect)
```

### config 구조

모든 스킬의 config는 **단일 파일** `~/.projectops/config/config.json` 하나로 관리한다.
skill_id를 키로 각 스킬의 설정을 네임스페이스로 분리한다.

| 스킬 | config 섹션 키 | 비고 |
|------|--------------|------|
| `commit`, `github`, `changelog-deploy`, `report` | `github` | PAT + repos 공유 (이슈 생성 승인/담당자 설정 `issue.*` 키 포함) |
| `synology-expose` | `synology-expose` | NAS 인스턴스 정보 |
| `ssh` | `ssh` | SSH 서버 접속 정보 |

### 새 스킬에 config 추가하는 방법

1. `skill_id`(스킬 폴더명)를 키로 `config.json`에 섹션 추가
2. `skills/references/config-rules.md` §7에 스키마 문서화
3. `skills/config.json.example`에 예시 추가
4. SKILL.md에 `references/config-rules.md §2~3` 참조 명시

**별도 config 파일(`skill-name.config.json` 등)을 새로 만들지 않는다.**

### skill별 CLI 커맨드 (3-layer 아키텍처)

각 skill이 자체 `scripts/<scope>_cli.py`를 보유한다. 호출 패턴 = self-contained 5줄 (`skills/references/common-rules.md` §"skill별 py 분산 호출" 참조).

| skill | cli 파일 | 주요 서브커맨드 |
|---|---|---|
| github | `skills/pro-github/scripts/github_cli.py` | create-issue, get-issue, get-issues, list-issues, update-issue, close-issue, reopen-issue, search-issues, add-comment, list-comments, edit-comment, delete-comment, list-labels, add-labels, remove-label, set-labels, add-assignees, remove-assignees, create-pr, list-prs, update-pr, get-pr, add-pr-comment, close-pr, reopen-pr, merge-pr, normalize-title, create-branch-name, get-commit-template, explore, secrets, actions |
| commit | `skills/pro-commit/scripts/commit_cli.py` | get-issue-number, get-issue, normalize-title, get-commit-template |
| report | `skills/pro-report/scripts/report_cli.py` | get-output-path, add-comment |
| review | `skills/pro-review/scripts/review_cli.py` | get-output-path |
| troubleshoot | `skills/pro-troubleshoot/scripts/troubleshoot_cli.py` | get-output-path |
| changelog-deploy | `skills/pro-changelog-deploy/scripts/changelog_cli.py` | actions, deploy-status, list-prs, update-pr, create-pr |

공유 도메인 로직은 `scripts/common/`에 있다 (gh_client, config, paths, title, issue_number, gh_branch, manifest, emit, bootstrap).

> GitHub API 호출은 각 skill의 `<scope>_cli.py` 서브커맨드 우선. 새 동작이 필요하면 `skills/references/mcp-subcommand-rules.md` 기준으로 `common/gh_client` 헬퍼 + cli 서브커맨드 + 테스트를 추가한다. 신규 skill에 py 필요하면 `skills/pro-skill-creator/templates/python_cli_script.py` 골격을 복사.

### Agent 주의사항

| 상황 | 처리 |
|------|------|
| config 없음 | 대화형 수집 — 억지 추론 금지 |
| repo owner/repo 불명확 | `git remote get-url origin` 추출 → 실패 시 config `github_repos` 참조 |
| GitHub API 401 | PAT 만료 안내 + `/pro-github`에서 재등록 유도 (`references/config-rules.md §2~5`) |
| `gh` CLI 사용 시도 | 금지 — curl로 대체 |
| 공통 워크플로우 수정 | `project-types/common/`과 `.github/workflows/` 루트 **두 곳 동일하게** 유지 |
| GitHub 댓글에 마크다운 표 | `array.join('\n')` 패턴 사용 (template literal 들여쓰기 시 표 깨짐) |

---

## 기여 가이드라인 핵심

> 상세 내용: `CONTRIBUTING.md`, `docs/WORKFLOW-COMMENT-GUIDELINES.md`

### 워크플로우 추가 시
- 공통 워크플로우: `project-types/common/` (원본) + `.github/workflows/` 루트 (복사본) **동일 유지**
- 타입별 워크플로우: `project-types/[type]/`만
- 필수 요소: `workflow_dispatch`, `concurrency`, `[skip ci]`

### Breaking Changes
호환성 문제 변경 시 `.github/config/breaking-changes.json`에 등록:
```json
{
  "버전": {
    "severity": "critical | warning",
    "title": "제목",
    "message": "상세 설명 및 조치 방법"
  }
}
```

---

## Skill routing

이 프로젝트에서 사용 가능한 스킬 호출 규칙:

| 요청 유형 | 호출 스킬 |
|----------|----------|
| **이슈 만들어줘, 이슈 등록, 버그 리포트, PR 생성, PR 올려줘, PR 머지, 이슈 댓글, 댓글 달아줘/수정/삭제, 이슈 확인, 이슈 닫기, 라벨 추가/제거, 담당자 추가, PR 조회, GitHub API** | **`pro-github` ← 최우선 트리거** |
| 코드 분석, 현황 파악 | `pro-analyze` |
| 버그, 오류, 원인 파악 | `pro-troubleshoot` |
| 새 기능 설계 | `pro-plan` → `pro-implement` |
| 코드 리뷰 | `pro-review` |
| 이슈 작성 / 이슈 생성 | `pro-github` (이슈 생성 워크플로우 흡수) |
| 커밋 | `pro-commit` |
| 배포 / automerge 실패 재트리거 | `pro-changelog-deploy` |
| 보고서 | `pro-report` |
| 원격 서버 SSH 접속, 로그/상태 확인 | `pro-ssh` |
| 브레인스토밍 | `superpowers:brainstorming` |
| 구현 계획 | `superpowers:writing-plans` |
| 계획 실행 | `superpowers:executing-plans` |

## 커밋 컨벤션 필수 규칙

커밋 메시지 앞에 이모지·태그(`🚀[기능개선]`, `⚙️[기능추가]` 등) **절대 포함 금지**.
이슈 제목에서 이모지+태그를 제거한 순수 내용만 사용한다.

- 올바른 예: `RELEASE-CHANGELOG PR 본문 초기화 보호 로직 추가 : feat : ... https://...`
- 잘못된 예: `🚀[기능개선][ChangeLog] RELEASE-CHANGELOG : feat : ...`

report·implement 등 커밋을 직접 실행하는 스킬도 이 규칙을 따른다.

## 기능 구현 워크플로우

새 기능 구현 시 순서:

1. `superpowers:brainstorming` — 설계 및 스펙 확정
2. `superpowers:writing-plans` — 상세 구현 계획
3. `superpowers:executing-plans` — 실제 구현
4. `superpowers:requesting-code-review` — 코드 리뷰 요청

---

## 알려진 스킬 동작 문제 및 해결 가이드

### 1. `pro-github` 스킬 자동 트리거 실패

**문제**: 사용자가 "PR 올려줘", "댓글 달아줘" 등을 요청해도 `pro-github` 스킬이 자동으로 트리거되지 않고, 다른 스킬(brainstorming 등)이 먼저 실행됨.

**원인**: `superpowers:using-superpowers` 규칙에서 어떤 스킬이든 1% 가능성이면 먼저 호출하도록 강제되는데, `brainstorming` 등 범용 스킬이 더 넓은 설명을 가지고 있어 우선 매칭됨. `pro-github` description의 트리거 키워드("PR 만들어줘", "댓글 달아줘")가 있어도 다른 스킬보다 낮은 우선순위로 처리됨.

**해결 방법 (사용자 관점)**:
- GitHub 작업 시 명시적으로 `/pro-github` 슬래시 커맨드를 입력
- 또는 메시지 앞에 "github:" 접두어 사용 ("github: PR 올려줘")

**해결 방법 (스킬 개발 관점)**:
- `skills/github/SKILL.md`의 description에 더 구체적인 트리거 키워드 추가 필요
- 또는 `pro-github`를 Skill routing 표에 더 명확한 패턴으로 등록
- PR 생성, 이슈 댓글, GitHub API 작업은 **반드시 `/pro-github` 명시 호출** 원칙을 CLAUDE.md에 명시

### 2. `pro-github` 스킬 실행 시 Repo 자동 감지 실패 (워크트리 환경)

**문제**: 스킬이 `git remote get-url origin`으로 현재 디렉토리의 repo를 감지하는데, Claude Code가 **projectops** 레포 컨텍스트에서 실행 중이면 `TEAM-ROMROM/RomRom-BE`가 아닌 `Cassiiopeia/projectops`를 origin으로 잡음.

**원인**: 작업 대상 레포(RomRom-BE)가 별도 워크트리에 있거나, 현재 Claude Code 세션의 primary working directory가 다른 레포인 경우 발생.

**해결 방법**:
- 스킬 호출 시 대상 레포를 명시: `/pro-github TEAM-ROMROM/RomRom-BE 이슈 #653 PR 생성`
- config의 `repos` 목록에 등록된 레포는 이름으로 지정 가능: "RomRom-BE PR 올려줘"

### 3. Windows 환경 Python `urllib` 에러 (Exit code 49)

**문제**: `curl ... | python3 -c "..."` 파이프라인에서 `Exit code 49` 오류 발생. Python이 정상 설치되어 있어도 bash 파이프에서 python3 경로 인식 실패.

**원인**: Windows Git Bash 환경에서 `python3` 명령이 Windows Store python stub을 가리키거나, 파이프 stdin 처리 방식 차이.

**해결 방법 (스킬 개선 필요)**:
- Windows 환경에서 GitHub API JSON 파싱은 `curl | python3 -c` 대신 **PowerShell `Invoke-RestMethod`** 사용
- 또는 curl 응답을 파일로 저장 후 파싱: `curl ... -o /tmp/out.json && python3 /tmp/out.json`
- `skills/github/SKILL.md`에 Windows 대응 PowerShell 코드블록 추가 필요

**임시 해결**: Claude가 PowerShell tool을 직접 사용하여 `Invoke-RestMethod`로 GitHub API 호출

### 4. PR head 브랜치명 422 오류 (한글 브랜치명)

**문제**: 브랜치명에 한글이 포함된 경우(`20260420_#653_FCM_푸시_페이로드에_라우팅용_데이터_포함_필요`) GitHub API PR 생성 시 `422 Validation Failed: head invalid` 오류.

**원인**: PowerShell `ConvertTo-Json`이 한글 포함 문자열을 올바르게 인코딩하지 못하거나, GitHub API가 URL-encoded 브랜치명을 다르게 처리.

**해결 방법**:
- PR 생성 전 실제 remote 브랜치 존재 여부를 먼저 확인: `git ls-remote origin "브랜치명"`
- 브랜치명이 push되어 있는지 확인 후 API 호출
- `head`에 `owner:branch` 형식 사용: `"TEAM-ROMROM:브랜치명"`
