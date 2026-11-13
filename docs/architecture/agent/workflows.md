# 워크플로우 규칙

> **언제 읽나:** `.github/workflows/`, `project-types/` 의 워크플로우를 추가·수정·리네임하거나, 배포/publish 축·댓글 트리거·이슈 템플릿을 건드릴 때
> `CLAUDE.md` 에서 옮긴 정본입니다. `CLAUDE.md` 에는 요약과 이 문서로 가는 링크만 있습니다.

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

## 핵심 워크플로우

### 공통 워크플로우

| 파일명 | 트리거 | 기능 |
|--------|--------|------|
| `PROJECT-TEMPLATE-INITIALIZER` | 저장소 생성 | 템플릿 초기화 (일회성) |
| `PROJECT-TEMPLATE-PLUGIN-VERSION-SYNC` | main 푸시 | 플러그인 매니페스트 버전 동기화 (**이 레포 전용**) |
| `PROJECT-TEMPLATE-CI` | develop·main 푸시/PR | 테스트 — 빠른 길/넓은 길 2갈래 (**이 레포 전용**, 아래 절) |
| `PROJECT-TEMPLATE-NPM-PUBLISH` | main 푸시 | 같은 커밋의 CI job이 전부 통과한 뒤 `projectops` npm 패키지 배포 (**이 레포 전용**) |
| `PROJECT-COMMON-VERSION-CONTROL` | main 직접 푸시(안전망) | 릴리스 머지 외 push 시 patch 증가 |
| `PROJECT-COMMON-RELEASE-CHANGELOG` | main PR (develop→main) | 버전 확정(semver 승격 — #546) + AI 체인지로그 + automerge |
| `PROJECT-COMMON-README-VERSION-UPDATE` | main 푸시 | README 버전 동기화 |
| `PROJECT-COMMON-SUH-ISSUE-HELPER` | 이슈 생성 | 브랜치명/커밋 제안 (내부 py — `issue_helper.py`, #478 내재화) |
| `PROJECT-COMMON-QA-ISSUE-CREATION-BOT` | @projectops 멘션 | QA 이슈 자동 생성 |
| `PROJECT-COMMON-SYNC-ISSUE-LABELS` | 라벨 파일 변경 | GitHub 라벨 동기화 |
| `PROJECT-COMMON-TEMPLATE-UTIL-VERSION-SYNC` | version.json 변경 | Util HTML 버전 동기화 (util 모듈 보유 레포에만 복사 — #491) |
| `PROJECT-COMMON-PROJECTS-SYNC-MANAGER` | 이슈 라벨 변경 | Issue Label → Projects Status 동기화 (선택 — `common/projects-sync/`, `--projects-sync`, #716) |
| `PROJECT-COMMON-AI-PR-SUMMARY` | 작업 PR 생성·갱신 | 변경 요약 댓글 (선택 — `common/pr-summary/`, #566) |

### ⚠️ 워크플로가 부르는 fastlane lane 은 실재해야 한다 (#601 — agent 필독)

**Fastfile 은 마법사가 덮어쓴다.** lane 을 손으로 더하면 다시 깔 때 사라지므로,
**워크플로를 있는 lane 에 맞춘다.** 반대로 하면 안 된다.

| 템플릿 | 정의하는 lane |
|---|---|
| `testflight-wizard/templates/Fastfile.ios.template` | `deploy` |
| `playstore-wizard/templates/Fastfile.playstore.template` | `build_aab` · `deploy_internal` · `promote_internal_to_production` · `validate` |

실사고: iOS 테스트 빌드가 없는 `upload_testflight` 를 불러 **한 번도 TestFlight 에 올라간
적이 없었다.** IPA 는 정상 생성되고 **마지막 업로드 한 스텝에서만** 죽어서 오래 안 보였다.
배포 경로는 맞는 lane 을 불러 멀쩡했고 **테스트 경로만** 틀렸는데, 그 경로를 끝까지
밟아본 사람이 없었다. 같은 종류를 찾아보니 Android 쪽에도 둘 더 있었다(`fastlane build`).

직접 만든 Fastfile 에만 있는 lane 을 쓰려면 **있는지 확인하고 부른다.**

```bash
if [ -f "android/fastlane/Fastfile" ] \
   && grep -qE '^[[:space:]]*lane[[:space:]]*:build([[:space:]]|$)' android/fastlane/Fastfile; then
  ( cd android && bundle exec fastlane build --verbose )   # 서브셸 — cd 가 새면 뒤가 엉킨다
else
  flutter build apk --release
fi
```

> **🔴 테스트 빌드는 `DEPLOY_MODE` 를 반드시 못 박는다.** iOS `deploy` lane 은 이 값에 따라
> **심사 자동 제출(`submit_for_review`)까지** 간다. 기본값에 기대고 있으면 Fastfile 기본값이
> 바뀌는 순간 테스트 빌드가 앱 심사에 올라간다 — 되돌릴 수 없는 종류의 사고다.
> 테스트 경로는 `export DEPLOY_MODE="store_only"` 를 명시한다.

### ⚠️ 빌드 플래그는 두 층이 함께 가야 한다 (#603 — agent 필독)

앱의 개발 스위치는 **두 층**에 있고, **한 층만 맞아도 빌드는 통과한다.**

| 층 | 어디에 | 위조 |
|---|---|:-:|
| 런타임 | `.env` (dotenv) | 가능 (Secret 주입) |
| 컴파일타임 | `--dart-define` | **불가** (바이너리에 박힌다) |

실사고: `.env` 에 개발 플래그가 찍히고 로그는 `✅ 적용 완료` 를 냈는데, **설치해 보면
디버깅 도구가 없었다.** 릴리스 빌드라 컴파일타임 게이트가 닫혀 있었고, 레포 전체에
`dart-define` 이 한 군데도 없었다 — 즉 **한 번도 켜진 적이 없었다.** 로그만 봐서는 알 수 없다.

**`.github/scripts/apply_build_profile.py` 가 한 곳에서 두 층을 모두 정한다.**

```yaml
- name: Apply build profile (test)
  id: build_profile
  run: python3 .github/scripts/apply_build_profile.py test .env

- name: Build
  # 🔴 여기에 dart-define 을 직접 적지 않는다. 적는 순간 다시 두 곳이 된다.
  run: flutter build apk --release ${{ steps.build_profile.outputs.build_flags }}
```

- **설정(`.github/config/build-profile.json`)이 없으면 아무 일도 하지 않는다.**
  남의 저장소에 설치되는 템플릿이므로 이것이 기본값이다. 예시는 `.example` 파일.
- `release` 라는 이름의 프로파일에는 **검증이 걸린다** — 개발 키가 켜진 채로, QA 토큰이
  남은 채로, 테스트 전용 dart-define 이 섞인 채로 배포 빌드가 나가면 **빌드를 세운다.**
- **`.env` 생성과 빌드가 다른 job 이면** 프로파일 결과를 `outputs.build_flags` 로 넘긴다
  (`IOS-TEST-TESTFLIGHT` · `IOS-TESTFLIGHT` 가 그렇다). 같은 job 이면 `steps.` 로 읽는다.
- **fastlane lane 으로 빌드하는 경로에는 플래그를 넘길 자리가 없다.** 플래그가 있는데
  그 경로를 타면 **빌드를 세운다** — 조용히 빠뜨리면 이 스텝이 고치려던 사고가 다시 난다.
- 플레이버 이름은 **`APP_FLAVOR`** 처럼 앱 이름이 안 들어가는 중립적인 것을 쓴다.
  Flutter 표준 `FLUTTER_APP_FLAVOR` 는 예약어라 `--dart-define` 으로 못 넣는다
  (`--flavor` 전용이며, 그건 Gradle productFlavors·Xcode scheme 을 요구한다).

적용된 워크플로우: `ANDROID-TEST-APK`·`IOS-TEST-TESTFLIGHT`(test) ·
`ANDROID-PLAYSTORE-CICD`·`ANDROID-FIREBASE-CICD`·`ANDROID-SELFHOSTED-CICD`·`IOS-TESTFLIGHT`(release)

### ⚠️ 워크플로우는 `permissions:` 를 반드시 선언한다 (#595 — agent 필독)

**선언하지 않으면 레포 기본값을 따르는데, 그 기본값은 레포마다 다르고 나중에 바뀐다.**

| 기본값 | 선언 안 했을 때 |
|---|---|
| `read` (GitHub 신규 레포 기본값) | 댓글을 다는 워크플로우가 **그 스텝에서 죽는다** |
| `write` | 읽기만 하면 되는 배포 워크플로우가 **과한 권한**을 갖는다 |

실사고: `@projectops apk build` 테스트 빌드가 항상 실패했다. 트리거 워크플로우에는 블록이
있어 **트리거까지는 성공**했고, 정작 빌드가 진행 상황 댓글을 다는 순간 막혔다.
겉보기에는 "빌드가 도는데 결과가 없다"로 보여 원인을 찾는 데 오래 걸렸다.

```
RequestError [HttpError]: Resource not accessible by integration
```

| 하는 일 | 적을 것 |
|---|---|
| 이슈·PR에 댓글·라벨 | `contents: read` + `issues: write` + `pull-requests: write` |
| PR에만 댓글 | `contents: read` + `pull-requests: write` |
| 체크아웃·빌드·배포만 | `contents: read` |
| 커밋을 푸시 | `contents: write` |
| 별도 PAT로만 API 호출 | `contents: read` (GITHUB_TOKEN 은 안 쓴다) |

위치는 최상위 `on:` 블록 **바로 뒤**다 (job 단위로 적어도 된다).
회귀 방지: `.github/scripts/test/test_workflow_permissions.py` 가 **모든** 워크플로우를 검사한다.

> **⚠️ `.yaml` 만 훑지 말 것.** 이 저장소에는 `.yml` 확장자 워크플로우도 5개 있다
> (`NEXUS-*` · `GITHUB-PACKAGES-PUBLISH` · `TEMPLATE-UTIL-VERSION-SYNC`).
> 실제로 `*.yaml` 만 본 첫 점검에서 한 건을 놓쳤고 테스트가 잡았다.

> **⚠️ `repository_dispatch` 는 기본 브랜치의 워크플로 정의로 돈다.** 이 트리거를 쓰는
> 워크플로우(`ANDROID-TEST-APK` · `IOS-TEST-TESTFLIGHT` · `APP-BUILD-TRIGGER`)를 develop
> 에서 고치고 테스트 빌드를 다시 걸면 **여전히 옛 정의가 실행된다.** 수정이 안 먹은 것처럼
> 보여 원인을 엉뚱한 데서 찾게 되므로, 반드시 기본 브랜치에 반영된 뒤에 확인한다.

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
| `PROJECT-FLUTTER-IOS-ASC-STATUS` | App Store Connect 버전 상태, 최근 빌드 번호 조회 (수동 실행, 조회 전용, #651) | 기본 |
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
- **새 타입을 추가하면 두 선언에 항목을 반드시 넣는다** — `project-types` 폴더(`server-deploy/`·`publish/<target>/`)와 어긋나지 않게 맞춘다. 미선언 타입은 보수적으로 전체 허용(질문 유지).

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

> **배포 워크플로우를 새로 추가하면 `src/core/branch-sub.js` 의 `DEPLOY_TRIGGER_WORKFLOWS` 에 파일 이름을 넣는다 (#1114).** 푸시되면 배포가 도는 워크플로(스토어·서버·패키지 publish·Vercel)만 해당한다.
> `deploy_trigger_branch` 를 쓰는 레포에서 이 표에 없는 파일은 기본 브랜치에서 배포가 돌아, 배포 브랜치를 나눴는데도 배포가 엉뚱한 곳에서 도는 사고가 된다. 버전 올림·README 버전·릴리스 노트·이슈 닫기 같은 공통 워크플로는 넣지 않는다(기본 브랜치를 따른다).
>
> **CI 사용 시간 절약 옵션(`ci_minutes_saver`, #1114)은 `src/core/ci-minutes-sub.js` 의 파일 이름 표로 바꾼다.** 새 CI 워크플로를 추가하면 표에 넣을지 정한다. 변환은 패턴이 정확히 맞을 때만 걸리므로, 표에 있는 워크플로의 `on:` 블록이나 `ENABLE_IOS` 줄 모양을 바꾸면 표의 변환도 함께 맞춘다(안 맞추면 옵션이 조용히 아무것도 안 한다).
>
> 서버 배포 워크플로우(SIMPLE/NONSTOP-*/PR-PREVIEW)는 `server-deploy/`로 묶여 **`deploy=docker-ssh`일 때만 포함**된다(`vercel`/`none`이면 폴더째 제외). publish 워크플로우는 `<type>/publish/<target>/`에 있고 **선택된 publish 타겟 집합**으로 복사가 결정된다(타입은 파일 위치일 뿐 게이트 아님).
>
> **확장 규칙(agent 필독)**: 새 "서버 배포" 워크플로우는 **그 타입의 `<type>/server-deploy/`** 에 파일만 넣는다(deploy≠docker-ssh면 자동 제외). 현재 `server-deploy/`를 가진 타입은 `spring`·`python` 두 개다. **타입 폴더 직하위에 두면 `--deploy none`에서도 복사되므로 절대 그렇게 두지 않는다** (실제로 python이 이 함정에 빠져 #521에서 교정됨). 새 publish 타겟은 `<type>/publish/<target>/`에 넣고 마법사 질문 목록에 값을 추가한다. 타입 비종속 배포 타겟(Vercel 등)은 `common/deploy/<target>/`에 넣는다.
>
> **⚠️ 워크플로우를 리네임/삭제할 때 (agent 필독, #470)**: 구 이름을 `src/core/migrations/registry.js`에 반드시 추가한다 — 마법사 업데이트가 기존 통합 레포의 구 파일을 자동 무해화(.bak)하는 유일한 경로다(레거시 마이그레이션은 전부 이 레지스트리 한 곳에서 관리). tier는 `safe`(순수 리네임 — 공존 시 중복 실행 실해) / `confirm`(배포 파이프라인일 수 있음 — 자동 조치 없이 안내만) 중 실해 기준으로 고른다. 레지스트리에 현행 배포 세트의 이름을 넣으면 살아 있는 워크플로우를 무해화하므로, 넣기 전에 현행 템플릿에 같은 이름이 없는지 확인한다. 구 파일에 사용자 커스텀 설정이 들어있을 수 있으면 registry 항목에 `settingsExtractor`를 지정해 무해화 직전 version.yml로 자동 이관한다 (`rules/settings-extractors.js`, #478 이슈 헬퍼가 모범 사례).
> 참고: **타입 선택 해제로 남는 고아 워크플로우**는 registry가 아니라 `src/core/orphan-workflows.js`가 동적 감지한다(#487) — registry는 리네임·폐기 전용, 고아 정리는 템플릿 인벤토리 대조(정확한 파일명 일치) 방식이다. 대화형은 확인 후 .bak 무해화, 비대화형은 안내만 출력한다.
>
> **⚠️ `common/` 아래에 조건부 폴더를 새로 만들 때 (agent 필독, #567·#851)**: `src/core/workflow-groups.js`의 `commonOptionalGroups`에 한 줄을 넣는다. 복사 게이트(`copy/workflows.js`)와 고아 감지(`orphan-workflows.js`)가 **같은 표**를 읽는다. 예전에는 두 곳을 따로 고쳐야 했고, 켜는 쪽만 만들어 **끈 뒤에도 파일이 남아 계속 실행되는** 일이 `secret-backup`·`deploy/<target>`에서 실제로 있었다.
>
> **`.github/util/` 모듈 안의 파일을 리네임/폐기할 때도 동일하다 (#500)**: registry에 `category: "util-file"`(tier safe, 정확 경로)로 구 파일을 등록한다 — util 복사(`src/core/copy/util.js`)는 overlay라 구 파일을 지우지 않으므로 registry가 유일한 정리 경로다. 현행 템플릿 파일과 같은 경로를 넣지 않는다.
>
> **⚠️ 브랜치 규칙(`YYYYMMDD_#번호_제목`)에 의존하는 워크플로우를 추가할 때 (agent 필독, #478)**:
> `.github/scripts/issue_helper.py`의 `GUIDE_LINES`에 (파일명, 안내 문구)를 추가하고,
> 워크플로우 헤더에 "⚠️ 브랜치 규칙 의존" 주석 블록을 넣는다. 상세: `docs/BRANCH-CONVENTION.md`

#### 공통 — 배포 타겟 / Secret 백업
| 파일명 | 기능 | 위치 | 조건 |
|--------|------|------|------|
| `PROJECT-COMMON-VERCEL-DEPLOY` | Vercel 프로덕션 배포 (React/Next 등) | common/deploy/vercel/ | `--deploy vercel` |
| `PROJECT-COMMON-SECRET-FILE-UPLOAD` | GitHub Secret → 서버(SSH) 업로드 | common/secret-backup/ | `--secret-backup` |
| `PROJECT-COMMON-AI-PR-SUMMARY` | 작업 PR에 변경 요약 댓글 | common/pr-summary/ | PR 댓글 질문에서 선택 |

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

## 이슈/PR 템플릿

**이슈 템플릿**: `bug_report.md` / `feature_request.md` / `design_request.md` / `qa_request.md`

**이슈 라벨**: 영문 표준 `priority: urgent, documentation, status: todo, status: in progress, status: needs review, status: feedback, status: done, status: on hold, status: cancelled` (기존 한글: `긴급, 문서, 작업전, 작업중, 담당자확인, 피드백, 작업완료, 보류, 취소`)

## 기여 가이드라인 핵심

> 상세 내용: `CONTRIBUTING.md`, `docs/WORKFLOW-COMMENT-GUIDELINES.md`

### 워크플로우 추가 시
- 공통 워크플로우: `project-types/common/` (원본) + `.github/workflows/` 루트 (복사본) **동일 유지**
- 타입별 워크플로우: `project-types/[type]/`만
- 필수 요소: `workflow_dispatch`, `concurrency`, `[skip ci]`
