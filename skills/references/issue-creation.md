# 이슈 생성 워크플로우 (pro-github 전용)

사용자가 GitHub **이슈를 새로 만들어달라**고 하면(예: "이슈 만들어줘", "버그 리포트 올려줘", "기능 요청 이슈") `pro-github` 스킬이 이 절차를 따른다. 대략적인 설명을 받아 **이슈 템플릿에 맞는 제목·본문을 작성**하고, **로컬 파일로 먼저 저장**한 뒤, 사용자 확인(또는 자동 승인 설정)에 따라 **GitHub에 등록**하고, **즉시 브랜치명을 계산**해 다음 작업 선택지를 준다.

> 조회/수정/댓글/라벨/담당자/PR 등 "생성 외" 작업은 `pro-github/SKILL.md`를 따른다. 이 문서는 **생성 워크플로우 전용**이다.

명령은 모두 `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py <서브커맨드> ...` 형태다. `{PYTHON}` · `{SCRIPTS}` · `{PROJECT_ROOT}`는 `pro-github/SKILL.md` "스크립트 찾기"를 한 번 실행해 얻은 실제 경로로 써넣는다 (Bash는 호출마다 상태가 초기화된다). PAT는 CLI가 자동 로드한다.

## 시작 전

1. `common-rules.md`의 **절대 규칙** 적용 (Git 커밋 금지, 민감 정보 보호).
2. **Config 확인** — `config-rules.md` §2~5 절차. config.json은 고정 경로 `{HOME}/.projectops/config/config.json` 한 곳뿐이다 (Read tool로 직접 읽는다. `ls`·`find`로 탐색 금지).
   - 있으면 → `global_pat`, `repos` 추출. **레포 선택**: ① `git remote get-url origin`의 `owner/repo`를 `repos`와 매칭 → ② 실패 시 `default: true`인 repo → ③ 없거나 여러 개면 번호를 매겨 고르게 한다.
   - 없으면 → `global_pat`, `default_assignee`, 첫 repo(owner/repo/name)를 수집해 저장 (형식은 `config-rules.md`).
3. **자동 승인 모드 판정** — `issue.auto_approve` (키 이름은 하위 호환을 위해 `issue.*` 유지). 먼저 발견되는 값 채택:
   1. `github.repos[]` 중 현 OWNER/REPO 항목의 `issue.auto_approve`
   2. `github.issue.auto_approve` (글로벌)
   3. 없으면 `false` (안전 default — 수동 승인)

   기억: `AUTO_APPROVE`(boolean), `CONFIG_HAS_KEY`(1·2에서 발견했으면 true, 아니면 첫 실행).
   > 자동 모드라도 중복 검사(2-1, 4-1)와 open 동일 이슈 발견 시 중단 정책은 그대로다. auto_approve는 "최종 등록 승인" 게이트만 스킵한다.
4. **담당자 결정** — "글로벌 + 레포별 오버라이드 + 첫 실행만 질문" 패턴:
   1. `github.repos[]`의 현 OWNER/REPO 항목의 `issue.assignee`
   2. `github.default_assignee` (글로벌)
   3. 없으면 미설정 (첫 실행 — 4단계 C-2에서 한 번만 질문)

   기억: `ASSIGNEE`, `ASSIGNEE_HAS_KEY`. 정해져 있으면 묻지 않고 자동 적용하며 승인 화면에 "담당자: {ASSIGNEE}"만 표시한다.

> 사용자에게 노출하는 안내는 자연어로만 한다. "auto_approve", "config.json" 같은 키 이름·경로를 사용자 메시지에 쓰지 않는다.

## 허용 이모지+태그 규칙

> **언어는 대상 레포의 템플릿을 따른다.** 대상 레포의 `.github/ISSUE_TEMPLATE/`를 읽어 그 템플릿의 언어, 절 제목, 허용 태그를 그대로 쓴다. 한글 템플릿이면 한글 절 제목과 태그(`❗[버그]`)를, 영문 템플릿이면 영문(`❗[Bug]`)을 쓴다. 템플릿이 없으면 영문으로 쓴다(아래 기본값). 두 언어의 태그는 모두 커밋 타입과 매핑된다.

**주요 태그** (타입 결정, 하나만):

| 영문 (기본) | 한글 | 용도 |
|-------------|------|------|
| `❗[Bug]` | `❗[버그]` | 버그 리포트 |
| `🎨[Design]` | `🎨[디자인]` | 디자인/UI 요청 |
| `🔧[Feature Request]` | `🔧[기능요청]` | 기능 요청 |
| `⚙️[Feature]` | `⚙️[기능추가]` | 새 기능 추가 |
| `🚀[Improvement]` | `🚀[기능개선]` | 기존 기능 개선 |
| `🔍[QA]` | `🔍[시험요청]` | QA/테스트 요청 |

**수식어 태그** (선택, 주요 태그 앞에):

| 영문 (기본) | 한글 | 조건 |
|-------------|------|------|
| `🔥[Urgent]` | `🔥[긴급]` | 사용자가 "긴급"이라 명시할 때만 |
| `📄[Docs]` | `📄[문서]` | 문서 관련일 때 |
| `⌛[~month/day]` | `⌛[~월/일]` | 마감일이 있을 때 |

**규칙**: 이모지와 `[` 사이에 공백 없음. 위 목록에 없는 이모지 사용 금지.
템플릿 주석의 복사용 예시는 `❗ [Bug][Category]`처럼 공백이 있지만 **제목에는 붙여 쓴다**. 등록된 이슈 제목이 전부 붙여 쓴 형태이고, 이슈 헬퍼·커밋 템플릿이 어느 쪽이든 태그를 똑같이 걷어 내므로 표기만 하나로 맞춘다.

## 절대 금지

- 채팅으로만 이슈 본문을 출력하고 파일 저장을 생략하는 것
- 코드적인 내용 (구현 방법, 코드 예시)
- 허용 목록에 없는 이모지, 이모지와 `[` 사이 공백
- `🔥[긴급]` 임의 추가 (사용자가 명시할 때만), 담당자 임의 채우기
- 생성 단계에서 템플릿 기본 라벨(`status: todo`) 외의 상태 라벨을 붙이거나 이슈를 닫는 것. 이후 시작(`status: in progress`)·완료(`status: done` 후 close)·취소(`status: cancelled` 후 close) 전환은 `common-rules.md` §이슈 상태 처리 규칙을 따른다
- 자동 모드에서 중복 검사(2-1, 4-1) 스킵 — 항상 실행. open 동일 이슈 발견 시 무조건 중단
- config 키 이름·파일 경로를 사용자 메시지에 노출

## 프로세스

### 1단계: 이슈 타입 자동 판단

| 타입 | 키워드 | 템플릿 |
|------|--------|--------|
| **버그** | 안 됨, 에러, 깨짐, 오류, 크래시, 장애 | `bug_report` |
| **기능** | 추가, 만들어야, 새로, 구현, 개선, 변경, 요청 | `feature_request` |
| **디자인** | 디자인, UI, UX, 폰트, 색상, 레이아웃 | `design_request` |
| **QA** | 테스트, QA, 시험, 검증, 확인 | `qa_request` |

**기능 세분류**: `🔧[Feature Request]`/`🔧[기능요청]`(요청/검토), `⚙️[Feature]`/`⚙️[기능추가]`(완전히 새 기능), `🚀[Improvement]`/`🚀[기능개선]`(기존 개선).

### 2단계: 이슈 제목 생성

```
[이모지+태그][카테고리] 제목 (50자 이내)
```

예: `⚙️[Feature][Skills] Add issue edit subcommands to the github skill` (한글 템플릿 레포: `⚙️[기능추가][Skills] github 스킬 이슈 편집 서브커맨드 보강`)

**제목 문장부호 규칙 (필수)** — 키보드로 바로 못 치는 문장부호는 "AI가 만든 티"가 나므로 쓰지 않는다.

- **em dash(`—`), en dash(`–`) 금지.** 콜론·쉼표·괄호로 대체. ❌ `스킬 리브랜딩 — 중립화` / ✅ `스킬 리브랜딩: 중립화`
- **가운뎃점(`·`) 금지.** 쉼표나 슬래시로 대체. ❌ `옛 이름·워크플로우명 수정` / ✅ `옛 이름, 워크플로우명 수정`
- 일반 하이픈(`-`)은 파일명·버전(`v4.2.0`) 등 원래 표기에 필요할 때만.

### 2-1단계: 중복 이슈 검색 (파일 저장 전)

제목에서 핵심 키워드를 뽑는다 (이모지·`[...]` 태그·특수문자·URL 제거 → 핵심 명사 2~3개). keyword는 마지막 인자로 그대로 넘긴다(공백 포함 가능, 내부에서 URL 인코딩). 인라인 Python 금지.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py search-issues {owner} {repo} "{핵심 키워드 2~3개}"
```

출력 JSON `{"count":N,"items":[{number,title,url,state,labels}]}`. `closed` 항목은 중복에서 제외. `[ERROR]`가 stderr에 찍히면 중복 검색을 건너뛰고 경고 후 진행.

**판단 (open 이슈만):**
- **사실상 동일** → 아래를 출력하고 **종료**.
  ```
  🚫 이미 동일한 이슈가 존재합니다.

  #{number} — {title}
  {html_url}

  새 이슈 생성을 중단합니다. 기존 이슈에서 작업을 이어가세요.
  ```
- **유사하지만 다름** → 경고 후 사용자 확인 (1. 새로 만들기 / 2. 취소). 2면 종료.
- **무관** / 결과 없음 / API 오류 → 그대로 진행.

### 3단계: 코드 탐색 및 본문 작성

1. `.github/ISSUE_TEMPLATE/` 해당 템플릿을 Read로 읽어 형식 파악
2. 관련 코드를 탐색하여 연관 파일 경로 포함
3. 템플릿 형식에 맞춰 본문 작성

### 4단계: 로컬 파일 먼저 저장

`doc-output-path.md` 규칙을 따른다. **경로를 직접 조립하지 않고** `get-output-path issue`가 돌려준 `path`를 그대로 쓴다 (산출물 루트는 설정으로 바뀐다). 현재 레포 기준으로 계산되므로 프로젝트 루트에서 부른다.

```bash
cd "{PROJECT_ROOT}" && PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py get-output-path issue --title "{이슈 제목}"
```

- `path` 예: `<산출물 루트>/issue/YYYYMMDD_001_제목.md`
- 등록 전이라 이슈 번호 대신 **그날의 일련번호**(`001`, `002`…)가 붙는다. 이슈 브랜치 위에서 실행해도 그 브랜치 번호를 빌려 쓰지 않는다. `TMP` 접두사는 쓰지 않는다 (`common-rules.md` §이슈 MD 파일명 규칙)
- 제목의 이모지·`[태그]`는 파일명에서 자동으로 빠진다

**저장 직전**: `common-rules.md`의 **파일 저장 직전 자체검토 프로토콜**로 본문 전체를 검토. 민감 정보 발견 시 마스킹.

저장 후 [시작 전 §3]의 `AUTO_APPROVE` / `CONFIG_HAS_KEY`로 분기한다.

#### A. 자동 모드 (`AUTO_APPROVE == true`)

요약과 파일 경로만 표시하고 즉시 4-1 → 5단계로 진행. 응답을 기다리지 않는다.

```
🤖 이 레포는 확인 없이 바로 등록되도록 설정돼 있어 안내드리고 GitHub에 등록합니다.
   (다시 매번 확인받고 싶으시면 "확인받게 해줘"라고 말씀해주세요.)

이슈 파일: {get-output-path 가 돌려준 경로}
제목: ⚙️[Feature][Skills] ...
라벨: status: todo
담당자: {ASSIGNEE}

GitHub에 등록합니다.
```

> 사용자가 "확인받게 해줘"라고 하면 4-1/5단계 전에 config를 갱신(우선순위 1이 있으면 그 값을, 없으면 우선순위 2를 `false`) 후 B 분기로 전환.

#### B. 수동 모드 (`AUTO_APPROVE == false`)

```
이슈 파일을 생성했습니다: {get-output-path 가 돌려준 경로}

제목: ⚙️[Feature][Skills] ...
라벨: status: todo
담당자: {ASSIGNEE}

내용을 확인해주세요. GitHub에 등록할까요?
1. 네, 등록해주세요
2. 제목을 수정하고 싶어요
3. 내용을 수정할게요 (파일 직접 수정 후 다시 요청)
4. 아니요, 로컬 저장만 할게요
```

**사용자 승인 전까지 GitHub API를 절대 호출하지 않는다.**

- **1** → 4-1단계. 단 `CONFIG_HAS_KEY == false`(첫 실행)면 4-1 직전에 [C] 한 번 실행
- **2** → 제목 수정 입력받아 본문 재생성 → 4단계 처음으로
- **3** → 파일 직접 수정 후 재요청 → 4단계 처음으로
- **4** → 로컬 저장만 하고 종료

#### C. 첫 실행 자동화 제안 (B에서 1 선택 + `CONFIG_HAS_KEY == false`, 한 번만)

```
💡 다음 이슈 등록부터 어떻게 진행할까요?

매번 등록 직전에 이슈 내용을 보여드리고 확인받는 방식이 기본입니다.
원하시면 이 확인 단계를 건너뛰고 곧바로 GitHub에 등록되도록 바꿀 수 있습니다.
(중복 검사는 자동 모드에서도 계속 작동합니다.)

1. 이 레포 이슈 등록은 앞으로 확인 없이 바로 진행해주세요
2. 모든 레포 이슈 등록을 앞으로 확인 없이 바로 진행해주세요
3. 지금처럼 매번 이슈 내용 확인받겠습니다
```

응답에 따라 Read/Write로 `config.json` 갱신: **1** → `github.repos[]`의 현 OWNER/REPO 항목에 `issue.auto_approve: true` / **2** → `github.issue.auto_approve: true` / **3** → `github.issue.auto_approve: false`.

> 갱신은 `config-rules.md` §4대로 전체를 Read 후 해당 키만 수정해 Write. PAT·다른 repos 항목을 날리지 않는다.

#### C-2. 담당자 첫 설정 (`ASSIGNEE_HAS_KEY == false`, 한 번만)

4-1 전에 한 번만 묻는다 (config에 담당자가 이미 있으면 건너뜀).

```
🙋 이슈 담당자를 누구로 지정할까요? (앞으로 자동 적용됩니다)
GitHub 사용자명을 알려주세요. (담당자 없이 진행하려면 "없음")
```

- 사용자명 → `github.default_assignee`에 저장, 이번 이슈부터 `ASSIGNEE`로 사용
- "없음" → `github.default_assignee`를 빈 문자열로 저장

### 4-1단계: 최종 중복 확인 (API 호출 직전)

2-1과 같은 `search-issues`를 다시 부른다.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py search-issues {owner} {repo} "{핵심 키워드}"
```

**사실상 동일한 open 이슈** → 즉시 중단. **없음/무관** → 5단계. `closed` 이슈는 중복 아님.

### 5단계: GitHub 이슈 생성 (승인 후)

이슈 본문에는 **제목 헤딩(`# ...`)과 라벨/담당자 메타 블록을 넣지 않는다.** 템플릿 섹션(📝현재 문제점, 🛠️해결 방안 등)만 쓴다. 로컬 `.md` 파일을 `body_file`로 넘기고, `--assignees`에는 [시작 전 §4]의 `ASSIGNEE`를 넘긴다 (미설정이면 생략).

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py create-issue {owner} {repo} "{제목}" "{이슈 본문 .md 절대경로}" "{라벨 csv}" --assignees "{ASSIGNEE}"
```

출력 JSON: `{"number":...,"url":...,"title":...,"assignees":[...]}`. 존재하지 않는 라벨은 자동 필터링되어 422가 나지 않는다. 담당자가 반영되지 않으면 `assignee_warning`이 오며, 이슈는 정상 생성된 것이므로 중단하지 않고 경고만 자연어로 전달한다.

반환된 실제 번호로 로컬 파일명의 일련번호를 rename한다 (예: `20260710_001_제목.md` → `20260710_245_제목.md`).

### 6단계: 브랜치명 즉시 계산

`create-branch-name "{이슈 제목}" {번호}`를 쓰거나 직접 계산한다. 형식 `YYYYMMDD_#{이슈번호}_{정규화된제목}` (예: `20260710_#235_기능추가_github_스킬_통합`).

### 7단계: 커밋 템플릿 계산

`get-commit-template "{이슈 제목}" "{이슈URL}"`을 부르고 출력의 `template`을 **그대로** 쓴다. 직접 조립하지 않는다.
- 형식: `{이슈제목에서 이모지·태그 제거한 순수 내용} : {타입} : {설명} {이슈URL}`
- `{타입}`은 제목 태그에서 추론된다 — 버그면 `fix`, 기능이면 `feat`, 문서면 `docs`. `feat`로 고쳐 쓰지 않는다 (`semver_auto` 레포에서 버그 수정이 minor로 오른다)

### 8단계: 다음 작업 선택지 제시

```
이슈 생성 완료: #{번호} — {제목}
브랜치명: {브랜치명}
이슈 URL: {url}

📝 커밋 메시지 템플릿:
{get-commit-template 의 template 그대로}
(작업 완료 후 /pro-commit 으로 자동 커밋하거나 위 형식으로 직접 커밋하세요)

다음 작업을 선택하세요:
1. 지금 worktree 생성 (/pro-init-worktree)
2. 브랜치만 생성 (현재 디렉토리에서 작업)
3. 현재 브랜치에서 그대로 작업 (브랜치 변경 없음)
4. 나중에 직접 (브랜치명 복사만)
```

- **1** → `/pro-init-worktree` 스킬에 브랜치명을 넘겨 위임한다. raw `git worktree add`를 직접 부르지 않는다 — 위치 규칙, 경로의 `#` 처리, 로컬 설정 파일 복사를 그 스킬이 맡는다
- **2** → `git checkout -b {브랜치명}`. 여러 세션이 같은 트리를 쓰는 레포면 브랜치 전환이 다른 세션도 바꾸므로, 그럴 땐 1을 권한다
- **3** / **4** → git 명령 없이 브랜치명만 출력하고 종료. 레포가 개발 브랜치 직행(예: develop에서 직접 작업)을 기본으로 정했으면 3을 기본 선택지로 안내한다
