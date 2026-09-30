# 앱 빌드 번호와 iOS 버전 이름 재설계

- 이슈: #643 (출시 후 iOS 테스트 빌드가 닫힌 버전 이름을 써서 TestFlight 업로드가 거부됨)
- 관련: #209 (테스트 빌드 버전 `0.0.0` 하드코딩), #601 (iOS 테스트 빌드 lane), TEAM-ROMROM/RomRom-FE#735
- 작성일: 2026-09-30
- 상태: 설계 검토 대기

---

## 1. 배경

### 1.1 이슈가 보고한 문제

앱이 App Store에서 승인되면 그 버전의 prerelease train이 닫힌다. iOS 테스트 빌드는 `version.yml`의 현재 버전을 그대로 쓰므로, 출시 직후부터 다음 릴리스로 버전이 올라가기 전까지 모든 테스트 빌드가 12~18분 빌드를 마친 뒤 업로드 단계에서 거부된다 (`ITMS-90186 Invalid Pre-Release Train`). #209의 수정은 문제를 없앤 것이 아니라 옮겼다.

파생 결함:

| # | 결함 |
|---|---|
| 1 | 실패 봇 댓글에 Apple 거부 사유가 없다 |
| 2 | 봇 댓글의 커밋이 빌드된 커밋이 아니라 `github.sha`(default 브랜치 끝)다 |
| 3 | 테스트 빌드 번호(이슈 번호 기반)와 릴리스 빌드 번호(`version_code`)가 서로 다른 체계다 |

### 1.2 조사로 새로 드러난 사실

- **이슈대로 버전 이름만 고치면 결함 3이 실제로 터진다.** 테스트 빌드가 아직 릴리스되지 않은 다음 패치(예: 2.1.3)에 45106 같은 큰 번호를 먼저 올리면, 뒤따르는 릴리스 2.1.3의 `version_code`(215)는 같은 train 안에서 더 작아 거부된다. 버전 이름과 빌드 번호는 한 묶음으로 고쳐야 한다.
- **현재 테스트 빌드 번호 계산(댓글 세기)은 그 자체로 구멍이 많다.** `PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml:365-434`
  - 한 이슈에서 100번째 빌드는 `451`+`100`=`451100`이 되어 이슈 4511의 첫 빌드와 겹친다
  - 댓글을 첫 100개만 읽는다 (`per_page: 100`, 페이지네이션 없음). 이후 번호가 멈춰 같은 번호가 반복된다
  - 빌드 명령 댓글을 지우면 횟수가 줄어 쓴 번호가 다시 나온다
  - `@projectops`와 `build`와 `app`이 부분 문자열로만 들어가도 센다 ("happy", "application" 등). SUH-ISSUE-HELPER 가이드 댓글과 트리거 자신의 실패 댓글도 센다
  - 플랫폼별로 따로 세서 `ios, ios, app, apk` 순서면 Android 번호가 내려간다
  - 이슈 번호 순서대로 번호가 커지므로, 작은 번호의 이슈를 나중에 빌드하면 같은 train 안에서 역전된다
- **iOS 두 워크플로 모두 서명(build job)과 업로드(deploy job)가 다른 job에 있다.** 번호를 업로드 직전에 정하거나 거부 시 재시도하려면 한 job에 있어야 한다.
- **릴리스의 심사 제출은 `ENV["BUILD_NUMBER"]`로 제출할 빌드를 고른다** (`Fastfile.ios.template:117`). 번호가 바뀌면 이 값도 최종 번호여야 한다.
- **사용자 레포의 Fastfile과 ExportOptions.plist는 마법사가 한 번 복사하고 끝이다.** `npx projectops` 업데이트가 덮어쓰지 않는다. 워크플로 변경은 이미 깔린 옛 Fastfile로도 동작해야 한다.

---

## 2. 목표와 비목표

### 목표

1. iOS 테스트 빌드가 닫힌 버전 이름을 절대 쓰지 않는다. 닫혔으면 빌드 시작 직후 알리고 다음 패치로 빌드한다.
2. iOS 빌드 번호가 테스트, 릴리스, 동시 빌드, 순서와 무관하게 거부되지 않는다.
3. 번호 때문에 거부되면 사람 개입 없이 스스로 복구한다.
4. 실패 시 Apple이 준 사유가 댓글(테스트)이나 job 요약(릴리스)에 한 줄로 보인다.
5. 표시되는 커밋이 실제로 빌드된 커밋이다.
6. Android 테스트 빌드 번호의 겹침 구멍을 없앤다.
7. 번호 규칙과 오류 해석이 각각 한 곳에만 있어, 새 스토어나 새 오류 코드를 한 군데만 고쳐 붙일 수 있다.

### 비목표

- Android 릴리스(Play Store, Firebase CICD, 셀프호스트) 번호 체계 변경. 계속 `version_code` 또는 pubspec을 쓴다.
- 테스트 폰에서 정식 앱으로 덮어 설치하는 경로 보장. 테스트 빌드는 지우고 다시 설치하는 것을 전제로 한다.
- 번호만 보고 이슈나 시각을 알아보는 것. 추적 정보는 릴리스 노트와 댓글에 둔다.
- 13절의 분리 이슈들.

---

## 3. 전제가 되는 외부 규칙

| 규칙 | 확신도 | 근거 |
|---|---|---|
| iOS 빌드 번호는 정수 최대 3개를 점으로 이은 형식, 전체 18자 이내 | 높음 | [CFBundleVersion](https://developer.apple.com/documentation/bundleresources/information-property-list/cfbundleversion), [TN2420](https://developer.apple.com/library/archive/technotes/tn2420/_index.html) |
| 같은 버전(train) 안에서 빌드 번호는 겹치면 안 되고 직전 업로드보다 커야 함 | 높음 | TN2420 |
| macOS를 함께 내는 앱은 버전이 달라도 번호 비교에 걸린 사례가 있음. 앱 전체에서 항상 커지게 하는 것이 안전 | 중간 | [Apple 포럼 759988](https://developer.apple.com/forums/thread/759988) |
| 버전은 승인(`PENDING_DEVELOPER_RELEASE`) 순간 닫히고, 이후 개발자 반려로도 다시 열리지 않음 | 중간 | [Apple 포럼 696344](https://developer.apple.com/forums/thread/696344), [821386](https://developer.apple.com/forums/thread/821386) |
| 앱 확장(.appex)은 본체와 버전, 빌드 번호가 같아야 함 | 높음 | TN2420 |
| ExportOptions `manageAppVersionAndBuildNumber` 기본값은 YES이며 Xcode가 번호를 바꿀 수 있음 | 높음 | [Apple 포럼 690647](https://developer.apple.com/forums/thread/690647) |
| ASC `GET /v1/builds` 등은 limit 최대 200. `sort=version`이 숫자순인지 문서에 없음 | 높음 | [ASC API](https://developer.apple.com/tutorials/data/documentation/appstoreconnectapi/get-v1-builds.json) |
| ASC JWT: ES256, `aud: appstoreconnect-v1`, 수명 20분 이하 | 높음 | [ASC 토큰](https://developer.apple.com/tutorials/data/documentation/appstoreconnectapi/generating-tokens-for-api-requests.json) |
| API 키 Developer 역할이 빌드와 버전 목록을 읽을 수 있는지는 미확인 | 낮음 | 조사 결과 |
| Play `versionCode` 최대 2,100,000,000 | 높음 | [Android 버전 관리](https://developer.android.com/studio/publish/versioning) |
| Firebase App Distribution은 번호 고유성을 요구하지 않고, 같은 번호면 기존 릴리스를 갱신함 | 중간 | [UploadReleaseResult](https://firebase.google.com/docs/reference/app-distribution/rest/v1/UploadReleaseResult) |
| `github.run_number`는 재실행 시 유지되고, 워크플로 파일 이름이 바뀌면 1부터 다시 시작 | 중간 | GitHub 동작 |

### Apple 업로드 거부 메시지 (분류 기준)

| 분류 | 코드와 대표 문구 |
|---|---|
| 번호 중복 | `ITMS-90189 Redundant Binary Upload. You've already uploaded a build with build number '<n>' for version number '<v>'`, 신형 `ENTITY_ERROR.ATTRIBUTE.INVALID.DUPLICATE`, `-19232` |
| 번호가 작음 | `90061 ... CFBundleVersion [<n>] ... must contain a higher version than that of the previously uploaded version [<x>]`, 신형 `The bundle version must be higher than the previously uploaded version: '<x>'` |
| train 닫힘 | `ITMS-90186 Invalid Pre-Release Train. The train version '<v>' is closed for new build submissions`, `ITMS-90062 ... must contain a higher version than that of the previously approved version [<v>]`, `ITMS-90478 ... a later version has been closed for new build submissions` |

---

## 4. 설계 결정

### 4.1 빌드 번호: 시각 기반 번호 + 하한 두 개

```
빌드 번호 = max( 지금 시각(UTC) - 2024-01-01 00:00:00 UTC 를 초로,
                 ASC에서 최근 올라간 번호 중 최대 + 1        (조회되면),
                 Apple 거부 메시지가 요구한 번호 + 1          (재시도일 때) )
```

- 기준 시각 상수 `EPOCH_2024 = 1704067200`.
- 예: 2026-09-30 14:04:00 KST(05:04 UTC)는 `86677440`.
- 2026년 기준 약 8,700만. Android 상한(21억)에는 2090년에 닿는다. iOS 18자 제한과도 거리가 멀다.
- 지금 쓰는 번호(iOS 45105, `version_code` 474)보다 크므로 전환할 때 역전이 없다.
- **시간은 거꾸로 가지 않으므로 나중에 뽑은 번호가 항상 더 크다.** 동시 빌드에서 거부된 쪽이 재시도로 번호를 새로 뽑으면, 그 번호는 먼저 업로드된 빌드가 번호를 뽑은 시각보다 뒤에 뽑혔으므로 반드시 더 크다. 번호를 정하는 데 외부 API가 필요 없다.
- ASC 하한은 예전에 날짜형(예: `2026093001`, 20억대) 번호를 쓴 앱을 위한 것이다. 조회에 실패하면 빠지고, 세 번째 하한이 거부 메시지로 복구한다.
- 같은 초에 두 빌드가 번호를 뽑아 겹치면 Apple이 중복으로 거부하고, 재시도에서 새 번호로 풀린다.

**적용 범위**

| 빌드 | 번호 |
|---|---|
| iOS 테스트 (TestFlight) | 위 규칙 |
| iOS 릴리스 (TestFlight, 심사 제출) | 위 규칙 |
| Android 테스트 (Firebase) | 위 규칙 (ASC 하한 없음, 재시도 없음) |
| Android 릴리스 (Play, Firebase CICD, 셀프호스트) | 변경 없음 (`version_code` 또는 pubspec) |

`version.yml`에는 어떤 번호도 다시 쓰지 않는다. `version_code`는 Android 릴리스 전용이 된다.

**되돌릴 수 없음**: iOS 번호가 약 8,700만으로 한 번 뛰면 이후 작은 번호 체계로 돌아갈 수 없다(같은 train 안, 그리고 macOS 동시 출시 앱은 train이 달라도). 시각 기반을 계속 쓰는 한 문제가 없지만 `breaking-changes.json`에 경고로 남긴다.

**검토 후 버린 대안**

| 대안 | 버린 이유 |
|---|---|
| 이슈 번호 기반 유지 | 1.2의 겹침, 역전 구멍이 그대로 남는다 |
| ASC 최대값 + 1 | 정렬 기준이 문서에 없고, 방금 올린 빌드가 목록에 뜨는 시점이 정해져 있지 않으며, Developer 역할 키의 읽기 권한이 미확인이다. 번호가 외부 상태에 매인다 |
| 겹칠 때만 보정 | 두 체계에 보정 규칙이 얹혀 추론과 디버깅이 어렵다 |
| 날짜형 번호(`YYMMDDHHmm`) | `2609301404`는 Android 상한(21억)을 넘는다. 연도를 빼면 해가 바뀔 때 작아진다 |
| `run_number` | 파일 이름이 바뀌면 1로 돌아가 겹친다. 재실행 시 같은 번호가 나온다 |

### 4.2 버전 이름: 사전 점검과 사후 복구 두 겹

**사전 점검 (준비 job, ASC 조회)**

- `GET /v1/apps?filter[bundleId]=...` 결과에서 `attributes.bundleId`가 정확히 같은 앱만 쓴다 (접두 일치 방지).
- `GET /v1/apps/{id}/appStoreVersions?filter[platform]=IOS`를 끝까지 페이지 넘겨 읽는다.
- 아래 상태 중 하나인 버전을 "닫힘"으로 본다. 신형 `appVersionState`와 구형 `appStoreState`를 모두 본다.
  - `appVersionState`: `ACCEPTED`, `PENDING_DEVELOPER_RELEASE`, `PENDING_APPLE_RELEASE`, `PROCESSING_FOR_DISTRIBUTION`, `READY_FOR_DISTRIBUTION`, `REPLACED_WITH_NEW_VERSION`
  - `appStoreState`: 위와 같은 의미의 값에 더해 `READY_FOR_SALE`, `PROCESSING_FOR_APP_STORE`, `PREORDER_READY_FOR_SALE`, `DEVELOPER_REMOVED_FROM_SALE`, `REMOVED_FROM_SALE`
  - `DEVELOPER_REJECTED`는 승인 전 철회와 승인 후 반려를 구분할 수 없으므로 "열림"으로 보고 사후 복구에 맡긴다.
- 버전은 정수 최대 3개를 숫자로 비교한다 (`1.20 > 1.3`). 부족한 자리는 0으로 채운다.
- 결정 규칙 (`closed_max` = 닫힌 버전 중 최대):
  - `version.yml` 버전 > `closed_max` 이면 그대로 쓴다.
  - 아니면 `closed_max`의 다음 패치를 쓴다. (`version.yml`이 출시 최대보다 낮게 되돌려진 경우도 여기로 온다.)
- 테스트 빌드: 결정된 버전과 이유를 시작 댓글에 한 줄로 남긴다. 예: `2.1.2는 출시되어 닫힘(READY_FOR_SALE) → 2.1.3으로 빌드`.
- 릴리스 빌드: `version.yml` 버전이 닫혔으면 버전 이름을 바꾸지 않고 즉시 실패한다. 사유와 조치("version.yml 버전을 올리세요")를 남긴다.
- 조회 실패(시크릿 누락, 권한 부족, 네트워크): 경고를 남기고 `version.yml` 버전으로 진행한다. 사후 복구가 받쳐준다.

**사후 복구 (업로드가 train 닫힘으로 거부됐을 때)**

- 거부 메시지에서 닫힌 버전을 읽는다 (`train version '<v>'`, `previously approved version [<v>]`).
- 테스트 빌드: 읽은 버전의 다음 패치로 다시 아카이브해 올린다. 빌드 도중 승인이 난 경우와 사전 점검 실패를 모두 덮는다.
- 릴리스 빌드: 사유와 함께 실패한다.
- `ITMS-90478`(더 높은 버전이 닫힘)은 메시지에 버전이 없으므로, ASC 조회가 되면 `closed_max`를 다시 구하고, 안 되면 사유와 함께 실패한다.

### 4.3 번호를 넣는 시점과 방식

- **시점**: 아카이브 직전. Flutter 빌드(`flutter build ios --no-codesign`)는 임시 번호로 한 번만 한다.
- **방식**: `xcodebuild archive`에 빌드 설정을 명령행으로 넘긴다. 확장 타깃이 어느 변수를 쓰든 맞춰지도록 네 개를 함께 넘긴다.
  - `FLUTTER_BUILD_NUMBER=<번호>` `CURRENT_PROJECT_VERSION=<번호>`
  - `FLUTTER_BUILD_NAME=<버전>` `MARKETING_VERSION=<버전>`
- 아카이브 안의 Info.plist를 직접 고치는 방식은 공식 근거와 성공 사례가 없어 쓰지 않는다.
- **서명 전**: 사용자 레포의 `ios/ExportOptions.plist`를 임시 사본으로 복사하고 사본에 `manageAppVersionAndBuildNumber=false`를 넣어 사용한다. 원본은 건드리지 않는다.
- **서명 후 검증 (업로드 전 필수)**: IPA를 풀어 본체와 모든 내장 번들(`PlugIns/*.appex`, `Watch/*.app`, `AppClips/*.app`)의 `CFBundleVersion`, `CFBundleShortVersionString`을 `plutil`로 읽는다. 하나라도 결정값과 다르면 업로드하지 않고, 어느 번들이 어떤 값인지 적어 실패한다. 빌드 설정 전달이 확장까지 먹히는지는 실측 전 미확인이므로(12절) 이 검증이 안전장치다.

### 4.4 재시도

- 업로드 실패 시 `classify-error`로 분류한다.

| 분류 | 동작 |
|---|---|
| `duplicate` | 번호 다시 계산 → 다시 아카이브 → 검증 → 서명 → 업로드 |
| `too_low` | 요구값을 세 번째 하한으로 넣고 위와 같이 반복 |
| `train_closed` | 테스트: 버전을 다음 패치로 바꿔 반복. 릴리스: 실패 |
| `other` | 재시도 없이 실패 |

- 최대 5회 시도. 모두 실패하면 마지막 사유를 남긴다.
- **이미 올라간 빌드는 다시 올리지 않는다.** 재시도 전에 ASC에서 이번 시도 번호가 이미 있는지 확인한다(`buildUploads`와 `builds`를 `cfBundleVersion`/`version`으로 조회). 있으면 업로드는 성공한 것이므로 뒤 단계(처리 대기, 심사 제출) 실패로 보고 재업로드 없이 실패한다. 로그 문구가 아니라 ASC 상태로 판단하므로 사용자마다 다른 옛 Fastfile에서도 동작한다. ASC 조회가 안 되면 중복 업로드 위험을 피하기 위해 재시도하지 않고 실패한다.
- 재시도는 Flutter 빌드를 다시 하지 않고 아카이브부터 다시 한다.

---

## 5. 구성 요소

모두 `.github/scripts/` 아래 표준 라이브러리 전용 Python이다. 레포 스크립트 표준을 따른다: argparse 서브커맨드, stdout은 JSON 한 줄(`ok`, 데이터, `summary`, `next`), 로그는 stderr, `if __name__ == "__main__": sys.exit(main())`. 워크플로에서 쓰는 값은 `GITHUB_OUTPUT`에도 쓴다(설정되어 있을 때만).

### 5.1 `build_number.py` (플랫폼 무관)

번호 규칙의 유일한 위치.

| 서브커맨드 | 입력 | 출력 |
|---|---|---|
| `next` | `--floor N` (여러 번 가능) | `{"ok": true, "build_number": 86677440, "source": "time"\|"floor", "built_at_utc": "..."}` |
| `describe` | `NUMBER` | 번호를 UTC 시각으로 되돌린 값 (디버깅용) |

- 새 스토어나 플랫폼이 하한을 더 필요로 하면 호출하는 쪽에서 `--floor`를 추가한다. 이 파일의 규칙은 바뀌지 않는다.

### 5.2 `asc_client.py` (App Store Connect 클라이언트)

ASC 호출의 유일한 위치. 13절의 "ASC 상태 조회 수동 워크플로"가 그대로 재사용한다.

- JWT: 헤더 `alg ES256, kid, typ JWT`, 페이로드 `iss, iat, exp(iat+1200 이하), aud`. 서명은 `openssl dgst -sha256 -sign <p8>`로 얻은 DER ECDSA 서명을 64바이트 raw(r‖s)로 바꾼다. macOS 러너의 LibreSSL과 Ubuntu의 OpenSSL 모두 지원한다. 토큰은 만료 전까지 재사용한다.
- 모든 목록 조회는 `links.next`를 따라 끝까지 읽는다. limit 200.
- 번들 ID 조회는 정확 일치만 인정한다.
- 빌드 번호는 첫 번째 정수 성분으로 숫자 비교한다. 점 형식(`45300.1`)이나 비정수도 죽지 않고 첫 성분 또는 제외로 처리한다.
- HTTP는 `urllib.request`, `timeout=30`. 호출 함수는 모듈 수준 함수로 두어 테스트에서 monkeypatch 한다.
- 인증 정보는 환경변수로만 받는다: `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_KEY_PATH`.

### 5.3 `ios_release.py` (iOS 흐름)

| 서브커맨드 | 하는 일 | 주요 출력 |
|---|---|---|
| `precheck-version` | 4.2 사전 점검. `--mode test\|release` | `version`, `changed`, `reason`, `closed_max` |
| `classify-error` | 업로드 로그 파일을 3절 표로 분류 | `kind`, `required_build`, `closed_version`, `reason_line` |
| `archive-upload` | 4.3, 4.4 전체. 아래 참조 | `build_number`, `version`, `attempts`, `reason_line` |

`archive-upload`는 진행 댓글의 단계 구분을 지키기 위해 두 단계로 나눠 호출한다. 두 호출 사이 상태는 작업 디렉터리의 JSON 파일로 넘긴다.

- `archive-upload --phase build`: 첫 시도의 번호 계산, 아카이브, 서명, 검증까지. 끝나면 "IPA 빌드 완료" 댓글을 단다.
- `archive-upload --phase upload`: 업로드와 4.4 재시도. 재시도가 필요하면 아카이브부터 다시 한다.

필요한 입력(환경변수): `APP_ROOT`, `WORKSPACE`(기본 `Runner.xcworkspace`), `SCHEME`(기본 `Runner`), `VERSION`, `MODE`(test/release), 서명 관련 값, ASC 인증 값, fastlane 실행에 넘길 값(`DEPLOY_MODE`, `APP_IDENTIFIER`, `RELEASE_NOTES` 등). `fastlane deploy` 호출 시 `BUILD_NUMBER`와 `APP_VERSION`을 최종값으로 넘긴다. 이는 옛 Fastfile의 `deliver(build_number: ENV["BUILD_NUMBER"])`와도 맞는다.

---

## 6. 워크플로 변경

### 6.1 `PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml`

| 항목 | 지금 | 바뀐 뒤 |
|---|---|---|
| job 구성 | notify-start → prepare-test-build → build-ios-test → deploy-testflight-test | notify-start → prepare-test-build → **build-upload-ios-test** (빌드와 배포 job 통합) |
| 버전 | `version_manager.sh get` 그대로 (L284) | `ios_release.py precheck-version --mode test` 결과 |
| 번호 | payload `build_number` 또는 `run_number` (L289-298) | `archive-upload`가 결정한 최종값. job 출력으로 노출 |
| 커밋 | `github.sha` (L369) | 준비 job이 체크아웃과 pull 후 `git rev-parse HEAD`를 출력. 뒤 job은 브랜치가 아니라 그 SHA로 체크아웃하고 pull 하지 않는다 |
| ASC 키 | deploy job에만 설치 | 준비 job(사전 점검)과 통합 job(업로드) 모두 설치 |
| 번호, 버전 표시 | 모든 댓글이 payload `build_number` 사용 (L169 등 8곳) | 통합 job의 최종 출력 사용. 시작 댓글에는 "빌드 시작 시 결정"으로 표시 |
| 릴리스 노트 | 준비 단계에서 `테스트 빌드 #<번호>`를 미리 기록 (L376) | 번호 없이 이슈, 브랜치, 커밋만 기록. What to Test에서 번호는 TestFlight가 자체 표시 |
| 실패 사유 | 없음 (L1066) | `reason_line`을 실패 댓글에 한 줄로 |
| IPA 경로 | `APP_ROOT` 무시 (L894) | 스크립트가 `APP_ROOT` 기준으로 처리 |
| 셸 | 기본 `bash -e` (pipefail 없음) | 손대는 job에 `defaults.run.shell: bash` |
| 시간 제한 | 없음 (기본 360분) | 통합 job `timeout-minutes: 120`, 준비 job 30 |
| `build-metadata.json` | 기록만 하고 아무도 안 읽음 | 삭제 |

### 6.2 `PROJECT-FLUTTER-IOS-TESTFLIGHT.yaml` (릴리스)

| 항목 | 바뀐 뒤 |
|---|---|
| job 구성 | prepare-build → **build-upload-ios** (빌드와 배포 통합) |
| 버전 | `precheck-version --mode release`. 닫혔으면 준비 단계에서 실패 |
| 번호 | `version_code`가 아니라 `archive-upload` 결과 |
| 심사 제출 | `BUILD_NUMBER`, `APP_VERSION`을 최종값으로 넘김 (`store_prepare`, `store_submit`) |
| 커밋 | 테스트와 같은 SHA 고정 방식 |
| 실패 사유 | 댓글이 없는 워크플로이므로 `$GITHUB_STEP_SUMMARY`와 `::error::`로 |
| 셸, 시간 제한 | 테스트와 같음 |
| 기존 동작 유지 | `DEPLOY_MODE` 입력과 기본값, `whats_new_override` 경로, 릴리스 노트 3800바이트 자르기, downloadPlatform 재시도. 기존 테스트가 리터럴로 검사하는 줄은 그대로 둔다 (11.2) |

### 6.3 `PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml`

- 빌드 번호 계산 스텝(L365-434)을 삭제한다. 댓글 목록 조회도 번호 용도로는 하지 않는다.
- dispatch payload의 `build_number`는 한 minor 동안 빈 문자열로 남긴다. 사용자 레포에서 트리거와 빌드 워크플로 중 한쪽만 갱신된 경우를 위한 호환 필드이며, 새 빌드 워크플로는 이 값을 읽지 않는다.
- 그 외 동작(키워드 해석, 브랜치 해석, 이슈 연결)은 바꾸지 않는다. 권한 검사와 주입 문제는 13절 분리 이슈에서 다룬다.

### 6.4 `PROJECT-FLUTTER-ANDROID-TEST-APK.yaml`

- 번호: payload `build_number` 또는 `run_number`(L306-313) 대신 준비 스텝에서 `build_number.py next`로 계산한다. `workflow_dispatch`도 같다.
- 버전 이름: 변경 없음 (`version.yml`).
- 커밋: `github.sha`(L301) 대신 체크아웃한 `HEAD`. APK 파일명, build-info, Firebase 릴리스 노트, 댓글 모두 이 값을 쓴다.
- 댓글의 번호는 이 워크플로가 계산한 값에서 읽는다.

---

## 7. 흐름

### 7.1 iOS 테스트 빌드

```
댓글 "@projectops ios build"
 → 트리거: 키워드, 브랜치 해석 → dispatch (번호 계산 없음)
 → notify-start: 브랜치 확인, 시작 댓글
 → prepare-test-build:
     체크아웃, pull → HEAD SHA 출력
     ASC 키 설치 → precheck-version --mode test
       열림: version.yml 버전 / 닫힘: 다음 패치 + 이유
     .env, 빌드 프로파일, 릴리스 노트(번호 없음)
 → build-upload-ios-test (SHA로 체크아웃):
     Flutter 빌드(임시 번호) → 인증서, 프로필, ASC 키
     archive-upload --phase build   (번호 계산, 아카이브, 서명, 번들 검증)
     "IPA 빌드 완료" 댓글
     archive-upload --phase upload  (업로드, 필요 시 재시도)
     성공/실패 댓글 (최종 번호, 버전, 커밋, 사유)
```

### 7.2 동시 빌드 예시

| 시각 (KST) | 이슈 451 | 이슈 452 |
|---|---|---|
| 14:04:00 | 아카이브, 번호 86677440 | |
| 14:06:30 | | 아카이브, 번호 86677590 |
| 14:15:10 | | 업로드 성공 |
| 14:16:00 | 업로드 거부 (`too_low`, 요구 86677590) | |
| 14:16:05 | 재시도: max(86678165, 86677591) = 86678165, 다시 아카이브 | |
| 14:22:00 | 업로드 성공 | |

### 7.3 릴리스 후 테스트 뒤 다음 릴리스

| 순서 | 빌드 | 버전 | 번호 |
|---|---|---|---|
| 1 | 2.1.2 출시 (승인) | 2.1.2 | (이전) |
| 2 | 이슈 451 테스트 | 2.1.2 닫힘 → 2.1.3 | 86677440 |
| 3 | 이슈 440 테스트 | 2.1.3 | 86770000 |
| 4 | 릴리스 2.1.3 | 2.1.3 | 86900000 (시각이 뒤라 항상 더 큼) |
| 5 | 릴리스 2.1.4 | 2.1.4 | 87200000 |

Android 릴리스는 같은 기간에 `version_code` 215, 216을 쓴다.

---

## 8. 엣지 케이스

### 8.1 번호

| # | 상황 | 처리 |
|---|---|---|
| N1 | 두 빌드가 동시에 진행 | 재시도로 해소 (7.2) |
| N2 | 같은 초에 번호를 뽑음 | 중복 거부 → 재시도 |
| N3 | 예전에 날짜형(20억대) 번호를 쓴 앱 | ASC 하한. 조회 실패 시 거부 메시지 하한 |
| N4 | ASC에 빌드가 없는 신규 앱 | 시각 번호 |
| N5 | ASC 조회 실패, 시크릿 누락, 권한 부족 | ASC 하한만 빠짐. 경고 표시 |
| N6 | 빌드 수천 개 | 끝까지 페이지 넘김, 숫자 비교 |
| N7 | 점 형식, 비정수 번호가 섞임 | 첫 정수 성분으로 비교, 파싱 불가 항목은 제외 |
| N8 | 러너 시계가 틀림 | GitHub 호스티드 러너는 NTP 동기화. 틀려도 거부 메시지 하한으로 복구 |
| N9 | macOS, visionOS 빌드가 같은 앱에 있음 | 앱 전체 단조 증가라 영향 없음 |
| N10 | Android 테스트 번호가 Play 번호보다 큼 | 비목표 (테스트 폰은 재설치) |
| N11 | Firebase 목록에서 테스트 빌드가 정식보다 위에 보임 | 표시 문제, 동작 영향 없음. 문서에 명시 |
| N12 | 한 이슈에서 100회 이상 빌드, 댓글 100개 초과, 댓글 삭제 | 댓글 세기를 없애 해당 없음 |
| N13 | 2090년 이후 Android 상한 초과 | 기준 시각 상수 교체로 대응. 문서와 코드 주석에 명시 |

### 8.2 번호 주입과 서명

| # | 상황 | 처리 |
|---|---|---|
| S1 | 앱 이름이 `Runner`가 아님 | IPA 안에서 `Payload/*.app`로 찾음 |
| S2 | 위젯, 알림 확장, 워치 앱, App Clip | 빌드 설정 4종 전달 + 서명 후 전 번들 검증 |
| S3 | 확장이 빌드 설정 변수를 안 쓰고 번호를 하드코딩 | 검증에서 불일치로 업로드 전 실패, 해당 번들과 값을 안내 |
| S4 | Xcode가 export 중 번호 변경 | ExportOptions 사본에 `manageAppVersionAndBuildNumber=false` |
| S5 | 사용자 레포 ExportOptions가 옛 템플릿 | 원본 대신 런타임 사본을 쓰므로 영향 없음 |
| S6 | 앱 화면이 `package_info_plus`로 번호 표시 | 번들 Info.plist를 읽으므로 최종 번호가 보임. `--dart-define`으로 따로 박은 값은 예외로 문서화 |
| S7 | 확장마다 별도 프로비저닝 프로필이 필요 | 현재도 미지원(프로필 1개). 이번 범위 밖, 검증 실패 메시지로 원인만 드러냄 |
| S8 | 모노레포 (`APP_ROOT`) | 모든 경로를 `APP_ROOT` 기준으로 |

### 8.3 업로드와 재시도

| # | 상황 | 처리 |
|---|---|---|
| U1 | 번호 중복, 번호 작음 | 재시도 |
| U2 | 인증, 네트워크, 서명, 기타 | 즉시 실패, 사유 한 줄 |
| U3 | 업로드 성공 후 처리 대기나 심사 제출 실패 | ASC에 이번 번호가 있으면 재업로드 금지 |
| U4 | U3 판단용 ASC 조회 불가 | 재시도하지 않고 실패 (중복 업로드 방지) |
| U5 | 빌드 중 승인되어 train 닫힘 | 테스트: 다음 패치로 재시도. 릴리스: 실패 |
| U6 | 5회 모두 실패 | 마지막 사유 표시 |
| U7 | fastlane 출력이 파이프로 묻힘 | 스크립트가 subprocess로 실행하고 종료 코드와 출력을 직접 받음 |
| U8 | 심사 제출이 엉뚱한 빌드 선택 | `BUILD_NUMBER`를 최종값으로 전달 |
| U9 | 재시도 중 job이 너무 길어짐 | 통합 job `timeout-minutes: 120` |
| U10 | 실행 취소 (브랜치별 cancel-in-progress) | 진행 중 업로드는 중단됨. 취소 댓글 처리는 13절 분리 이슈 |

### 8.4 버전 이름

| # | 상황 | 처리 |
|---|---|---|
| V1 | 승인 이후 상태 | 닫힘으로 판정 (4.2 목록) |
| V2 | 심사 대기, 심사 중 | 열림 |
| V3 | 승인 후 개발자 반려 (`DEVELOPER_REJECTED`) | 열림으로 보고 사후 복구 |
| V4 | `version.yml`이 출시 최대보다 낮음 | 출시 최대의 다음 패치 |
| V5 | 다음 릴리스가 minor(2.2.0)라 2.1.3 train이 남음 | 무해 |
| V6 | 릴리스 버전이 이미 닫힘 | 준비 단계에서 실패, 조치 안내 |
| V7 | `version.yml`에 `-beta`, `+5` 같은 접미사 | `version_manager.py`가 이미 잘라냄. 결과를 그대로 사용 |
| V8 | ASC 버전 문자열이 2자리(`2.1`) | 0을 채워 비교 |
| V9 | 번들 ID가 다른 앱의 접두사 | 정확 일치만 인정 |

### 8.5 표시와 추적

| # | 상황 | 처리 |
|---|---|---|
| D1 | 커밋 표시 | 준비 job의 `HEAD` SHA |
| D2 | job마다 다른 커밋을 빌드 | 뒤 job이 SHA로 체크아웃, pull 안 함 |
| D3 | 번호, 버전이 준비 단계 값으로 표시 | 최종 출력에서 읽음 |
| D4 | 실패 사유 없음 | `reason_line` 표시 |
| D5 | 번호로 이슈를 알 수 없음 | 비목표. 릴리스 노트와 댓글에 이슈, 브랜치, 커밋 |

---

## 9. 실패와 폴백 정책

| 실패 지점 | 결과 |
|---|---|
| 사전 점검 ASC 조회 | 경고 후 `version.yml` 버전으로 진행 (테스트, 릴리스 공통) |
| 번호의 ASC 하한 조회 | 경고 후 하한 없이 진행 |
| 업로드 거부 (번호) | 재시도 |
| 업로드 거부 (train, 테스트) | 버전 바꿔 재시도 |
| 업로드 거부 (train, 릴리스) | 실패 |
| 재업로드 여부 판단용 ASC 조회 | 재시도하지 않고 실패 |
| 번들 번호 검증 불일치 | 업로드 없이 실패 |

어떤 폴백도 지금보다 나쁜 결과를 만들지 않는다. ASC가 전혀 안 되는 레포는 지금과 같은 경로로 빌드되고, 추가로 거부 메시지 기반 복구를 얻는다.

---

## 10. 호환성과 사용자 레포 반영

- **복사 목록**: `src/core/copy/simple.js`의 `copyScripts()`에 `build_number.py`, `asc_client.py`, `ios_release.py`를 각각 호출 워크플로와 이슈 번호 주석과 함께 추가한다. 목록에서 빠져도 CI가 잡지 못하므로(`test/copy-simple.test.js`는 목록에 있는 파일의 존재만 검사) 구현 체크리스트에 넣는다.
- **마이그레이션 레지스트리**: 워크플로 파일 리네임이나 삭제가 없으므로 등록하지 않는다.
- **옛 Fastfile**: `pilot`은 번호를 IPA에서 읽고, `deliver`는 `BUILD_NUMBER` env만 쓴다. 두 값만 맞추면 되므로 Fastfile 수정 없이 동작한다.
- **ExportOptions**: 마법사 템플릿(`.github/util/flutter/testflight-wizard/templates/ExportOptions.plist`)에 `manageAppVersionAndBuildNumber=false`를 추가한다(신규 설치용). 기존 레포는 런타임 사본으로 커버된다. 마법사 `version.json`을 올리면 `version-sync.sh`를 실행한다.
- **payload `build_number`**: 한 minor 동안 빈 값으로 유지 후 제거.
- **breaking-changes.json**: 이 변경이 들어가는 릴리스 버전 키로 `warning`을 등록한다. 내용: iOS와 Android 테스트 빌드 번호가 시각 기반(약 8,700만)으로 바뀜. iOS 릴리스 번호는 더 이상 `version_code`와 같지 않으며 되돌릴 수 없음. Firebase 테스트 빌드 설치 폰은 정식 앱 설치 전 삭제 필요. `version_code`는 Android 릴리스 전용.
- **필요 시크릿**: 새로 추가되는 시크릿은 없다. 기존 `APP_STORE_CONNECT_API_KEY_ID`, `APP_STORE_CONNECT_ISSUER_ID`, `APP_STORE_CONNECT_API_KEY_BASE64`를 준비 job에서도 쓴다. 키 역할은 App Manager 이상 권장으로 문서화한다(Developer는 읽기 권한 미확인, 없으면 폴백).

---

## 11. 테스트와 검증

### 11.1 새 pytest (`.github/scripts/test/`, CI `quick` job에서 실행)

- `test_build_number.py`: 시각 번호 계산(고정 시각 주입), 하한 적용, 단조 증가, `describe` 왕복, JSON 출력 계약.
- `test_asc_client.py`: JWT 헤더와 페이로드, 테스트 중 생성한 P-256 키로 서명 후 `openssl`로 검증, DER→raw 변환, 페이지네이션, 번들 ID 정확 일치, 번호 파싱(점 형식, 비정수).
- `test_ios_release.py`:
  - `classify-error`: 3절의 실제 문구 샘플 전부(90189, 90061, 신형 DUPLICATE와 higher 문구, 90186, 90062, 90478, 무관한 실패)
  - `precheck-version`: 상태별 닫힘 판정, 다음 패치 계산, `version.yml`이 더 낮은 경우, 2자리 버전, 조회 실패 폴백, 테스트와 릴리스 모드 차이
  - `archive-upload`: 가짜 `xcodebuild`, `fastlane`, ASC로 성공, 중복 후 성공, 작음 후 성공, train 닫힘(테스트는 재시도, 릴리스는 실패), 업로드 후 뒤 단계 실패(재업로드 안 함), ASC 불가 시 재시도 안 함, 5회 소진, 번들 검증 불일치

### 11.2 기존 테스트 유지

| 테스트 | 지켜야 할 것 |
|---|---|
| `test_workflow_shell_syntax.py` | 모든 `run:` 블록이 `bash -n` 통과, heredoc 종료자 컬럼 0 |
| `test_release_tag_guard.py` | job이 자기 자신을 `needs.<id>`로 참조하지 않음 (job 통합 시 주의) |
| `test_workflow_permissions.py` | permissions 선언, 댓글 쓰는 파일의 `issues`/`pull-requests: write` |
| `test_fastlane_lanes.py` | 테스트 워크플로에 `fastlane deploy` 문자열과 `DEPLOY_MODE="store_only"` 유지. 호출이 스크립트로 옮겨가도 워크플로에 이 두 문자열이 남아야 하므로 스크립트에 넘기는 env로 둔다 |
| `test_store_whats_new.py` | 릴리스 워크플로의 `STORE_WHATS_NEW_OVERRIDE`, `INPUT_WHATS_NEW_OVERRIDE` 리터럴 줄 유지 |
| `test_comment_trigger_guard.py` | 트리거의 마커 가드 유지 |
| `npm test` (`copy-simple.test.js` 포함) | 복사 목록의 파일 존재 |

### 11.3 실측 (Twin-Fang/elum)

1. 출시된 버전 상태에서 iOS 테스트 빌드 → 다음 패치로 전환되고 시작 댓글에 이유 표시, 업로드 성공.
2. 두 이슈에서 동시에 iOS 테스트 빌드 → 둘 다 업로드 성공, 하나는 재시도 기록.
3. 확장이 있는 앱이면 번들 검증 통과 확인. 없으면 확장을 넣은 버려질 브랜치로 1회 확인.
4. 릴리스 `store_only` 1회, 가능하면 `store_prepare` 1회로 `deliver`가 최종 번호의 빌드를 고르는지 확인.
5. Android 테스트 빌드 1회로 Firebase 업로드와 번호 확인.

---

## 12. 미확인 사항과 위험

| 항목 | 위험 | 대응 |
|---|---|---|
| `xcodebuild` 명령행 빌드 설정이 모든 확장 번들까지 반영되는가 | 확장이 다른 방식으로 번호를 정하면 불일치 | 서명 후 번들 검증이 업로드 전에 막음. 11.3-3으로 실측 |
| Flutter의 Xcode 빌드 단계가 명령행 `FLUTTER_BUILD_NUMBER`를 덮어쓰는가 | 본체 번호가 임시값으로 남음 | 같은 검증으로 발견. 발견 시 아카이브 전 `Generated.xcconfig` 갱신으로 전환 |
| Developer 역할 API 키의 읽기 권한 | 사전 점검과 재업로드 판단 불가 | 폴백 경로. 문서에 App Manager 권장 |
| 신형 Apple 오류 문구 변화 | 분류 누락으로 `other` 처리 | 즉시 실패하되 사유는 보임. 샘플과 패턴 추가로 대응 |
| ASC 업로드 후 목록 반영 지연 | 재업로드 판단 시 "없음"으로 오판 | 재업로드 판단 전 짧은 대기와 재조회(최대 3회, 20초 간격) |

---

## 13. 분리 이슈 (이번 범위 밖)

원인이 달라 섞으면 리뷰와 롤백이 어렵다. 보안 두 건은 우선순위를 높게 둔다.

| 제안 이슈 | 내용 | 심각도 |
|---|---|---|
| 빌드 트리거 권한 검사 없음 | `issue_comment` 트리거에 `author_association` 검사가 없어, 공개 레포에서는 누구나 서명 키와 스토어 시크릿이 들어간 빌드를 실행할 수 있음 | 높음 |
| 워크플로 스크립트 주입 | 댓글의 브랜치 인자(트리거 L303 등), 이슈 제목(TEST-APK L548), 시크릿 값(iOS 릴리스 L178, L387, L469 등)이 스크립트에 직접 삽입됨 | 높음 |
| testflight 마법사 secrets 파일 권한 644 | 이슈 #643 §7 | 중간 |
| 셀프호스트 Android가 디버그 키로 서명, `SMB_PATH_ANDROID` 미정의 | SELFHOSTED-CICD | 중간 |
| ASC 상태 조회 수동 워크플로 | 이슈 #643 §7. `asc_client.py` 재사용 | 낮음 |
| 취소된 실행의 진행 댓글이 "진행 중"으로 남음 | 모든 테스트 빌드 워크플로 | 낮음 |
| 트리거 키워드가 부분 문자열 매칭 | "happy", "application"도 통과, 명령이 아니어도 반응과 실패 댓글 | 낮음 |
| 릴리스 준비 job의 쓰지 않는 Flutter, CocoaPods 설치 | macOS 시간 낭비 | 낮음 |

---

## 14. 문서 갱신

- `docs/FLUTTER-TEST-BUILD-TRIGGER.md`: 빌드 번호 규칙(86-127행)을 시각 기반으로 교체, 이미 틀려 있던 `0.0.0` 설명(121-126행) 수정, 출시 후 버전 자동 전환 설명 추가.
- `docs/FLUTTER-CICD-OVERVIEW.md`: iOS 번호 규칙, ASC 키 역할 권장, 실패 사유 표시.
- `docs/VERSION-CONTROL.md`: `version_code`가 Android 릴리스 전용이 되었음을 명시.
- `CLAUDE.md`: "빌드 번호 규칙은 `build_number.py` 한 곳, Apple 오류 해석은 `ios_release.py classify-error` 한 곳" 에이전트 규칙 추가.
- 두 iOS 워크플로와 TEST-APK 머리 주석의 번호 설명 갱신.
