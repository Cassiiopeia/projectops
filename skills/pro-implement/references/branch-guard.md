# Phase 0-0 — 브랜치 가드 상세

> 언제 읽나: 구현을 시작하려는데 현재 브랜치가 보호 브랜치(main/develop/release 등)로 보일 때.

**목적**: 보호 브랜치(`main`/`master`/`develop`/`*release*`/`R_*` 등) 위에서 곧장 편집이 시작되는 사고 방지.

## 0-0-1. 현재 브랜치 조회

```bash
git rev-parse --abbrev-ref HEAD
```

- 실패 시 (not a git repo) → 가드 스킵, Phase 0으로 바로 진행
- `HEAD` 가 반환됨 (detached HEAD) → 보호 브랜치로 간주 (안전 우선)

## 0-0-2. 보호 브랜치 판정

다음 중 하나라도 매치되면 보호 브랜치:

- 정확 일치: `main`, `master`, `develop` (단 `develop`은 아래 0-0-3의 개발 브랜치 직행 예외를 먼저 본다)
- 패턴 매치 (case-insensitive): `*release*`, `^R_\d+$`, `.*_R_\d+$`
- `git symbolic-ref refs/remotes/origin/HEAD` 결과 (있으면)

## 0-0-3. 보호 브랜치 아니면 통과

Phase 0으로 진행.

**개발 브랜치 직행 레포는 통과한다.** 레포가 개발 브랜치에서 직접 작업하는 것을 기본으로
선언했으면(레포 `CLAUDE.md`·`AGENTS.md`에 "develop에서 직접 작업", "develop 직행" 같은 규칙이
있으면), 현재 브랜치가 그 개발 브랜치(`version.yml`의 `metadata.deploy_branch`, 없으면 `develop`)일 때
보호 브랜치로 보지 않고 Phase 0으로 진행한다. 묻지 않는다 — 레포가 이미 정한 규칙이다.
`main`/`master`/기본(배포) 브랜치는 이 예외가 없다.

## 0-0-4. 보호 브랜치면 3옵션 제시

```
⚠ 현재 '<branch>' 브랜치 위에 있습니다 (보호 브랜치).
어떻게 진행할까요?

1. worktree 새로 만들기 (권장)
2. 현재 위치에서 새 브랜치만 생성 (git checkout -b)
3. 그냥 이 브랜치에서 진행
```

## 0-0-5. 옵션별 분기

**옵션 1 (worktree)**:
- `init-worktree` 스킬에 위임
- 사용자가 최초 메시지에서 이미 준 정보(이슈 번호 등) 전달
- 생성 완료 후 사용자가 선택한 워크트리 경로 안내
- 메시지: "새 세션에서 `{경로}` 로 이동 후 `/implement` 다시 호출하세요"
- **현 세션 implement 흐름은 여기서 종료** (현 세션에서는 워크트리 이동 불가)

**옵션 2 (새 브랜치만)**:
1. "새 브랜치명을 알려주세요" 질문
2. `git checkout -b {입력받은_이름}` 실행
3. Phase 0으로 진행

**옵션 3 (현 브랜치에서 진행)**:
- 사용자가 3을 선택하면 바로 Phase 0으로 진행
- 재확인 없음 (사용자가 이미 선택했으므로)
