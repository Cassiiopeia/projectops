# 커밋 메시지 컨벤션 (상세)

`common-rules.md` §"커밋 메시지 컨벤션"의 상세다. 커밋을 만드는 스킬(`pro-commit`, 커밋을 직접 실행하는
`pro-report` 등)이 읽는다.

## 형식

```
{이슈제목} : {타입} : {변경사항 설명} {이슈URL}
```

| 타입 | 용도 |
|------|------|
| `feat` | 새 기능 추가 |
| `fix` | 버그 수정 |
| `refactor` | 리팩토링 (기능 변경 없음) |
| `docs` | 문서/주석 변경 |
| `chore` | 빌드, 설정, 기타 |
| `style` | 코드 스타일 (로직 변경 없음) |
| `test` | 테스트 추가/수정 |

**예시** — 이슈 제목이 `⚙️[기능추가][Skills] commit 스킬 신규 추가`인 경우, SUH-ISSUE-HELPER가 만드는
커밋 템플릿은 이모지+태그를 제거한 순수 내용만 쓴다.

```
commit 스킬 신규 추가 : feat : 이슈 컨텍스트 기반 커밋 메시지 자동 생성 https://github.com/Cassiiopeia/projectops/issues/224
commit 스킬 신규 추가 : docs : common-rules 커밋 컨벤션 예시 수정 https://github.com/Cassiiopeia/projectops/issues/224
commit 스킬 신규 추가 : fix : owner/repo 추출 로직 버그 수정 https://github.com/Cassiiopeia/projectops/issues/224
```

## 핵심 규칙

- `{이슈제목}`은 SUH-ISSUE-HELPER가 생성한 커밋 템플릿의 앞부분을 **그대로** 쓴다 — 이모지+태그(`⚙️[기능추가][Skills]`)는 넣지 않는다
- `{타입}`은 **이번 커밋의 변경 내용**으로 정한다 — `feat`가 기본값이지만 항상 feat가 아니다
- 같은 이슈에 여러 커밋을 할 때 타입이 달라질 수 있다 (feat → fix → docs 순서 가능)
- 이슈 컨텍스트가 있을 때만 이 형식을 쓴다. 이슈와 무관한 커밋(hotfix, 설정 변경 등)은 자유 형식 허용
- 사용자가 `/commit` 스킬을 호출하면 이 형식으로 자동 완성

커밋 템플릿은 `github_cli.py get-commit-template "{이슈 제목}" "{이슈URL}"`의 `template`을 **그대로** 쓴다.
타입은 제목 태그에서 추론된다(버그 → `fix`, 기능 → `feat`, 문서 → `docs` 등). 실제 작업이 태그와 다를 때만
`--type`으로 바꾼다.

## 커밋 타입이 릴리스 버전을 결정한다 (#546)

`version.yml`의 `metadata.template.options.semver_auto`가 켜진 레포는 릴리스 구간 커밋 제목으로 버전
승격 폭이 정해진다. 타입을 아무거나 고르면 버전이 잘못 나간다.

| 커밋 타입 | 릴리스 결과 |
|---|---|
| `제목 : feat! : 내용` (또는 `feat!:`) | **major** — 4.2.45 → 5.0.0 |
| `제목 : feat : 내용` | **minor** — 4.2.45 → 4.3.0 |
| `fix` / `docs` / `chore` / `refactor` / `test` | patch — 4.2.45 → 4.2.46 |

- **`!`는 호환성이 깨질 때만 붙인다** — 기존 사용자의 설정·API·CLI 인자가 더 이상 동작하지 않게 되는
  변경. 확신이 없으면 붙이지 말고 사용자에게 묻는다.
- 한 릴리스 구간에 섞이면 가장 높은 것이 이긴다 (major > minor > patch).
- 키가 없거나 `false`인 레포는 항상 patch라 타입이 버전에 영향을 주지 않는다.

## 이슈 기반 커밋 원칙

커밋 전 이슈 번호가 확정돼 있어야 한다. 브랜치명(`YYYYMMDD_#번호_제목`)에서 번호를 뽑거나
(`commit_cli.py get-issue-number`), 사용자가 알려준 번호로 이슈를 조회해 확인한다. develop 직행처럼
브랜치명에 번호가 없으면 사용자에게 번호를 묻는다. 번호를 확인하지 못하면 **즉시 멈추고** 선택지를
제시한다 — 임의로 커밋 메시지를 만들어 커밋하지 않는다.
