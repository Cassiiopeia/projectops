# 수정 등급과 적용 방법

결함을 찾은 뒤 무엇을 **자동으로 고치고**, 무엇을 **초안까지만** 만들고, 무엇을 **제안만** 하는지.
모든 수정은 레포마다 계획을 보여주고 승인받은 뒤 적용한다. 조직 레포는 팀원과 공유하는 곳이다.

## 등급

| 등급 | 항목 | 적용 경로 |
|---|---|---|
| **API 수정** (승인 후 즉시) | About description·homepage·topics, Discussions 켜기, 라벨 생성·이름 변경(이력 유지)·색상 | `/pro-github` (`github_cli.py`) 또는 GitHub REST |
| **파일 추가** (승인 후 커밋) | CONTRIBUTING, SECURITY, CODE_OF_CONDUCT(Contributor Covenant), yml 이슈 폼, `ISSUE_TEMPLATE/config.yml`, PR 템플릿, `dependabot.yml`, AGENTS.md, AI 기여 정책 절 | 레포를 로컬에 받아 파일 작성 → `/pro-commit` |
| **초안** (사용자가 검토) | README 재구성, 비교 표, 벤치마크 절, vhs `.tape`, 로고·배너 SVG, 소셜 미리보기 이미지 | 파일로 만들어 보여주고 반영 여부를 묻는다 |
| **제안만** | 라이선스 선택·변경, 소셜 미리보기 업로드(API 없음), 브랜치 보호, 거버넌스, 레포 보관(archive), 레포 이름 변경 | 보고서에 이유와 방법만 적는다 |

## 라벨을 바꿀 때

- 기존 라벨은 **삭제하지 말고 이름을 바꾼다** (`PATCH /repos/{o}/{r}/labels/{name}` 의 `new_name`).
  이미 붙은 이슈에 그대로 이어진다.
- 권장 기본 세트 (project-auto-wizard #255에서 검증):
  - `type: bug` `type: feature` `type: enhancement` `type: docs` `type: test` `type: chore` `type: refactor`
  - `area: <레포 영역>` (레포 구조를 보고 정한다)
  - `priority: critical` `priority: high` `priority: medium` `priority: low`
  - `status: needs triage` `status: in progress` `status: blocked`
  - GitHub 기본 유지: `good first issue` `help wanted` `duplicate` `wontfix` `question`
- **projectops를 쓰는 레포는 한글 상태 라벨(`작업전`·`작업중`·`작업완료` 등)이 Projects 보드 동기화에
  쓰인다.** 이 라벨은 지우거나 바꾸지 않는다. 영어 라벨을 **추가**만 하고, 전환은 사용자에게 묻는다.

## 영어화

- 공개 레포의 README 기본은 영어다. 한국어는 `README.ko.md`로 옮기고 상단에 언어 링크를 둔다.
- 코드 속 사용자 노출 문구까지 영어로 바꾸는 것은 큰 작업이다. 카탈로그 구조(`en`·`ko`)를 먼저 제안하고,
  카탈로그 밖 한글 유입을 막는 검사를 함께 권한다 (project-auto-wizard #331·#337 방식).

## 커밋·푸시

- 커밋은 `/pro-commit` 규칙을 따른다. 푸시는 사용자가 명시적으로 요청할 때만 한다.
- 대상 레포가 로컬에 없으면 clone 위치를 사용자에게 묻는다.
