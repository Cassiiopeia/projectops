# 커밋 메시지 구성 규칙 · mention 정제

> 언제 읽나: 타입 판단이 애매할 때, 이슈 제목 정제 규칙을 확인할 때, `sanitize-message` 결과(`removed: true`)나 실패를 해석할 때.

## 이슈 제목 정제 (SUH-ISSUE-HELPER의 `extractIssueTitle`과 동일)

`get-issue` 출력의 `title`은 **agent가 임의 요약/재작성하지 않고** 결정적으로 정제한다.

1. `[태그]` 형식(`[버그]`, `[기능개선]` 등)을 모두 제거
2. 앞에 붙은 이모지·제어문자(So/VS16/ZWJ)를 제거
3. 앞뒤 공백 trim — 결과가 비면 원본 제목을 그대로 사용

같은 규칙을 `commit_cli.py normalize-title "<제목>"` 이 실행한다. 이슈 URL·정제 제목·타입을 한 번에 조립하려면
`commit_cli.py get-commit-template "<이슈제목>" "<이슈URL>" [--type fix]` 를 쓴다 (`--type` 을 생략하면 제목 태그에서 유도하므로, 태그와 실제 작업이 다를 때만 지정). 현재 작업 디렉터리 기준 이슈 번호는
`commit_cli.py get-issue-number` 로도 얻을 수 있다.

## 타입 추천표

| 변경 내용 | 추천 타입 |
|-----------|-----------|
| 새 기능, 새 파일 추가 | `feat` |
| 버그 수정, 에러 처리 | `fix` |
| 코드 구조 변경 (로직 유지) | `refactor` |
| 문서, 주석, README | `docs` |
| 설정 파일, 빌드 관련 | `chore` |
| 테스트 추가/수정 | `test` |
| 스타일, 포맷 | `style` |

**호환성이 깨지는 변경이면 타입 뒤에 `!`를 붙인다** (예: `feat!`, `fix!`, `chore!`).
릴리스 시 이 마커가 major 승격(4.x.x → 5.0.0)을 발동시킨다 (#546 — `semver_auto` 켜진 레포).
기존 사용자의 설정·API·CLI 인자가 더 이상 동작하지 않게 되는 변경에만 붙이고,
확신이 없으면 붙이지 않는다 (사용자에게 물어본다).

## 메시지 형식

`{clean_title} : {타입} : {변경설명} {html_url}`

| 부분 | 결정 방식 |
|------|-----------|
| `clean_title` | 위 정제 결과 **그대로** — agent가 다시 요약/재작성하지 않는다 |
| `html_url` | `get-issue` 결과 **그대로** |
| `{타입}` | diff 분석으로 agent 추천 (사용자 승인) |
| `{변경설명}` | staged diff 분석으로 agent 작성 (사용자 승인) |

- agent가 자유 판단하는 부분은 **타입과 변경설명뿐**이다.
- `{변경설명}`에 `@username` GitHub mention(`@claude` 등)을 절대 포함하지 않는다. 이슈 본문·제목에서 따온 문구에 mention이 있으면 제거 후 사용한다.
- 이슈 없이 자유 형식으로 커밋하는 경우에만 제목을 직접 입력받는다.

## mention trailer 정제 (`sanitize-message`)

커밋 직전, 메시지 끝의 `@username` mention trailer를 무조건 자동 제거한다(skill 차원 강제 sanitize). 메시지 작성 단계의 검열을 우회한 경우의 마지막 방어선이다.

> ⚠️ **셸 `sed`로 하지 않는다 (#523).** 과거 `sed -E ':a;$!N;$!ba;...'` 한 줄로 처리했는데 이 라벨 구문이 **GNU sed 전용**이라 macOS(BSD sed)에서는 **종료 코드 0으로 조용히 통과하며 입력을 그대로 흘려보냈다.** 안전망이 켜져 있다고 믿는 상태에서 실제로는 꺼져 있었다. OS별 도구 차이를 타지 않도록 `commit_cli.py`로 옮겼다.

- 출력 JSON: `{"message": "정리된 메시지", "removed": true|false, "summary": "..."}`. `removed`가 `true`면 mention이 실제로 제거된 것이므로, 왜 들어갔는지 메시지 작성 단계를 되짚어본다.
- **실패해도 빈 메시지를 만들지 않는다.** 스크립트 호출이 실패하거나 결과가 비면 **커밋을 중단**한다(`git commit -m ""`로 깨지는 것을 막는다). 과거 sed 방식은 실패를 성공으로 보고했지만 이제는 드러난다.
- 정제 규칙은 `commit_cli.py`의 `sanitize-message` **한 곳에만** 둔다. 문서에 같은 정규식을 fallback으로 복제하지 않는다 — 규칙이 두 곳에 있으면 한쪽만 고쳐져 어긋난다(sed 시절 사고의 재발 경로).
- **본문 중간의 mention은 보존한다.** `@projectops build app 관련 수정`처럼 의미 있게 등장한 mention은 지우지 않고, **끝에 붙은 trailer만** 제거한다.
