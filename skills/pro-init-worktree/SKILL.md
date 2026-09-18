---
name: pro-init-worktree
description: "Git Worktree 자동 생성 도구. 브랜치명을 입력받아 worktree를 생성하고, .gitignore 기반 로컬 파일 후보를 조사해 필요한 파일만 근거와 함께 선택 복사한다. worktree 생성, 브랜치 분리 작업, 독립 작업 환경 구성이 필요할 때 사용. /init-worktree 호출 시 사용."
---

# Git Worktree 자동 생성

브랜치명을 입력받아 **Git worktree를 자동 생성하고, .gitignore 기반 로컬 파일 후보를 조사한 뒤 worktree에 필요한 파일만 근거와 함께 선택 복사**하라.

## 사용자 입력

$ARGUMENTS

## 입력 없는 경우

사용법을 안내하라:
```
/init-worktree
20260120_#163_Github_Projects_에_대한_템플릿_개발_필요
```

## 실행 프로세스

### 1단계: 브랜치명 추출
- 사용자 입력에서 브랜치명 추출 (`#` 문자 포함 원본 유지)
- 브랜치명이 없으면 사용법 안내 후 종료

### 2단계: 환경 준비
```bash
# 프로젝트 루트로 이동
cd [프로젝트_루트]

# Git 긴 경로 지원 (Windows, 최초 1회)
git config --global core.longpaths true
```

### 3단계: 임시 Python 스크립트 생성 및 실행

**인코딩 문제 해결을 위해 브랜치명을 코드에 직접 포함**시킨 임시 파일을 생성한다.

파일명: `init_worktree_temp_{timestamp}.py`

```python
# -*- coding: utf-8 -*-
import sys, os, shutil, glob

os.chdir('프로젝트_루트_경로')

branch_name = '브랜치명_원본_그대로'

# worktree_manager 실행
sys.path.insert(0, 'scripts')  # 플러그인 루트 scripts/
import worktree_manager
os.environ['GIT_BRANCH_NAME'] = branch_name
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.argv = ['worktree_manager.py']
exit_code = worktree_manager.main()

if exit_code == 0:
    import subprocess
    result = subprocess.run(['git', 'worktree', 'list', '--porcelain'],
                            capture_output=True, text=True, encoding='utf-8')
    lines = result.stdout.split('\n')
    worktree_path = None
    for i, line in enumerate(lines):
        if line.startswith(f'branch refs/heads/{branch_name}'):
            worktree_path = lines[i-1].replace('worktree ', '')
            break
    if worktree_path:
        print(f'WORKTREE_PATH={worktree_path}')

sys.exit(exit_code)
```

**실행** (Windows에서는 `-X utf8` 필수):
```bash
python -X utf8 init_worktree_temp_{timestamp}.py
```

실행 후 임시 파일 삭제.

### 4단계: Gitignored 로컬 파일 후보 조사 및 선택 복사

Worktree 생성 성공 후 **원본 프로젝트에 존재하는 gitignored 로컬 파일 후보를 먼저 조사**하고, 에이전트가 복사 필요성을 판단한 뒤 필요한 파일만 복사한다.

이 단계의 목적은 `.gitignore`에 등록된 모든 파일을 무조건 복사하는 것이 아니다. Spring, React, React Native, Flutter 등 프로젝트 타입마다 필요한 로컬 설정 파일이 다르므로, 후보를 inventory로 만든 뒤 판단 근거를 남겨 재발 가능한 누락을 줄이는 것이다.

#### 4-1. 소스/대상 경로 확정

- **소스(원본) 루트**: 현재 작업 중인 프로젝트 루트 (`git rev-parse --show-toplevel`로 확인)
- **대상(워크트리) 루트**: 3단계에서 확인한 `WORKTREE_PATH`

#### 4-2. .gitignore에서 후보 inventory 생성

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

#### 4-3. 실제 존재 파일 탐색

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

#### 4-4. 에이전트 판단 기준

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

#### 4-5. 참조 관계 확인

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

#### 4-6. 경로 계산 및 복사 실행

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

#### 4-7. 복사 결과 및 누락 후보 체크

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

### 5단계: 결과 출력

```
✅ Worktree 생성 완료!
📍 경로: [worktree_path]
📋 복사된 파일:
  ✅ android/app/google-services.json
  ✅ ios/Runner/GoogleService-Info.plist

📝 커밋 메시지 템플릿:
{브랜치명에서 날짜·이슈번호·이모지·태그 제거한 순수 제목} : feat : {변경사항 설명} {이슈URL}
(작업 완료 후 /commit 으로 자동 커밋하세요)
```

## 브랜치명 처리 규칙

- `#` 문자: Git 브랜치명에서는 **원본 유지**, 폴더명에서만 `_`로 변환
- 특수문자: 폴더명 생성 시 `_`로 변환
- Worktree 위치: `{프로젝트명}-Worktree/` 폴더 (예: `myapp-Worktree`)

## 스크립트 위치

`worktree_manager.py`를 다음 순서로 탐색:
1. `scripts/worktree_manager.py`
