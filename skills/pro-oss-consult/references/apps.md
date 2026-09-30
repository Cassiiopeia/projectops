# 배포형 앱(`app`) 추가 기준

방문자가 코드를 import하는 게 아니라 **받아서 설치하는** 레포. README는 제품 페이지 역할을 한다.

근거 (2026-09-30): stablyai/orca, localsend, immich, rustdesk, AppFlowy, jan, ente, Aegis, saber-notes/saber.

## 반드시

| 항목 | 물어볼 것 | 근거 |
|---|---|---|
| 다운로드 경로가 README 맨 위 | 공식 스토어 배지(Play·App Store·F-Droid·Flathub) 또는 플랫폼×채널 표가 첫 화면에 있나 | 9개 전부 |
| 실제 스크린샷 | 기기 프레임은 드물다. 실제 화면이면 된다 | 9개 전부 |
| 최소 OS 버전 | Android·iOS 몇 이상인지 적혀 있나 | |
| CI가 만든 릴리스 파일, 일관된 이름 | `<app>-<version>-<os>-<arch>.<ext>`, Android는 ABI별 + universal | arm64가 압도적 (localsend 11.5만 vs arm32 1.2만) |
| 읽히는 릴리스 노트 | 사람 말 요약 먼저, 그다음 "조치 필요·마이그레이션" | immich |
| 버그 폼에 버전·OS | 앱 안 어디서 버전을 보는지까지 안내하나 | 9개 전부 |
| 서명된 빌드 | | |

## 권장

- 버그 폼에 **설치 경로**(Play / App Store / TestFlight / Firebase App Distribution / GitHub APK)와 로그 위치
- `privacy_policy.md`를 레포에 두고 스토어 개인정보처리방침 URL로 쓴다 (변경 이력이 git에 남는다, saber)
- 스토어 메타데이터를 레포에 둔다: `fastlane/metadata/android/<locale>/`, 스토어 "새 기능"은
  `changelogs/<versionCode>.txt`. README 스크린샷도 여기서 가져오면 한 벌로 관리된다 (Aegis·saber)
- 베타·RC 채널
- 자동 업데이트, 또는 스토어 설치 권장 (업데이트 매니페스트가 설치 파일보다 훨씬 많이 받아진다)
- SECURITY.md, `SHA256SUMS`, 서명 인증서 지문 공개. Play App Signing을 쓰면 Play가 다른 키로 재서명하므로
  채널별로 어느 지문인지 README에 밝힌다
- 앱 자체의 번역 (Weblate·Crowdin·inlang)

## 있으면 좋음

- F-Droid·재현 가능한 빌드, 패키지 매니저(winget·Homebrew)
- 빌드 변형 분리 (스토어용·사이드로드용·FOSS)
- **앱 권한 설명 표** — 조사한 9개 중 아무도 안 했다. Flutter 앱이 차별화할 수 있는 빈자리다
- 상표 안내 (포크가 이름을 못 쓰게)

## 실제 앱 레포로 점검해 보고 보강한 것 (EarLocAlert, 2026-10-01)

- **`collect`의 `files.privacy_policy`** — 개인정보처리방침 파일을 루트·docs·.github에서 찾는다. 없으면 README의
  "개인정보" 절이 스토어 URL 역할을 하는지 본다 (EarLocAlert는 파일 없이 README 절로 둔다).
- **fastlane·스토어 메타데이터는 루트에 없을 수 있다.** Flutter 앱은 `android/fastlane`, `ios/fastlane` 아래에 둔다.
  `files.store_metadata_root`가 `false`여도 없다고 단정하지 말고 `files.mobile_dirs`의 폴더 안을 직접 본다.
- 앱 레포는 `docs/` 번호 문서(요구사항·릴리스·운영 등)와 `release-notes/` 폴더를 두는 경우가 있다. 릴리스 노트가
  README·CHANGELOG 어디에 있는지 `root_entries`로 먼저 확인한다.

## 라이선스 맥락

- 서버가 딸린 앱(immich·rustdesk·AppFlowy·ente)은 AGPL을 많이 쓴다. 수정한 서버를 호스팅하는 회사가
  소스를 공개하게 하려는 것이다. 수익은 유료 등급·호스팅 서비스에서 낸다.
- 순수 클라이언트 앱은 MIT·Apache·GPL.
- 라이선스는 권하지 않고 선택지와 차이만 설명한다.

## projectops와 연결

사용자의 Flutter 레포 다수는 projectops의 Flutter 워크플로우(Play Store·TestFlight·Firebase·APK 빌드)를
쓴다. 릴리스 파일·스토어 메타데이터 개선안은 **그 워크플로우를 고치는 방향**으로 제안한다.
워크플로우가 Fastfile의 lane과 맞아야 한다는 규칙(CLAUDE.md #601)을 지킨다.
