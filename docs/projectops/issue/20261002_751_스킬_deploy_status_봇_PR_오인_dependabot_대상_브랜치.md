📝 현재 문제점
---

- `deploy-status`가 `--pr` 없이 호출되면 base 브랜치(main)로 들어오는 열린 PR 중 **첫 번째**를 deploy PR로 고른다. head를 확인하지 않는다. 의존성 봇(Dependabot)도 기본 브랜치로 PR을 올리므로 봇 PR이 deploy PR로 오인된다. 실제로 `Bump actions/github-script` PR(#748)이 "기존 deploy PR"로 잡혔다.
- `pro-changelog-deploy`는 기존 deploy PR이 있으면 재사용하며 `update-pr`로 본문을 릴리스 노트로 덮어쓴다. 오인된 상태로 이 경로를 타면 봇 PR 본문이 덮어써진다.
- 새로 추가한 `.github/dependabot.yml`이 대상 브랜치를 지정하지 않아 PR이 main으로 올라온다. 이 레포는 main 직접 반영이 곧 배포 트리거(npm 배포, 버전 안전망)라 의존성 PR이 main으로 향하면 안 된다.
- 루트 `.github/workflows/`의 공통 워크플로우는 `project-types/common/` 원본과 동일해야 하는데(CLAUDE.md 규칙) 이를 검증하는 테스트가 없다. Dependabot이 루트 사본만 바꾸면 조용히 어긋난다. 열린 PR에는 `checkout 5→7`, `setup-node 4→7` 같은 메이저 업데이트도 섞여 있다.

🛠️ 해결 방안 / 제안 기능
---

- deploy PR 탐색에 `head` 필터를 추가한다. head를 주면 그 브랜치에서 온 PR만, 주지 않으면 `dependabot/`, `renovate/` 브랜치를 제외한다. CLI에 `--head` 인자를 추가하고 스킬 문서의 호출에 반영한다.
- `dependabot.yml`에 `target-branch: develop`을 지정하고, 메이저 버전 업데이트는 무시한다.
- 루트 공통 워크플로우와 `project-types/common/` 사본이 같은지 검사하는 테스트를 추가한다.

⚙️ 작업 내용
---

- `scripts/common/gh_client.py`: `find_open_pr_by_base`에 head 필터와 봇 제외
- `skills/pro-changelog-deploy/scripts/changelog_cli.py`, `SKILL.md`: `--head` 인자와 호출 반영
- `.github/dependabot.yml`: 대상 브랜치와 메이저 무시
- 회귀 테스트: PR 탐색, 공통 워크플로우 사본 동일성
