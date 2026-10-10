# 레포 탐색 (explore)

> 언제 읽나: "내 레포 보여줘", "레포 목록 탐색해줘", "README 가져와줘", "{레포명} 정보 봐줘", "Org 레포 탐색해줘" 같은 요청일 때.

명령은 `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py explore <sub> ...` 형태다 (SKILL.md "스크립트 찾기"). 출력 JSON을 그대로 파싱해 판단한다.

## Phase 0 — Owner 결정

1. "내 레포", owner 미명시 → config의 기본 repo owner 또는 현재 git remote owner를 사용한다. 사용자가 실제 PAT 소유자 레포 목록을 원하면 owner를 명시하게 한다.
2. owner 명시 ("acme-org", "acme-user" 등) → 해당 owner 사용. 기본 `--type auto`로 user/org를 자동 판별한다.

## Phase 1 — 레포 목록

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py explore list-repos {owner} --type auto
# user/org가 확실하면: --type user 또는 --type org
```

**필터링**: 사용자가 "fork 제외", "Java만", "stars 높은 순" 등을 요청하면 별도 API 재호출 없이 위 결과에서 agent가 직접 필터링한다.

## Phase 2 — 단일 레포 상세

특정 레포명이 언급되면 아래 4개를 순서대로 수집한다. 각 호출은 독립적이며, 하나가 실패해도 나머지는 계속 진행한다.

```bash
# 2-1. 기본 메타정보
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py explore repo-detail {owner} {repo}
# 2-2. README
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py explore readme {owner} {repo}
# 2-3. 언어 구성
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py explore languages {owner} {repo}
# 2-4. 최근 커밋 10개
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py explore commits {owner} {repo} --limit 10
```

`next` 값이 있으면 그대로 이어서 실행해 탐색 흐름을 연결한다.
