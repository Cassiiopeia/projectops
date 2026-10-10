> 언제 읽나: worktree 생성 후 4단계(gitignored 로컬 파일 후보 조사·판단·선택 복사)를 진행할 때. 후보 기준·제외 목록·탐색 명령·분류 기준·참조 확인·출력 형식이 여기 있다.

# Gitignored 로컬 파일 후보 조사 및 선택 복사

Worktree 생성 성공 후 **원본 프로젝트에 존재하는 gitignored 로컬 파일 후보를 먼저 조사**하고, 에이전트가 복사 필요성을 판단한 뒤 필요한 파일만 복사한다.

이 단계의 목적은 `.gitignore`에 등록된 모든 파일을 무조건 복사하는 것이 아니다. Spring, React, React Native, Flutter 등 프로젝트 타입마다 필요한 로컬 설정 파일이 다르므로, 후보를 inventory로 만든 뒤 판단 근거를 남겨 재발 가능한 누락을 줄이는 것이다.

## 4-1. 소스/대상 경로 확정

- **소스(원본) 루트**: 현재 작업 중인 프로젝트 루트 (`git rev-parse --show-toplevel`로 확인)
- **대상(워크트리) 루트**: 3단계에서 확인한 `WORKTREE_PATH`

## 4-2. .gitignore에서 후보 inventory 생성

소스 루트의 `.gitignore`를 읽어 **원본 프로젝트에 실제 존재하는 파일/디렉토리 후보**를 먼저 만든다. 에이전트는 익숙한 파일명만 임의로 고르지 말고, 반드시 이 inventory를 기준으로 판단한다.

**포함 기준** (아래 조건을 모두 만족):
- `!`(negation) 접두어 없음
- 주석(`#`) 라인 아님
- 빈 줄 아님
- 패턴이 `**` glob을 포함하지 않는 단순 경로 또는 단순 확장자(`*.yml` 수준)

**명백한 제외 대상** (패턴 또는 실제 경로에 아래 문자열이 포함되면 복사 후보에서 제외):
```
build/  target/  .gradle  node_modules  Pods/  .dart_tool
Generated  generate  .last_build_id  .framework  .flx  .zip
DerivedData  XCBuildData  .class  .pyc  .log  .symbols  .map.json
.pub-cache  .pub/  migrate_working_dir  .history  .svn  .swiftpm
bin/  out/  dist/  nbproject  .sts4-cache  .springBeans
.idea  .vscode  .DS_Store  .flutter-plugins  flutter_export_environment.sh
```

## 4-3. 실제 존재 파일 탐색

후보 패턴 각각에 대해 소스 루트에서 실제 파일 존재 여부 확인:

```bash
# 단순 경로 패턴 (예: android/key.properties)
ls [소스_루트]/[패턴]

# 와일드카드 패턴 (예: *.env, src/main/resources/application-*.yml)
find [소스_루트] -name "[패턴파일명부분]" \
  -not -path "*/build/*" \
  -not -path "*/target/*" \
  -not -path "*/.gradle/*" \
  -not -path "*/node_modules/*" \
  -not -path "*/Pods/*" \
  -not -path "*/.dart_tool/*" \
  -not -path "*/*-Worktree/*" \
  -type f -size -1M
```

> `-size -1M`: 1MB 초과 파일은 민감 설정 파일이 아닐 가능성 높으므로 제외

## 4-4. 에이전트 판단 기준

탐색된 후보를 바로 전부 복사하지 말고, 아래 기준으로 `복사 권장` / `판단 필요` / `복사 비권장`으로 분류한다.

**복사 권장**:
- 런타임 환경 설정: `.env`, `.env.local`, `.env.*`, `application-*.yml`, `application-*.yaml`, `application-*.properties`
- 인증/키/서명 설정: `key.properties`, `*.jks`, `*.keystore`, `service-account*.json`, `firebase-key*.json`
- 플랫폼 로컬 설정: `google-services.json`, `GoogleService-Info.plist`
- 빌드/런타임 설정 파일에서 직접 참조되는 gitignored 파일

**판단 필요**:
- 프로젝트 고유의 `*.json`, `*.yml`, `*.yaml`, `*.properties`, `*.toml`, `*.xcconfig` 파일
- 이름만으로 용도를 확정하기 어렵지만 원본에는 존재하고 worktree에는 없는 로컬 설정 파일

**복사 비권장**:
- 재생성 가능한 캐시/빌드 결과
- IDE 상태 파일
- 의존성 디렉토리
- 로그, 임시 파일, 대용량 파일

## 4-5. 참조 관계 확인

복사 여부가 애매한 후보는 프로젝트 파일에서 참조되는지 확인한다. 참조되는 gitignored 파일은 `복사 권장` 후보로 승격한다.

확인 예시:
```bash
rg -n "후보파일명|후보파일명에서_확장자_제외한_이름" [소스_루트] \
  -g '!build/**' -g '!target/**' -g '!node_modules/**' -g '!Pods/**' \
  -g '!.dart_tool/**' -g '!*.lock'
```

참조 관계 예:
- iOS/Flutter: `*.xcconfig`의 `#include`
- Android/Gradle: signing config, `key.properties`, keystore 참조
- Spring: profile/import 설정, `application-*.yml`, `application-*.properties`
- React/React Native/Node: dotenv/env loader, Firebase 설정 참조

## 4-6. 경로 계산 및 복사 실행

탐색된 각 파일에 대해:

1. **상대 경로 계산**: `절대경로` → 소스 루트 기준 상대경로
2. **대상 경로** = `대상_루트` + `상대경로`
3. **복사**:
```bash
mkdir -p [대상_파일의_부모_디렉토리]
cp [소스_절대경로] [대상_절대경로]
```

복사/스킵 결과는 반드시 근거와 함께 출력한다:

```
✅ copied ios/Flutter/Secrets.xcconfig
reason: ios/Flutter/Debug.xcconfig 또는 Release.xcconfig에서 include되는 로컬 빌드 입력 파일

⏭ skipped .dart_tool/package_config.json
reason: Flutter가 재생성하는 캐시 파일
```

## 4-7. 복사 결과 및 누락 후보 체크

각 파일 복사 후 대상 경로 존재 확인. 결과를 `✅` / `❌`로 표시.

그 다음, 원본 inventory 중 대상 worktree에 존재하지 않는 후보를 다시 출력한다. 이 단계는 실패 처리하지 않는다. 단, 에이전트는 누락 후보마다 복사하지 않은 이유를 남겨야 한다.

출력 예시:
```
⚠️ 복사되지 않은 gitignored 후보:
  - ios/Flutter/Secrets.xcconfig
    판단: 복사 권장
    근거: ios/Flutter/Debug.xcconfig에서 include됨
    조치: 복사 필요 여부 재검토

  - .idea/workspace.xml
    판단: 복사 비권장
    근거: IDE 로컬 상태 파일
    조치: 복사하지 않음
```
