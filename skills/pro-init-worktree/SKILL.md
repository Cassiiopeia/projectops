---
name: pro-init-worktree
description: "Create a git worktree from a branch name and copy only the needed local files (found via .gitignore) with reasons. Use for worktree creation, branch-isolated work, or /init-worktree."
---

# Git Worktree 자동 생성

## When to use

- worktree 생성, 브랜치 분리 작업, 독립 작업 환경 구성이 필요할 때, /init-worktree 호출 시 사용한다.

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

### 3단계: worktree 생성

임시 Python 스크립트를 만들지 않는다. 브랜치명(`#`·한글 그대로)을 `--branch` 로 넘기면 된다 (스크립트 찾기는 `../references/common-rules.md` §표준 호출 패턴, `SKILL=pro-init-worktree`).

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/worktree_cli.py create --root {원본_루트} --branch "{브랜치명}" --base origin/develop
```

- **새 브랜치는 `--base` 에서 딴다.** 생략하면 지금 체크아웃된 HEAD 에서 따므로, 다른 작업 브랜치 위에서 부르면 엉뚱한 커밋이 딸려 온다. 개발 브랜치(`origin/develop` 등)를 명시한다. 이미 있는 로컬·리모트 브랜치는 `--base` 와 무관하게 그대로 쓴다.
- 결과 JSON 의 `worktree` 가 새 폴더 경로다. 실패하면 `output_tail` 의 첫 오류를 본다.

### 4단계: Gitignored 로컬 파일 후보 조사 및 선택 복사

**`references/local-files.md` 를 읽고 그대로 진행한다.** 핵심만:

- **먼저 기억을 꺼낸다** — `{PYTHON} {SCRIPTS}/worktree_cli.py recall --root {원본_루트}` (스크립트 찾기는 `../references/common-rules.md` §표준 호출 패턴, `SKILL=pro-init-worktree`).
  지난번 세트가 있으면 `copy_now` 는 그대로 복사하고 **`new_candidates` 만 판단**한다. 처음이면(`first_time`) 전부 판단한다.
- **기억한 세트는 손으로 `cp` 하지 않는다** — `{PYTHON} {SCRIPTS}/worktree_cli.py copy --root {원본_루트} --to {worktree_경로}` (대상에 이미 있는 파일은 `--overwrite` 없이는 건드리지 않는다. 새로 판단한 파일은 `--files a,b`).
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
```

커밋 템플릿은 직접 조립하지 않는다. 브랜치명의 이슈 번호로 `github_cli.py get-issue {owner} {repo} {번호}`를 불러
원본 제목과 URL을 받고, `github_cli.py get-commit-template "{원본 제목}" "{이슈URL}"`의 `template`을 그대로 보여준다.
타입은 제목 태그에서 추론된다(버그 → `fix`, 기능 → `feat`) — `feat`로 고정하면 `semver_auto` 레포에서 버그 수정이 minor로 오른다.
이슈를 조회하지 못하면(PAT 없음 등) 템플릿 줄을 뺀다.

## 브랜치명 처리 규칙

- `#` 문자: Git 브랜치명에서는 **원본 유지**, 폴더명에서만 `_`로 변환
- 특수문자: 폴더명 생성 시 `_`로 변환
- Worktree 위치: `{프로젝트명}-Worktree/` 폴더 (예: `myapp-Worktree`)

## 스크립트 위치

> **고정 진입점이 있으면 아래 탐색을 건너뛴다** (#942): `~/.projectops/bin/projectops_cli.py` 는 한 번이라도 CLI 를 실행하면 생기고, 부를 때마다 설치된 가장 새 스크립트를 찾아 인자를 그대로 넘긴다. 세션 도중 플러그인이 업데이트돼도 옛 경로에 묶이지 않는다.
> `PYTHONIOENCODING=utf-8 python3 ~/.projectops/bin/projectops_cli.py init-worktree <서브커맨드> ...` (없거나 `scripts_not_found` 면 아래 탐색). 응답에 `newer_installed` 가 오면 이 진입점으로 다시 부른다.
> zsh 에서 명령을 변수에 담지 않는다 (`P="python3 …"; $P` 는 exit 127). 줄이려면 함수로 감싼다: `G(){ PYTHONIOENCODING=utf-8 python3 ~/.projectops/bin/projectops_cli.py init-worktree "$@"; }` → `G recall --root {원본_루트}`.

`worktree_manager.py`를 다음 순서로 탐색:
1. `scripts/worktree_manager.py`

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-init-worktree`.
Keys for this skill: the common `language`, `tone`, `rules` only.
Preferences change presentation only; approval gates, secret protection and `--dry-run` stay in force.

## 작업이 끝난 worktree 제거

`git worktree remove --force` 를 직접 치지 않는다. 이슈가 실제로 닫혔는지 먼저 확인한 뒤:

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/worktree_cli.py remove --root {원본_루트} --branch "{브랜치명}"
```

미커밋 변경이 있으면 `dirty` 와 변경 목록을 돌려주고 멈춘다. 버려도 된다고 사용자가 정한 뒤에만 `--force`. 브랜치와 커밋은 남는다.
