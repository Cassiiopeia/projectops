# 기여하기

이슈를 맡고 PR을 보내는 방법을 짧게 정리했습니다. 전체 안내(개발 환경, 검사, 커밋 형식, 코드 규칙)는 GitHub의 [CONTRIBUTING.md](https://github.com/Cassiiopeia/projectops/blob/main/CONTRIBUTING.md)([한국어](https://github.com/Cassiiopeia/projectops/blob/main/docs/i18n/CONTRIBUTING.ko.md))에 있습니다.

## 이슈 맡기

`good first issue`·`help wanted` 라벨이 붙은 이슈는 댓글로 맡을 수 있습니다. 같은 일을 두 사람이 고치지 않게 하기 위해서입니다.

| 댓글 (한 줄에 단독으로) | 결과 |
|---|---|
| `/assign` | 봇이 담당자로 지정합니다. 이미 맡은 사람이 있으면 누구인지 알려 줍니다 |
| `/unassign` | 맡은 이슈를 내려놓습니다 |

- **7일** 안에 연결된 PR이 없으면 지정이 풀리고 다른 사람이 맡을 수 있습니다 (매일 한 번 확인합니다).
- 큰 변경(새 프로젝트 타입, 새 워크플로우, 동작 변경)은 먼저 이슈를 열고 메인테이너의 방향 확인을 기다려 주세요.
- 질문은 이슈 대신 [Discussions](https://github.com/Cassiiopeia/projectops/discussions)에 남겨 주세요.

## PR 열기

1. PR은 `main`이 아니라 **`develop`** 을 대상으로 엽니다. `main`은 릴리스 PR만 받습니다.
2. 본문에 `Fixes #<번호>`를 적어 이슈와 연결합니다.
3. 푸시 전에 검사를 돌립니다.

```bash
npm test
python3 -m pytest scripts/tests/ .github/scripts/test/ -q
```

포크에서 보낼 때는 브랜치 이름은 자유입니다. 커밋 메시지와 PR 제목은 Conventional Commits(`fix: ...`, `docs: ...`)로 쓰면 메인테이너가 머지할 때 프로젝트 형식으로 바꿉니다.

## 관련 문서

- [브랜치 네이밍 규칙](BRANCH-CONVENTION.md): 메인테이너 자동화가 쓰는 `YYYYMMDD_#번호_제목` 형식
- [워크플로우 주석 표준](WORKFLOW-COMMENT-GUIDELINES.md): 워크플로우 파일 주석 규칙
- [Translating](TRANSLATING.md): 파일을 추가해 언어를 더하는 방법 (영어 원문)
