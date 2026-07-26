# 이슈 생성 워크플로우 (pro-github 전용)

사용자가 GitHub **이슈를 새로 만들어달라**고 하면(예: "이슈 만들어줘", "버그 리포트 올려줘", "기능 요청 이슈") `pro-github` 스킬이 이 절차를 따른다. 대략적인 설명을 받아 **GitHub 이슈 템플릿에 맞는 제목·본문을 자동 작성**하고, **로컬 파일로 먼저 저장**한 뒤, 사용자 확인(또는 자동 승인 설정)에 따라 **GitHub API로 실제 등록**하고, **즉시 브랜치명을 계산**하여 다음 작업 선택지를 제공한다.

> 조회/수정/댓글/라벨/담당자/PR 등 이슈 "생성 외" 작업은 `pro-github/SKILL.md`의 서브커맨드 호출법을 따른다. 이 문서는 **생성 워크플로우 전용**이다.

## 시작 전

1. `references/common-rules.md`의 **절대 규칙** 적용 (Git 커밋 금지, 민감 정보 보호).

2. **프로젝트 루트 확인**: `PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)`

3. **Config 확인** — `references/config-rules.md` §2~5 절차. config.json은 고정 경로 `{HOME}/.projectops/config/config.json` 한 곳뿐이다 (Read tool로 직접 읽는다. `ls`·`find`로 탐색 금지).

   파일이 존재하면 → `global_pat`, `repos` 추출. **레포 선택 우선순위**:
   1. `git remote get-url origin`으로 현재 레포의 `owner/repo` 추출 → `repos` 배열과 매칭
   2. 매칭 실패 시 → `default: true`인 repo
   3. 없거나 여러 개면 → 번호를 매겨 선택하게 한다

   파일이 없으면 → `global_pat`, `default_assignee`, 첫 repo(owner/repo/name)를 수집해 저장. 저장 형식은 `references/config-rules.md` 참조.

4. **Python 실행 환경**: `references/common-rules.md` §"PYTHON 변수 설정" 패턴 사용 (Windows Store stub 회피).

5. **자동 승인 모드 판정** — config에서 `issue.auto_approve` 값을 결정한다. (키 이름은 하위 호환을 위해 `issue.*` 그대로 유지한다.)

   해석 우선순위 (먼저 발견되는 값 채택):
   1. `github.repos[]` 중 `owner == 현 OWNER && repo == 현 REPO`인 항목의 `issue.auto_approve`
   2. `github.issue.auto_approve` (글로벌 기본값)
   3. 없으면 `false` (안전 default — 수동 승인)

   두 값으로 기억: `AUTO_APPROVE`(boolean), `CONFIG_HAS_KEY`(true면 우선순위 1·2에서 발견, false면 첫 실행).

   > 자동 모드라도 중복 검사(2-1, 4-1)와 open 동일 이슈 발견 시 중단 정책은 그대로 적용된다. auto_approve는 "최종 등록 승인" 게이트만 스킵한다.
   > 사용자에게 노출하는 안내는 자연어로만 한다. "auto_approve", "config.json" 같은 키 이름·경로를 사용자 메시지에 쓰지 않는다.

6. **담당자(assignee) 결정** — config에서 담당자를 결정한다 (auto_approve와 같은 "글로벌 + 레포별 오버라이드 + 첫 실행만 질문" 패턴).

   우선순위:
   1. `github.repos[]`의 현 OWNER/REPO 항목의 `issue.assignee` (레포별 오버라이드)
   2. `github.default_assignee` (글로벌 기본값)
   3. 없으면 미설정 (첫 실행 — 5단계에서 한 번만 질문)

   두 값으로 기억: `ASSIGNEE`, `ASSIGNEE_HAS_KEY`.

   > **핵심 — 사용자 무간섭**: `ASSIGNEE`가 정해져 있으면 묻지 않고 자동 적용, 승인 화면에 "담당자: {ASSIGNEE}"만 표시. `ASSIGNEE_HAS_KEY=false`일 때만 한 번 질문하고 config에 저장 → 이후 영구 자동.

## 허용 이모지+태그 규칙

`.github/ISSUE_TEMPLATE/` 폴더가 존재하면 파일들을 읽어 허용 조합을 파싱한다. 없으면 아래 기본값을 사용한다.

**주요 태그** (타입 결정, 하나만 선택):

| 이모지+태그 | 용도 |
|-------------|------|
| `❗[버그]` | 버그 리포트 |
| `🎨[디자인]` | 디자인/UI 요청 |
| `🔧[기능요청]` | 기능 요청 |
| `⚙️[기능추가]` | 새 기능 추가 |
| `🚀[기능개선]` | 기존 기능 개선 |
| `🔍[시험요청]` | QA/테스트 요청 |

**수식어 태그** (선택적, 주요 태그 앞에 붙임):

| 이모지+태그 | 조건 |
|-------------|------|
| `🔥[긴급]` | 사용자가 "긴급"이라 명시할 때만 |
| `📄[문서]` | 문서 관련일 때 |
| `⌛[~월/일]` | 마감일이 있을 때 |

**규칙**: 이모지와 `[` 사이에 공백 없음. 위 목록에 없는 이모지 사용 금지.

## 절대 금지

- 채팅으로만 이슈 본문을 출력하고 파일 저장을 생략하는 것
- 코드적인 내용 (구현 방법, 코드 예시)
- 허용 목록에 없는 이모지 사용
- `🔥[긴급]` 임의 추가 (사용자가 명시할 때만)
- 담당자 임의 채우기
- 이모지와 `[` 사이 공백
- 이슈 상태(open/closed) 임의 변경 — 사용자가 명시적으로 요청할 때만
- 이슈 라벨 임의 변경 — 사용자가 명시적으로 요청할 때만
- 자동 모드에서 중복 검사(2-1, 4-1) 스킵 — auto_approve라도 중복 검사는 항상 실행. open 동일 이슈 발견 시 무조건 중단
- config 키 이름·파일 경로를 사용자 메시지에 노출

## 프로세스

### 1단계: 이슈 타입 자동 판단

| 타입 | 키워드 | 템플릿 |
|------|--------|--------|
| **버그** | 안 됨, 에러, 깨짐, 오류, 크래시, 장애 | `bug_report` |
| **기능** | 추가, 만들어야, 새로, 구현, 개선, 변경, 요청 | `feature_request` |
| **디자인** | 디자인, UI, UX, 폰트, 색상, 레이아웃 | `design_request` |
| **QA** | 테스트, QA, 시험, 검증, 확인 | `qa_request` |

**기능 세분류**: `🔧[기능요청]`(요청/검토), `⚙️[기능추가]`(완전히 새 기능), `🚀[기능개선]`(기존 개선).

### 2단계: 이슈 제목 생성

```
[이모지+태그][카테고리] 제목 (50자 이내)
```

예시: `⚙️[기능추가][Skills] github 스킬 이슈 편집 서브커맨드 보강`

**제목 문장부호 규칙 (필수)**: 키보드로 바로 못 치는 특수 문장부호는 "AI가 만든 티"가 나므로 제목에서 쓰지 않는다.

- **em dash(`—`), en dash(`–`) 금지.** 부연은 콜론(`:`), 쉼표(`,`), 괄호로 대체.
  - ❌ `스킬 리브랜딩 — 중립화` / ✅ `스킬 리브랜딩: 중립화`
- **가운뎃점(`·`) 금지.** 나열은 쉼표(`,`)나 슬래시(`/`)로 대체.
  - ❌ `옛 이름·워크플로우명 수정` / ✅ `옛 이름, 워크플로우명 수정`
- 일반 하이픈(`-`)은 파일명·버전(`v4.2.0`) 등 원래 표기에 필요할 때만.

### 2-1단계: 중복 이슈 검색 (파일 저장 전)

이슈 제목에서 핵심 키워드를 추출한다 (이모지·`[...]` 태그·특수문자·URL 제거 → 핵심 명사 2~3개).

**인라인 Python 금지.** `github_cli.py`의 `search-issues`를 호출한다. keyword는 마지막 인자로 그대로 넘기며(공백 포함 가능), 내부에서 URL 인코딩한다. **PAT는 자동 로드되므로 `GITHUB_PAT=`는 생략 가능**하다.

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SCRIPTS="$PROJECT_ROOT/skills/pro-github/scripts"; [ -d "$SCRIPTS" ] || SCRIPTS=$(ls -d ~/.claude/plugins/cache/*/projectops/*/skills/pro-github/scripts 2>/dev/null | sort -V | tail -1); cd "$SCRIPTS" || exit 1
PYTHONIOENCODING=utf-8 "$PYTHON" github_cli.py search-issues {owner} {repo} "{핵심 키워드 2~3개}"
```

출력 JSON `{"count":N,"items":[{number,title,url,state,labels}]}`. `state`가 `closed`인 항목은 중복에서 제외. `[ERROR]`가 stderr에 찍히면 중복 검색을 건너뛰고 경고 후 진행.

**판단 기준 (open 이슈만):**
- **사실상 동일**: 즉시 중단.
  ```
  🚫 이미 동일한 이슈가 존재합니다.

  #{number} — {title}
  {html_url}

  새 이슈 생성을 중단합니다. 기존 이슈에서 작업을 이어가세요.
  ```
  출력 후 **종료**.
- **유사하지만 다름**: 경고 후 사용자 확인 (1. 새로 만들기 / 2. 취소). 2면 종료.
- **무관** / 검색 결과 없음 / API 오류: 그대로 진행.

### 3단계: 코드 탐색 및 본문 작성

1. `.github/ISSUE_TEMPLATE/` 해당 템플릿을 Read로 읽어 형식 파악
2. 관련 코드를 탐색하여 연관 파일 경로 포함
3. 템플릿 형식에 맞춰 본문 작성

### 4단계: 로컬 파일 먼저 저장

`references/doc-output-path.md` 규칙을 따른다. 경로를 agent가 직접 계산한다:
- 형식: `{PROJECT_ROOT}/docs/projectops/issue/YYYYMMDD_{이슈번호}_{정규화된제목}.md`
- 이슈 번호는 GitHub 등록 전이므로 임시로 `TMP1`, `TMP2`… 사용 (등록 후 실제 번호로 rename)
- 제목 정규화: `github_cli.py`의 `normalize-title`을 쓰거나 agent가 직접(특수문자 제거, 공백→`_`, 50자 이내)

**저장 직전**: `references/common-rules.md`의 **파일 저장 직전 자체검토 프로토콜**로 본문 전체를 검토. 민감 정보 발견 시 마스킹.

파일 저장 후 [시작 전 §5]의 `AUTO_APPROVE` / `CONFIG_HAS_KEY`로 분기한다.

#### A. 자동 모드 (`AUTO_APPROVE == true`)

요약과 파일 경로만 표시하고 즉시 4-1 → 5단계로 진행. 응답을 기다리지 않는다.

```
🤖 이 레포는 확인 없이 바로 등록되도록 설정돼 있어 안내드리고 GitHub에 등록합니다.
   (다시 매번 확인받고 싶으시면 "확인받게 해줘"라고 말씀해주세요.)

이슈 파일: docs/projectops/issue/20260710_TMP1_제목.md
제목: ⚙️[기능추가][Skills] ...
라벨: 작업전
담당자: {ASSIGNEE}

GitHub에 등록합니다.
```

> 사용자가 "확인받게 해줘"라고 하면 4-1/5단계 전에 config를 갱신(우선순위 1이 있으면 그 값을, 없으면 우선순위 2를 `false`) 후 B 분기로 전환.

#### B. 수동 모드 (`AUTO_APPROVE == false`)

```
이슈 파일을 생성했습니다: docs/projectops/issue/20260710_222_제목.md

제목: ⚙️[기능추가][Skills] ...
라벨: 작업전
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

응답에 따라 Read/Write로 `config.json` 갱신:
- **1** → `github.repos[]`의 현 OWNER/REPO 항목에 `issue.auto_approve: true`
- **2** → `github.issue.auto_approve: true`
- **3** → `github.issue.auto_approve: false`

> 갱신 시 `references/config-rules.md §4`대로 전체를 Read 후 해당 키만 수정해 Write. PAT·다른 repos 항목을 날리지 않는다.

#### C-2. 담당자 첫 설정 (`ASSIGNEE_HAS_KEY == false`, 한 번만)

4-1 전에 한 번만 묻는다 (config에 담당자가 이미 있으면 건너뜀).

```
🙋 이슈 담당자를 누구로 지정할까요? (앞으로 자동 적용됩니다)
GitHub 사용자명을 알려주세요. (담당자 없이 진행하려면 "없음")
```

- 사용자명 → `github.default_assignee`에 저장, 이번 이슈부터 `ASSIGNEE`로 사용
- "없음" → `github.default_assignee`를 빈 문자열로 저장

### 4-1단계: 최종 중복 확인 (API 호출 직전)

2-1과 동일하게 `github_cli.py`의 `search-issues`를 호출한다 (인라인 Python 금지).

```bash
SCRIPTS="$PROJECT_ROOT/skills/pro-github/scripts"; [ -d "$SCRIPTS" ] || SCRIPTS=$(ls -d ~/.claude/plugins/cache/*/projectops/*/skills/pro-github/scripts 2>/dev/null | sort -V | tail -1); cd "$SCRIPTS" || exit 1
PYTHONIOENCODING=utf-8 "$PYTHON" github_cli.py search-issues {owner} {repo} "{핵심 키워드}"
```

**사실상 동일 open 이슈 발견** → 즉시 중단. **없음/무관** → 5단계 진행. `closed` 이슈는 중복 아님.

### 5단계: GitHub 이슈 생성 (승인 후)

GitHub 이슈 본문에는 **제목 헤딩(`# ...`)과 라벨/담당자 메타 블록을 포함하지 않는다.** 템플릿 섹션(📝현재 문제점, 🛠️해결 방안 등)만 작성한다.

**인라인 Python 금지.** `github_cli.py`의 `create-issue`를 호출한다. body는 로컬에 저장한 `.md` 파일(템플릿 섹션만)을 `body_file`로 전달한다. `--assignees`에는 [시작 전 §6]의 `ASSIGNEE`를 넘긴다 (미설정이면 생략).

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SCRIPTS="$PROJECT_ROOT/skills/pro-github/scripts"; [ -d "$SCRIPTS" ] || SCRIPTS=$(ls -d ~/.claude/plugins/cache/*/projectops/*/skills/pro-github/scripts 2>/dev/null | sort -V | tail -1); cd "$SCRIPTS" || exit 1
PYTHONIOENCODING=utf-8 "$PYTHON" github_cli.py create-issue {owner} {repo} "{제목}" "{이슈 본문 .md 절대경로}" "{라벨 csv}" --assignees "{ASSIGNEE}"
```

출력 JSON: `{"number":...,"url":...,"title":...,"assignees":[...]}`. 존재하지 않는 라벨은 자동 필터링되어 422가 나지 않는다. 요청한 담당자가 반영되지 않으면 `assignee_warning`이 들어오며, 이슈는 정상 생성된 것이므로 중단하지 않고 그 경고만 자연어로 전달한다.

반환된 실제 번호로 로컬 파일의 임시 번호(`TMP1` 등)를 rename한다.

### 6단계: 브랜치명 즉시 계산

`github_cli.py`의 `create-branch-name`을 쓰거나 agent가 직접 계산:
- 형식: `YYYYMMDD_#{이슈번호}_{정규화된제목}`
- 예: `20260710_#235_기능추가_github_스킬_통합`

### 7단계: 커밋 템플릿 계산

`github_cli.py`의 `get-commit-template`을 쓰거나 agent가 직접:
- 형식: `{이슈제목에서 이모지·태그 제거한 순수 내용} : feat : {설명} {이슈URL}`

### 8단계: 다음 작업 선택지 제시

```
이슈 생성 완료: #{번호} — {제목}
브랜치명: {브랜치명}
이슈 URL: {url}

📝 커밋 메시지 템플릿:
{순수 내용} : feat : {변경사항 설명} {이슈URL}
(작업 완료 후 /pro-commit 으로 자동 커밋하거나 위 형식으로 직접 커밋하세요)

다음 작업을 선택하세요:
1. 지금 worktree 생성 (../{브랜치명}/)
2. 브랜치만 생성 (현재 디렉토리에서 작업)
3. 현재 브랜치에서 그대로 작업 (브랜치 변경 없음)
4. 나중에 직접 (브랜치명 복사만)
```

- **1** → `git worktree add -b {브랜치명} ../{브랜치명}`
- **2** → `git checkout -b {브랜치명}`
- **3** / **4** → git 명령 없이 브랜치명만 출력하고 종료

## 산출물 저장

`references/doc-output-path.md` 규칙을 따라 `docs/projectops/issue/` 하위에 저장한다 (Step 4에서 처리).
