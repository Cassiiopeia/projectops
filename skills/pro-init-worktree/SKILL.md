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

**`references/local-files.md` 를 읽고 그대로 진행한다.** 핵심만:

- **먼저 기억을 꺼낸다** — `{PYTHON} {SCRIPTS}/worktree_cli.py recall --root {원본_루트}` (스크립트 찾기는 `../references/common-rules.md` §표준 호출 패턴, `SKILL=pro-init-worktree`).
  지난번 세트가 있으면 `copy_now` 는 그대로 복사하고 **`new_candidates` 만 판단**한다. 처음이면(`first_time`) 전부 판단한다.
- **복사가 끝나면 바로 기록한다** — `{PYTHON} {SCRIPTS}/worktree_cli.py record --root {원본_루트} --copied a,b --skipped c`.
  상대 경로만 넘긴다(파일 내용·값은 넘기지 않는다). 이 호출을 빼먹으면 다음 worktree 에서 같은 판단을 다시 한다.
- `.gitignore` 에서 **원본에 실제로 있는 후보 inventory** 를 먼저 만든다 — 익숙한 파일명만 골라 복사하지 않는다.
- 후보마다 `복사 권장` / `판단 필요` / `복사 비권장` 으로 분류하고, 애매하면 프로젝트 파일에서 **참조되는지** 확인해 승격한다.
  (`.env*` · `application-*.yml` · `key.properties` · `*.jks` · `google-services.json` · `GoogleService-Info.plist` 는 권장, 캐시·IDE·의존성·로그는 비권장)
- 복사·스킵·누락 후보 **모두 근거(reason)와 함께** 출력한다. 누락 후보는 실패 처리하지 않는다.

### 5단계: 결과 출력

```
✅ Worktree 생성 완료!
📍 경로: [worktree_path]
📋 복사된 파일:
  ✅ android/app/google-services.json
  ✅ ios/Runner/GoogleService-Info.plist

📝 커밋 메시지 템플릿:
{get-commit-template 의 template 그대로}
(작업 완료 후 /pro-commit 으로 자동 커밋하세요)
```

커밋 템플릿은 직접 조립하지 않는다. 브랜치명의 이슈 번호로 `github_cli.py get-issue {owner} {repo} {번호}`를 불러
원본 제목과 URL을 받고, `github_cli.py get-commit-template "{원본 제목}" "{이슈URL}"`의 `template`을 그대로 보여준다.
타입은 제목 태그에서 추론된다(버그 → `fix`, 기능 → `feat`) — `feat`로 고정하면 `semver_auto` 레포에서 버그 수정이 minor로 오른다.
이슈를 조회하지 못하면(PAT 없음 등) 템플릿 줄을 빼고 `/pro-commit`만 안내한다.

## 브랜치명 처리 규칙

- `#` 문자: Git 브랜치명에서는 **원본 유지**, 폴더명에서만 `_`로 변환
- 특수문자: 폴더명 생성 시 `_`로 변환
- Worktree 위치: `{프로젝트명}-Worktree/` 폴더 (예: `myapp-Worktree`)

## 스크립트 위치

`worktree_manager.py`를 다음 순서로 탐색:
1. `scripts/worktree_manager.py`
