🗒️ 설명
---

`docs/` 루트 문서 17종을 실제 워크플로우·스크립트·마법사와 1:1 대조한 결과, **문서만 보고 따라 하면 실패하는 오류**가 다수 확인되었습니다. 문서 구조 자체는 정상이나, 오래 갱신되지 않은 문서에 사실관계 오류가 누적된 상태입니다.

가장 큰 문제는 **Flutter 배포 Secret 이름이 문서 4종 전부에서 틀린 것**입니다. 워크플로우와 마법사(`.py`/`.js`/`.html`)는 서로 일치하는데 문서만 다른 이름을 안내하고 있어, 신규 사용자가 문서대로 Secret을 등록하면 iOS/Android 배포가 100% 실패합니다.

추가로 문서가 아니라 **구현 쪽 결함 2건**도 함께 발견되었습니다.

- Python 타입의 서버 배포 워크플로우가 배포 축(`deploy`) 게이트 밖에 놓여 있어, `--deploy none`을 선택해도 배포 워크플로우가 복사됩니다.
- Projects 동기화 워크플로우의 `PROJECT_URL` 기본값이 특정 개인 프로젝트 보드로 활성화된 채 배포되고 있습니다.

🔄 재현 방법
---

**A. Flutter Secret 이름 (가장 치명적)**

1. `docs/FLUTTER-CICD-OVERVIEW.md`의 "2단계: GitHub Secrets 설정" 항목을 그대로 따라 Secret을 등록한다
2. Flutter 프로젝트에 iOS TestFlight 또는 Android Play Store 워크플로우를 설치하고 main에 푸시한다
3. 워크플로우가 참조하는 Secret 이름과 등록한 이름이 달라 인증서/키스토어 단계에서 실패한다

**B. 존재하지 않는 명령어**

1. `docs/TROUBLESHOOTING.md`의 "버전 파일 상태 진단" 항목대로 `version_manager.sh sync --dry-run`을 실행한다
2. 스크립트가 `--dry-run` 인자를 인식하지 않고 무시하므로, 미리보기가 아니라 **실제 동기화가 수행된다**

**C. 체인지로그 흐름 오해**

1. `docs/CHANGELOG-AUTOMATION.md`의 자동화 흐름도대로 develop에 푸시한다
2. 문서는 "develop 푸시 → 버전 증가 → PR 자동 생성"이라고 안내하지만, 실제로는 아무 일도 일어나지 않는다
3. 릴리스 PR을 수동으로 만들어야 함을 문서에서 알 수 없다

**D. 구현 결함 1 (Python 배포 축)**

1. Python 타입 프로젝트에 배포 없음(`--deploy none`)으로 템플릿을 통합한다
2. 서버 배포 워크플로우 2종이 그대로 설치된다

**E. 구현 결함 2 (Projects URL)**

1. 템플릿을 통합한 뒤 이슈에 상태 라벨을 추가한다
2. 동기화 대상이 사용자 본인의 보드가 아니라 템플릿에 하드코딩된 개인 보드로 향한다

📸 참고 자료
---

**1. Flutter Secret 이름 오기 (문서 4종 공통)**

문서가 안내하는 이름 → 실제 워크플로우·마법사가 쓰는 이름

| 문서 표기 | 실제 |
|---|---|
| `IOS_CERTIFICATE_BASE64` | `APPLE_CERTIFICATE_BASE64` |
| `IOS_CERTIFICATE_PASSWORD` | `APPLE_CERTIFICATE_PASSWORD` |
| `IOS_PROVISIONING_PROFILE_BASE64` | `APPLE_PROVISIONING_PROFILE_BASE64` |
| `APP_STORE_CONNECT_API_ISSUER_ID` | `APP_STORE_CONNECT_ISSUER_ID` |
| `APP_STORE_CONNECT_API_KEY_CONTENT` | `APP_STORE_CONNECT_API_KEY_BASE64` |
| `ANDROID_KEYSTORE_BASE64` | `RELEASE_KEYSTORE_BASE64` |
| `ANDROID_KEYSTORE_PASSWORD` | `RELEASE_KEYSTORE_PASSWORD` |
| `ANDROID_KEY_ALIAS` | `RELEASE_KEY_ALIAS` |
| `ANDROID_KEY_PASSWORD` | `RELEASE_KEY_PASSWORD` |
| `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` | `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_BASE64` |

- 해당 문서: `docs/FLUTTER-CICD-OVERVIEW.md`, `docs/FLUTTER-TESTFLIGHT-WIZARD.md`, `docs/FLUTTER-PLAYSTORE-WIZARD.md`, `docs/FLUTTER-TEST-BUILD-TRIGGER.md`
- 누락된 Secret: `IOS_BUNDLE_ID`, `IOS_PROVISIONING_PROFILE_NAME`, `APPLE_TEAM_ID`, `SECRETS_XCCONFIG`, `ENV_FILE`
- `docs/FLUTTER-TESTFLIGHT-WIZARD.md`는 같은 문서 안에서 `APP_STORE_CONNECT_ISSUER_ID`와 `APP_STORE_CONNECT_API_ISSUER_ID`를 혼용하고 있습니다

**2. 존재하지 않는 명령어 2건**

| 문서 | 안내 | 실제 |
|---|---|---|
| `docs/TROUBLESHOOTING.md` | `version_manager.sh sync --dry-run` | `--dry-run` 미지원, 실제 동기화가 실행됨 |
| `docs/CHANGELOG-AUTOMATION.md` | `changelog_manager.py validate` | 지원 서브커맨드는 `update-from-summary`, `generate-md`, `export` 3종뿐 |

**3. 동작 설명이 실제와 다른 항목**

| 문서 | 문서 주장 | 실제 |
|---|---|---|
| `docs/CHANGELOG-AUTOMATION.md` 자동화 흐름 | develop 푸시가 버전 증가와 PR 자동 생성을 유발 | VERSION-CONTROL은 main 푸시에만 동작, 릴리스 PR을 자동 생성하는 워크플로우는 없음 |
| `docs/CHANGELOG-AUTOMATION.md` 트리거 | `pull_request` + `[opened, synchronize]` | `pull_request_target` + `[opened]` (재푸시로 재실행되지 않음) |
| `docs/CHANGELOG-AUTOMATION.md` 무한루프 설명 | develop을 푸시 트리거로 쓰는 워크플로우가 없음 | TEMPLATE-CI, TEMPLATE-UTIL-VERSION-SYNC, FLUTTER-CI, REACT-CI, NEXUS-CI 5종이 develop 푸시 트리거 |
| `docs/CHANGELOG-AUTOMATION.md` PR 제목 | CodeRabbit이 `Deploy 날짜-버전 : 요약` 형식으로 변경 | 워크플로우가 `🚀 Deploy 날짜-버전` 형식으로 변경, 요약 부분 없음 |
| `docs/VERSION-CONTROL.md` paths-ignore | `CHANGELOG.md`, `README.md` | `CHANGELOG.md`, `CHANGELOG.json`, `version.yml` (README는 무시 대상 아님) |
| `docs/PR-PREVIEW.md` 환경변수 | `SUH_LAB_BASE_DOMAIN`, `EXTERNAL_PORT` | 두 이름 모두 존재하지 않음. 실제는 `PREVIEW_DOMAIN_SUFFIX`, `PREVIEW_PORT` |
| `docs/PR-PREVIEW.md` 필수 Secret | SSH 비밀번호 방식만 기재 | `SSH_KEY`(키 인증), `SSH_PORT` 누락. 아키텍처 설명도 Synology 전용으로 고정 |
| `docs/TROUBLESHOOTING.md` SSH | 방화벽 22번 포트 허용 | 템플릿 기본 SSH 포트는 2022 |
| `docs/TROUBLESHOOTING.md` 체인지로그 | CodeRabbit 설치 여부만 확인 | provider 사다리 도입 이후 확인 항목이 달라짐 |
| `docs/ISSUE-AUTOMATION.md` | `issue-label.yml` | `issue-labels.yml` (오타) |
| `docs/SKILLS.md` | "세 그룹으로 나뉩니다" | 실제 섹션은 4그룹 |

**4. 누락 및 낡은 목록**

| 문서 | 내용 |
|---|---|
| `docs/WORKFLOW-COMMENT-GUIDELINES.md` 파일별 적용 현황 | 이미 사라진 SYNOLOGY 시대 파일명 4종을 여전히 기재. 루트 12종 중 6종만, common 10종 중 4종만, flutter 8종 중 5종만 수록. python, node 섹션 자체가 없음 |
| `docs/FLUTTER-CICD-OVERVIEW.md` | Firebase 마법사와 Firebase 배포 워크플로우가 통째로 빠짐. FLUTTER-CI도 누락. 마법사 템플릿 파일명 오기. 자체 서버 배포를 여전히 Synology 전용으로 표기 |
| Firebase 마법사 전용 문서 | Play Store, TestFlight는 전용 문서가 있으나 Firebase만 없음 |
| `docs/NPX-WIZARD.md` | 마법사 첫 질문이 프로젝트 성격 기반으로 바뀐 것이 미반영. 마이그레이션 레지스트리 수치가 낡았고 신규 분류 2종 누락. 고아 워크플로우 정리, 마이그레이션 기록 기능 미문서화. 배포 축 스킵 조건이 basic 단독으로만 서술 |
| Python 타입 문서 | 워크플로우 3종이 존재하나 문서에 타입별 설명이 없음 |
| `README.md` | docs 6종이 어디에서도 링크되지 않음 |
| `docs/` | 문서 인덱스가 없어 README에만 의존 |

**5. 링크 및 잔재**

- `.github/util/common/projects-sync-wizard/README.md`의 상대 경로 2건이 깨져 있음 (상위 디렉터리 깊이 오류)
- `pr_body.md`가 저장소 루트에 추적 상태로 남아 있으며, 템플릿 제외 목록 어디에도 등록되어 있지 않음
- `docs/suh-template/` 빈 폴더 잔재

**6. 구현 결함 2건**

| 항목 | 내용 |
|---|---|
| Python 서버 배포 워크플로우 위치 | 서버 배포 워크플로우는 `server-deploy/` 하위에 두어야 배포 축 선택이 적용되는데, Python 타입의 배포 워크플로우 2종은 타입 폴더 바로 아래에 있어 배포 없음을 선택해도 항상 복사됨 |
| Projects 동기화 URL | `PROJECT_URL`이 주석 처리되지 않은 채 특정 개인 프로젝트 보드 주소로 활성화되어 배포됨. 문서는 "주석을 해제하고 입력하세요"라고 안내하고 있어 설명과도 어긋남 |

✅ 예상 동작
---

- 문서에 적힌 Secret 이름, 환경변수 이름, 명령어가 실제 워크플로우·스크립트와 정확히 일치해야 합니다
- 문서에 적힌 자동화 흐름과 트리거 조건이 실제 워크플로우 정의와 일치해야 합니다
- 문서에 없는 기능(Firebase 마법사, Python 타입, 마법사 신규 질문 흐름)이 문서에 반영되어야 합니다
- 배포 없음을 선택한 프로젝트에는 서버 배포 워크플로우가 설치되지 않아야 합니다
- Projects 동기화 대상은 사용자가 직접 지정해야 하며, 템플릿 기본값이 특정 개인 보드를 가리켜서는 안 됩니다

⚙️ 환경 정보
---

- **대상**: `Cassiiopeia/projectops` (템플릿 저장소 본체)
- **확인 버전**: v4.2.33 (main 기준, docs 내용은 develop과 동일)
- **확인 방법**: docs 루트 17종 전체를 워크플로우 YAML, 스크립트, 마법사 소스와 대조

🙋‍♂️ 담당자
---

- **백엔드**: Cassiiopeia
- **프론트엔드**: -
- **디자인**: -
