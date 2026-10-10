# Phase 6 — Finishing 상세

> 언제 읽나: 모든 task 완료 + Phase 3 검증 통과 후, PR·로컬 머지·보관·폐기 중 하나를 실행할 때.

superpowers finishing-a-development-branch 패턴 + SUH GitHub 환경 특화.

**진입 조건**: 모든 Phase 2 태스크 completed + Phase 3 검증 통과. 미충족 시 이 Phase 진입 금지.

## Step 1: 최종 테스트 검증

빌드/타입체크/주요 테스트 실제 실행. 출력 그대로 인용.

실패 시:
```
테스트 실패 — Finishing 진입 불가.
실패 내용: {출력 그대로}
수정 후 Phase 3부터 다시 진행하세요.
```

## Step 2: 환경 감지 + 변수 보관

```bash
GIT_DIR=$(git rev-parse --git-dir)
GIT_COMMON=$(git rev-parse --git-common-dir)
WORKTREE_PATH=$(git rev-parse --show-toplevel)
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
# 머지 대상은 개발(릴리스 소스) 브랜치다 — version.yml metadata.deploy_branch, 없으면 develop.
# origin/HEAD(=기본·배포 브랜치)로 잡으면 main 에 직접 머지하게 된다.
BASE_BRANCH=$(grep -E '^[[:space:]]*deploy_branch:' version.yml 2>/dev/null | head -1 | sed -E 's/.*deploy_branch:[[:space:]]*"?([^"#[:space:]]+)"?.*/\1/')
[ -n "$BASE_BRANCH" ] || BASE_BRANCH=develop
DEFAULT_BRANCH=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||')
MAIN_ROOT=$(git -C "$GIT_COMMON/.." rev-parse --show-toplevel)
```

판정:
- `GIT_DIR != GIT_COMMON` → worktree 환경 (옵션 2/4에서 worktree 정리)
- `BASE_BRANCH` → 옵션 2 머지 대상. 원격에 그 브랜치가 없으면(`git ls-remote --heads origin "$BASE_BRANCH"`가 비면) 사용자에게 묻는다
- **`BASE_BRANCH`가 `main`/`master`이거나 `DEFAULT_BRANCH`와 같으면 옵션 2를 막는다** — 기본(배포) 브랜치는 릴리스 PR(`/pro-changelog-deploy`)로만 갱신된다. 이때는 옵션 1(PR)만 안내한다
- `CURRENT_BRANCH`, `WORKTREE_PATH`, `MAIN_ROOT` → Step 4에서 사용

## Step 3: 옵션 제시

```
구현이 완료되었습니다. 어떻게 진행할까요?

1. GitHub PR 생성 (권장)
2. 로컬 브랜치 머지
3. 보관 (나중에 처리)
4. 폐기

번호를 선택하세요.
```

## Step 4: 옵션별 실행

**옵션 1 — GitHub PR 생성**:
- `github` 스킬 호출 (⚠ `gh pr create` 직접 호출 금지 — common-rules의 전용 스킬 경유 강제)
- PR 제목·본문은 `pro-github` 의 PR 제목 규칙을 그대로 따른다 — 이슈 제목에서 이모지와 `[태그]`를 뺀 순수 텍스트 (이슈 없으면 plan 한 줄 요약). 형식을 여기서 따로 정하지 않는다
- PR base 는 위 `BASE_BRANCH`(개발 브랜치)다
- worktree 유지 (PR 피드백 반영 위해)

**옵션 2 — 로컬 머지** (`BASE_BRANCH`가 기본·배포 브랜치면 실행하지 않는다):

> ⚠ **공유 작업 트리에서 `checkout` 하지 않는다.** `MAIN_ROOT`는 다른 세션도 쓰는 트리일 수 있고,
> 거기서 브랜치를 바꾸면 그 세션의 작업 기준이 통째로 바뀐다. `MAIN_ROOT`의 현재 브랜치가
> 이미 `BASE_BRANCH`일 때만 아래를 실행하고, 아니면 멈추고 사용자에게 알린다 (옵션 1 PR 권장).
> `git pull`은 non-fast-forward 면 `--rebase`로 통합한다 — 강제 리셋 금지.

```bash
MAIN_ROOT=$(git -C "$(git rev-parse --git-common-dir)/.." rev-parse --show-toplevel)
cd "$MAIN_ROOT"
[ "$(git rev-parse --abbrev-ref HEAD)" = "$BASE_BRANCH" ] || { echo "MAIN_ROOT 가 $BASE_BRANCH 에 있지 않습니다 — checkout 하지 않고 멈춥니다"; exit 1; }
git pull --rebase origin "$BASE_BRANCH"
git merge <feature-branch>
```
머지 후 테스트 재검증 → 통과 시 worktree 정리:
```bash
git worktree remove "$WORKTREE_PATH"
git worktree prune
git branch -d <feature-branch>
```

**옵션 3 — 보관**:
"브랜치 `{name}` 보관됨. worktree: `{path}`"
worktree 유지.

**옵션 4 — 폐기**:
```
⚠ 다음을 영구 삭제합니다:
- 브랜치: {name}
- 커밋: {목록}
- worktree: {path} (있으면)

확인하려면 'discard' 를 입력하세요.
```
확인 후:
```bash
MAIN_ROOT=$(git -C "$(git rev-parse --git-common-dir)/.." rev-parse --show-toplevel)
cd "$MAIN_ROOT"
git worktree remove "$WORKTREE_PATH"   # worktree 있을 때만
git worktree prune
git branch -D <feature-branch>
```

## Step 5: 변경 보고서 안내 (선택)

옵션 1~4 실행 후 사용자에게 한 줄 안내:
> "변경 보고서가 필요하면 `/report` 호출하면 됩니다 (Phase 4에서 메모리 보관한 변경 파일 목록 + 검증 결과 활용)."

자동 호출 안 함 — 사용자 선택.

## Finishing 안티 패턴

| ❌ | ✅ |
|---|---|
| 테스트 실패 상태로 옵션 제시 | Step 1 통과 후에만 Step 3 진입 |
| `gh pr create` 직접 사용 | `github` 스킬 호출 |
| 폐기 확인 없이 브랜치 삭제 | 'discard' typed confirmation |
| worktree 안에서 `git worktree remove` | MAIN_ROOT로 cd 후 실행 |
| 옵션 1/3 후 worktree 삭제 | 옵션 2/4만 worktree 정리 |
| `impl.md` 산출물 자동 생성 | implement는 산출물 없음. `/report` 별도 호출 |
