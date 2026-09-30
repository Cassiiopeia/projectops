# 배포형 앱(`app`) 추가 기준

방문자가 코드를 import하는 게 아니라 **받아서 설치하는** 레포. README는 제품 페이지 역할을 한다.

근거 (조사 시점 2026-09-30): stablyai/orca, localsend, immich, rustdesk, AppFlowy, jan, ente, Aegis, saber-notes/saber.
**표본은 공개 FOSS 앱 9개다.** 스토어로만 배포하는 앱은 표본에 거의 없으므로 아래 "반드시"를 그대로 옮기지 않는다.
먼저 배포 방식을 판별한다.

## 0. 배포 방식부터 판별

| 방식 | 단서 | 적용 |
|---|---|---|
| **A. GitHub 릴리스로 설치 파일 배포** | Releases에 apk·ipa·dmg·exe 자산 | 아래 1절 "반드시" 전부 + 3절 |
| **B. 스토어 전용** (Play·App Store) | Releases 자산이 없고 스토어 링크만 | 1절 중 다운로드 경로·스크린샷·최소 OS·버그 폼만. **릴리스 파일·서명 항목은 해당 없음**. 2절 스토어 요건 적용 |
| **C. 둘 다** | 스토어 + Releases(사이드로드) | 전부 |

배포 방식이 불분명하면 사용자에게 묻는다.

## 1. 반드시 (방식 A 기준. B는 표에 표시한 것만)

| 항목 | 물어볼 것 | 근거 | B(스토어 전용) |
|---|---|---|---|
| 다운로드 경로가 README 맨 위 | 공식 스토어 배지(Play·App Store·F-Droid·Flathub) 또는 플랫폼×채널 표가 첫 화면에 있나 | 9개 전부 | 적용 |
| 실제 스크린샷 | 기기 프레임은 드물다. 실제 화면이면 된다 | 9개 전부 | 적용 |
| 최소 OS 버전 | Android·iOS 몇 이상인지 적혀 있나 | | 적용 |
| CI가 만든 릴리스 파일, 일관된 이름 | `<app>-<version>-<os>-<arch>.<ext>`, Android는 ABI별 + universal | arm64가 압도적 (조사 시점: localsend arm64 약 11.5만 vs arm32 약 1.2만) | 해당 없음 |
| 읽히는 릴리스 노트 | 사람 말 요약 먼저, 그다음 "조치 필요·마이그레이션" | immich | GitHub 릴리스가 없으면 해당 없음 |
| 버그 폼에 버전·OS | 앱 안 어디서 버전을 보는지까지 안내하나 | 9개 전부 | 적용 |
| 서명된 빌드 | 배포하는 APK·AAB가 **릴리스 키로 서명**됐나(debug 서명이 아닌가)? 서명 인증서 지문을 README나 SECURITY.md에 공개했나? 채널(GitHub APK·Play)마다 지문이 다르면 어느 쪽인지 밝혔나? | Aegis·saber가 공개 | 해당 없음 (스토어가 서명을 관리) |

## 2. 스토어 심사 요건 (방식 B·C)

이 항목은 **취향이 아니라 심사 이슈**다. 레포에서는 "제출했는지"를 볼 수 없으므로 **사용자에게 묻는다.** 공식 문서로 확인한 것만 사실로 적었다.

| 항목 | 확인된 사실 (출처) | 레포에서 볼 것 |
|---|---|---|
| 개인정보처리방침 URL | **Apple: 모든 앱에 필수** (https://developer.apple.com/help/app-store-connect/manage-app-information/manage-app-privacy). **Google Play: 데이터 보안 양식을 제출하려면 개인정보처리방침이 필요** (https://support.google.com/googleplay/android-developer/answer/10787469). Play 정책은 방침이 "active, publicly accessible and non-geofenced URL (no PDFs) and is non-editable"이어야 한다고 적는다 (https://support.google.com/googleplay/android-developer/answer/10144311) | `collect`의 `files.privacy_policy`. 있으면 경로를, 없으면 README "개인정보" 절이 있는지 본다 |
| **README 절·GitHub blob 페이지가 그 URL로 받아들여지는가** | **확인 필요.** 위 공식 문서에 "앵커 URL·GitHub 렌더 페이지 허용 여부"는 없다. 단정하지 않는다. "non-editable" 조건과 GitHub 페이지의 관계도 문서에 없다 | 사용자가 스토어에 실제로 넣은 URL을 묻는다 |
| 계정 삭제 | **Apple**: 계정 생성을 지원하는 앱은 앱 안에서 계정 삭제를 시작할 수 있어야 한다(2022-06-30부터). 비활성화만으로는 부족하다 (https://developer.apple.com/support/offering-account-deletion-in-your-app/). **Google Play**: 계정 생성 앱은 앱 안 삭제 경로와, 앱을 지운 사용자를 위한 웹 링크가 필요하다 (https://support.google.com/googleplay/android-developer/answer/13327111) | 앱에 회원가입이 있나 → 있으면 계정 삭제 경로(앱 안·웹)가 README나 앱 코드에 있나 |
| 데이터 보안(Play)·개인정보 영양 라벨(Apple) | 둘 다 **수집·사용하는 데이터를 스토어 콘솔에 신고**해야 한다 (위 Play 10787469, Apple manage-app-privacy 링크). 신고 내용은 앱이 실제로 하는 일과 맞아야 한다 | 레포에서는 제출 여부를 볼 수 없다. 사용자에게 묻고, 코드의 권한·SDK(위치·광고·분석)와 신고 내용이 맞는지 대조한다 |

- 위 표의 나머지 세부 요건(항목별 입력 방법, 예외)은 **확인하지 못했다(확인 필요).** 공식 문서를 열어 확인하라고 안내한다.
- `privacy_policy.md`를 레포에 두고 스토어 URL로 쓰는 방식(변경 이력이 git에 남는다, saber)이 있다. 이것이 위 요건을 만족하는지는 스토어 정책에 달려 있으니 확인 필요로 둔다.

## 3. 권장

- 버그 폼에 **설치 경로**(Play / App Store / TestFlight / Firebase App Distribution / GitHub APK)와 로그 위치
- 스토어 메타데이터를 레포에 둔다: `fastlane/metadata/android/<locale>/`, 스토어 "새 기능"은
  `changelogs/<versionCode>.txt`. README 스크린샷도 여기서 가져오면 한 벌로 관리된다 (Aegis·saber)
- 베타·RC 채널
- 자동 업데이트, 또는 스토어 설치 권장 (업데이트 매니페스트가 설치 파일보다 훨씬 많이 받아진다)
- SECURITY.md(신고 채널 포함), `SHA256SUMS`, 서명 인증서 지문 공개. Play App Signing을 쓰면 Play가 다른 키로 재서명하므로
  채널별로 어느 지문인지 README에 밝힌다
- 앱 자체의 번역 (Weblate·Crowdin·inlang)
- **민감 권한(위치·마이크·카메라·연락처 등)을 쓰는 앱은 권한 설명 표** — 어떤 권한을 왜, 언제 쓰는지와 수집·전송 여부.
  조사한 9개 중 아무도 안 했다. 차별화이면서 위 스토어 데이터 신고와 앱의 실제 동작을 맞추는 근거 자료가 된다

## 4. 있으면 좋음

- F-Droid·재현 가능한 빌드, 패키지 매니저(winget·Homebrew)
- 빌드 변형 분리 (스토어용·사이드로드용·FOSS)
- 상표 안내 (포크가 이름을 못 쓰게)

## 5. 실제 앱 레포 점검에서 관찰된 패턴

- **`collect`의 `files.privacy_policy`** — 개인정보처리방침 파일을 루트·docs·.github에서 찾는다. 파일이 없고 README에 "개인정보" 절만
  있는 앱 레포가 실제로 있었다. 이때는 "파일 없음, README 절 있음"으로 기록하고 스토어 URL로 쓰는 것이 문제 없는지는 2절대로 **확인 필요**로 둔다.
- **fastlane·스토어 메타데이터는 루트에 없을 수 있다.** Flutter 앱은 `android/fastlane`, `ios/fastlane` 아래에 둔다.
  `files.store_metadata_root`가 `false`여도 없다고 단정하지 말고 `files.mobile_dirs`의 폴더 안을 직접 본다.
- 앱 레포는 `docs/` 번호 문서(요구사항·릴리스·운영 등)와 `release-notes/` 폴더를 두는 경우가 있다. 릴리스 노트가
  README·CHANGELOG 어디에 있는지 `root_entries`로 먼저 확인한다.

## 6. 라이선스 맥락

- 서버가 딸린 앱(immich·rustdesk·AppFlowy·ente)은 조사 당시 AGPL을 많이 썼다. AGPL은 수정한 프로그램을 네트워크로 제공할 때도
  사용자에게 소스를 제공할 의무가 생길 수 있는 라이선스다. 이 선택의 의도는 레포마다 다르므로 추측하지 않는다.
- 순수 클라이언트 앱은 MIT·Apache·GPL이 보였다.
- 라이선스는 권하지 않고 선택지와 차이만 설명한다. 스토어 배포 앱에 GPL 계열 코드가 들어갈 때의 양립 여부는 `rubric.md` E3대로 확인 필요로 둔다.

## 7. projectops와 연결 (projectops 워크플로우를 쓰는 레포일 때만)

레포가 projectops의 Flutter 워크플로우(Play Store·TestFlight·Firebase·APK 빌드)를 쓴다면 릴리스 파일·스토어 메타데이터
개선안은 **그 워크플로우를 고치는 방향**으로 제안한다. 지켜야 할 규칙 하나: **워크플로우가 부르는 fastlane lane은 Fastfile에 실제로 있어야 한다.**
Fastfile은 설정 마법사가 다시 덮어쓰므로 lane을 손으로 더하지 말고 워크플로우를 이미 있는 lane에 맞춘다. 테스트 빌드는 심사 자동 제출로
이어지는 모드가 켜지지 않도록 배포 모드를 명시한다.
