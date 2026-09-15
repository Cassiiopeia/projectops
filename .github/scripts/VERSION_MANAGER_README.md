# Version Manager Documentation

## 개요
이 스크립트는 다양한 프로젝트 타입에서 버전을 중앙 관리하는 도구입니다.
GitHub Actions와 연동되어 자동으로 버전을 관리하고 동기화합니다.

## 프로젝트 타입별 동기화 파일

### Spring (`spring`)
- **동기화 파일**: `build.gradle`
- **버전 형식**: `version = "x.y.z"` 또는 `version = 'x.y.z'`
- **설명**: 모든 하위 build.gradle 파일도 함께 업데이트됩니다

### Flutter (`flutter`)
- **동기화 파일**: `pubspec.yaml`
- **버전 형식**: `version: x.y.z`
- **설명**: Flutter 프로젝트의 표준 버전 파일

### React/Node.js (`react`, `node`)
- **동기화 파일**: `package.json`
- **버전 형식**: `"version": "x.y.z"`
- **설명**: npm/yarn 패키지 버전과 동기화

### React Native (`react-native`)
- **iOS 동기화 파일**: `ios/*/Info.plist`
  - **버전 형식**: `<key>CFBundleShortVersionString</key><string>x.y.z</string>`
- **Android 동기화 파일**: `android/app/build.gradle`
  - **버전 형식**: `versionName "x.y.z"`
- **설명**: iOS가 있으면 iOS 우선, 없으면 Android 파일 사용

### React Native Expo (`react-native-expo`)
- **동기화 파일**: `app.json`
- **버전 형식**: `"expo": { "version": "x.y.z" }`
- **설명**: Expo 관리형 프로젝트의 버전 파일

### Python (`python`)
- **동기화 파일**: `pyproject.toml`
- **버전 형식**: `version = "x.y.z"`
- **설명**: Python 프로젝트의 표준 버전 파일 (FastAPI, Django 등)

### Basic/기타 (`basic` 또는 기타)
- **동기화 파일**: `version.yml`만 사용
- **버전 형식**: `version: "x.y.z"`
- **설명**: 특정 프로젝트 타입이 없는 경우 version.yml만 관리

## 동작 방식

### 버전 동기화
1. `version.yml`과 프로젝트 파일의 버전을 비교
2. 더 높은 버전으로 자동 동기화
3. 모든 관련 파일을 동시에 업데이트

### 버전 증가
`increment`는 `--bump`로 승격 폭을 받습니다. 생략하면 `patch`입니다(기존 동작).

- **Patch**: 세 번째 자리 증가 (x.y.Z -> x.y.Z+1) — `--bump patch` 또는 생략
- **Minor**: 두 번째 자리 증가, patch는 0으로 (x.Y.z -> x.Y+1.0) — `--bump minor`
- **Major**: 첫 번째 자리 증가, 나머지는 0으로 (X.y.z -> X+1.0.0) — `--bump major`
- **version_code**: 승격 폭과 무관하게 항상 +1

릴리스 워크플로우는 `version.yml`의 `metadata.template.options.semver_auto`가 `true`일 때
커밋 제목을 분류해(`changelog_manager.py classify-bump`) 이 값을 결정합니다.
키가 없거나 `false`면 항상 `patch`입니다. 자세한 규칙은 `docs/VERSION-CONTROL.md` 참조.

## 사용 명령어

```bash
# 현재 버전 확인 (동기화 포함)
./version_manager.sh get

# 버전 증가 (기본 patch)
./version_manager.sh increment

# 승격 폭 지정
./version_manager.sh increment --bump minor   # 1.2.3 -> 1.3.0
./version_manager.sh increment --bump major   # 1.2.3 -> 2.0.0

# 특정 버전으로 설정
./version_manager.sh set 1.2.3

# 버전 동기화만 수행
./version_manager.sh sync

# 버전 형식 검증
./version_manager.sh validate 1.2.3
```

## GitHub Actions 워크플로우

워크플로우는 다음과 같이 동작합니다:
1. main 브랜치에 푸시 시 자동 실행
2. 현재 버전 확인 및 동기화
3. Patch 버전 자동 증가
4. 변경사항 커밋 및 태그 생성

## 주의사항

- `project_types`는 최초 설정 후 변경하지 마세요 (첫 항목이 primary)
- 버전은 항상 `x.y.z` 형식을 유지해야 합니다
- 프로젝트 파일과 version.yml 중 높은 버전이 우선됩니다
- 커밋 메시지에 `[skip ci]`가 포함되면 워크플로우가 실행되지 않습니다