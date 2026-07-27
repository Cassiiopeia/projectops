# Config Rules

모든 skill의 config 파일 읽기/쓰기는 이 파일의 규칙을 따른다.

---

## 1. Config 파일 경로 구조

config 파일은 **글로벌 단일 파일**로만 관리한다. 스킬이 추가되어도 파일을 새로 만들지 않는다.

```
{HOME}/.projectops/config/config.json
```

`{HOME}`은 OS별로 다르다. 아래 §2에서 확인하는 방법을 따른다.

---

## 2. 홈 디렉토리 확인 (OS별)

config를 읽거나 쓰기 전에 아래 커맨드로 홈 디렉토리를 확인한다:

```bash
echo "$HOME"
```

| OS | 반환 예시 |
|----|-----------|
| macOS | `/Users/username` |
| Linux | `/home/username` |
| Windows (Git Bash) | `/c/Users/username` |
| Windows (PowerShell) | `C:\Users\username` (단, `$HOME` 대신 `$env:USERPROFILE`) |

**agent 판단 규칙:**
- `echo "$HOME"` 결과가 `/c/Users/...` 또는 `C:\Users\...` 형태 → Windows
- `/Users/...` → macOS
- `/home/...` → Linux
- 결과가 비어있으면 `echo "$USERPROFILE"` 로 재시도

---

## 3. Config 읽기

> ⚠️ **config.json은 절대 탐색하지 않는다.** 경로는 `{HOME}/.projectops/config/config.json` **한 곳으로 고정**이다. Read tool로 이 경로를 **바로** 읽는다. `ls`·`find`·glob으로 찾지 마라.
>
> **특히 하네스 설치 경로(`~/.claude/...`, `~/.codex/...`, `~/.gemini/...`, `~/.pi/...`)를 뒤지지 마라.** 각 스킬의 SKILL.md는 *스크립트*(`*_cli.py`) 위치를 찾을 때 이 경로들을 `ls`로 조회한다 — 이건 **스크립트 전용**이며 config.json은 그 안에 **없다.** 그 `ls` 패턴을 config 찾기에 전이시키면 엉뚱한 파일을 잡거나 "config 없음"으로 오판해 이미 등록된 PAT를 사용자에게 다시 묻게 된다 (실제 발생한 사고). **스크립트는 캐시에서 ls로, config는 홈의 고정 경로에서 Read로 — 두 경로를 절대 섞지 않는다.**

agent는 Read tool로 `{HOME}/.projectops/config/config.json`을 읽는다.
(Search·find로 탐색하지 않는다 — 경로가 고정이므로 탐색이 필요 없고, 탐색하면 플러그인 캐시 등 엉뚱한 파일을 잡을 수 있다)

파일이 없으면 → §5 대화형 수집으로 진행한다.

각 스킬은 자신의 `skill_id`에 해당하는 섹션만 읽는다:

```
github 스킬    → config["github"]
synology-expose → config["synology-expose"]
ssh 스킬       → config["ssh"]
```

**github 스킬의 레포 자동 매칭 (읽기 후 즉시 수행):**

```bash
git remote get-url origin 2>/dev/null
```

반환값에서 `owner/repo`를 추출하여 `repos` 배열과 비교한다:
- `https://github.com/owner/repo` → `owner`, `repo` 추출
- `git@github.com:owner/repo.git` → `owner`, `repo` 추출

**레포 선택 우선순위:**
1. git remote URL 매칭 → `repos` 배열 중 `owner`+`repo` 모두 일치하는 항목
2. 매칭 실패 시 → `default: true`인 항목
3. 위 둘 다 없으면 → 번호를 매겨 사용자에게 선택

config에 해당 레포가 없는 경우 → 새 레포 추가 여부를 사용자에게 묻고 §4 절차로 추가한다.

**PAT 우선순위 (레포별 API 호출 시):**
1. 해당 repo 항목의 `pat` 필드가 non-null이면 사용
2. `null`이거나 없으면 `global_pat` fallback

**PAT는 직접 추출하지 않는다 — 표준 도구를 쓴다 (중요):**

과거 agent가 인라인 Python으로 PAT를 꺼내다 `config["github"]["global_pat"]`의
`["github"]` 네임스페이스를 빠뜨려 `KeyError`/`missing_pat`이 반복 발생했다.
PAT 추출은 매번 즉흥 코드로 짜지 말고 아래 두 경로 중 하나만 쓴다:

- **각 skill의 `<scope>_cli.py` 서브커맨드 호출 시** → PAT를 아예 신경 쓰지 않는다.
  `<scope>_cli.py`가 `GITHUB_PAT` 환경변수 → 없으면 `config.json`에서 위 우선순위로 **자동 로드**한다 (`scripts/common/config.py:get_github_pat`).
  `GITHUB_PAT=`를 안 붙여도 동작한다.

- **curl로 직접 호출 시 (긴급용)** → `common.config.get_github_pat` 함수를 사용한다.

  ```bash
  PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
  PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
  PAT=$(PYTHONIOENCODING=utf-8 "$PYTHON" -c "import sys; sys.path.insert(0, '$PROJECT_ROOT/scripts'); from common.config import get_github_pat; print(get_github_pat('{owner}', '{repo}') or '')")
  # PAT가 빈 문자열이면 config 없음 → 이 문서 §2~5 절차로 대화형 등록 안내
  ```

  `get_github_pat`은 위 우선순위(repo별 `pat` → `global_pat`)를 그대로 구현하므로
  agent가 네임스페이스를 직접 다룰 일이 없다.

---

## 4. Config 저장 (쓰기)

agent가 Write tool로 `{HOME}/.projectops/config/config.json`에 저장한다.

**반드시 전체 파일을 Read로 읽은 뒤 수정**하여 덮어쓴다. 기존 다른 섹션을 날리지 않도록 주의한다.

새 섹션 추가 시 기존 파일을 Read로 읽은 뒤 해당 `skill_id` 키를 추가하여 저장한다.

---

## 5. Config 없을 때 — 대화형 수집

파일이 없으면 정보를 하나씩 수집한다. **한 번에 여러 개를 묻지 않는다.**

스킬에 필요한 섹션만 수집한 뒤 §4의 저장 절차를 따른다.

---

## 6. Agent 판단 원칙

- **애매하면 억지 추론 금지** — 즉시 사용자에게 질문
- **한 메시지 = 한 질문** — 여러 항목을 한꺼번에 묻지 않는다
- **이미 준 정보는 다시 묻지 않는다**
- **위험한 작업 실행 전 반드시 확인** — config 덮어쓰기 포함
- PAT, 토큰 등 민감 정보는 `common-rules.md` 마스킹 규칙 적용

---

## 7. Skill별 Config 스키마

모든 스킬의 설정은 단일 `config.json` 안에서 `skill_id`를 키로 구분한다.
전체 구조 예시는 `skills/config.json.example` 참조.

### `github` 섹션

`issue`, `commit`, `changelog-deploy`, `github`, `report` 스킬이 공유한다.

```json
{
  "github": {
    "default_assignee": "GitHub_사용자명",
    "global_pat": "ghp_xxxxxxxxxxxxxxxxxxxx",
    "commit":            { "auto_approve": false },
    "issue":             { "auto_approve": false },
    "changelog_deploy":  { "auto_approve": false },
    "repos": [
      {
        "name": "프로젝트 이름",
        "owner": "GitHub_사용자명_또는_조직명",
        "repo": "저장소명",
        "pat": null,
        "default": true,
        "commit":            { "auto_approve": true },
        "issue":             { "auto_approve": true },
        "changelog_deploy":  { "auto_approve": true, "app_release": true, "head_branch": "develop", "base_branch": "main", "provider": "coderabbit" }
      }
    ]
  }
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `default_assignee` | ✅ | 이슈 기본 담당자 GitHub 사용자명 (글로벌). `pro-github`가 이슈 생성 시 자동 적용한다. 빈 문자열이면 담당자 없이 생성. 누락 시 첫 이슈에서 1회 질문 후 저장 |
| `global_pat` | ✅ | 전체 공용 GitHub PAT (repo + workflow 권한) |
| `commit.auto_approve` | — | commit 스킬의 커밋 메시지 사용자 승인 게이트 자동 통과 여부 (글로벌 기본값). `true`면 제안 메시지 표시 후 즉시 커밋. 누락 시 `false`(수동 승인) |
| `issue.auto_approve` | — | `pro-github` 이슈 생성의 이슈 등록 사용자 승인 게이트 자동 통과 여부 (글로벌 기본값). `true`면 제목·라벨·로컬 파일 경로 표시 후 즉시 GitHub 등록. **중복 검사(2-1, 4-1단계)는 항상 실행** — 자동 모드라도 open 동일 이슈 발견 시 중단. 누락 시 `false`. (키 이름은 하위 호환을 위해 `issue.*` 유지 — pro-issue 통합 후에도 동일 키) |
| `changelog_deploy.auto_approve` | — | changelog-deploy 스킬의 릴리스 노트 사용자 승인 게이트 자동 통과 여부 (글로벌 기본값). `true`면 본문 표시만 하고 즉시 PR 생성. 누락 시 `false` |
| `repos` | ✅ | 사용할 저장소 목록 |
| `repos[].name` | ✅ | 프로젝트 식별 이름 |
| `repos[].owner` | ✅ | GitHub 사용자명 또는 조직명 |
| `repos[].repo` | ✅ | 저장소명 |
| `repos[].pat` | — | 레포별 개별 PAT. `null`이면 `global_pat` 사용 |
| `repos[].default` | — | `true`인 항목이 기본 선택 repo |
| `repos[].{commit,issue,changelog_deploy}.auto_approve` | — | 해당 레포에 한정한 자동 승인 오버라이드. 글로벌 값보다 우선 |
| `repos[].issue.assignee` | — | 이 레포만 다른 이슈 담당자. `default_assignee`(글로벌)보다 우선. 누락 시 글로벌 사용. 사용자가 "이 레포 담당자는 OOO으로" 하면 agent가 저장 |
| `repos[].changelog_deploy.app_release` | — | 이 레포가 앱스토어/플레이스토어 심사로 직결되는 배포인지(앱 심사 인지). `true`면 changelog-deploy 스킬이 릴리스 노트 승인 게이트에 심사 경고 배너를 띄우고 정제를 더 엄격히 적용. **레포별로만** 저장(글로벌 기본값 없음). 누락 시 스킬이 1.5단계에서 자동 감지 후 한 번 확인해 저장. agent가 자연어 응답을 받아 갱신하며 사용자가 직접 편집하지 않는다 |
| `changelog_deploy.head_branch` | — | 릴리스 PR의 head(소스) 브랜치. 레포별(`repos[]`) 우선, 없으면 글로벌(`github.changelog_deploy`). 둘 다 없으면 스킬이 version.yml `deploy_branch` → 폴백 `develop`로 판정 후 기록 |
| `changelog_deploy.base_branch` | — | 릴리스 PR의 base(프로덕션) 브랜치. 우선순위 동일. 없으면 version.yml `default_branch` → 폴백 `main` |
| `changelog_deploy.provider` | — | 릴리스 노트 생성 방식(`coderabbit`\|`commit`\|`github-ai`\|`openai`). 우선순위 동일. 없으면 version.yml `options.changelog.provider` → `.coderabbit.yaml` 존재 여부 → 폴백 `coderabbit`. `coderabbit`/`github-ai`/`openai`는 스킬이 릴리스 노트를 선제 작성, `commit`은 워크플로우 커밋 분석에 위임 선택 가능 |

> `head_branch`/`base_branch`/`provider` 세 키는 changelog-deploy 스킬이 **최초 1회 자동 판정(version.yml·`.coderabbit.yaml` 신호) 후 애매하면 사용자에게 물어 기록**한다. 이후 실행은 config에서 바로 읽어 재질문하지 않는다. **사용자는 직접 편집하지 않으며**, "배포 브랜치 바꿔줘"/"릴리스 노트 방식 바꿔줘" 같은 자연어 발화로 갱신한다.

**PAT 결정 로직:**
```
effective_pat = repo.pat if repo.pat else config["github"].global_pat
```

**자동 승인 결정 로직 (3 스킬 공통, 해석 우선순위):**
```
1. repos[i].{skill_id}.auto_approve   (현 owner/repo 매칭 결과)
2. github.{skill_id}.auto_approve     (글로벌 기본값)
3. false                              (안전 default — 수동 승인)
```

`{skill_id}` = `commit` / `issue` / `changelog_deploy`

> **운영 원칙**: `commit`·`issue`·`changelog_deploy` 옵션은 사용자가 직접 편집하기보다 각 스킬이 자연어 응답("다음부턴 자동으로 진행해주세요" 등)을 받아 자동 갱신하도록 설계됐다. SKILL이 사용자에게 키 이름·파일 경로를 노출하지 않는다.

> **마이그레이션 — 명시적 break**: 이전 키 `changelog_deploy.auto_approve_release_notes`는 더 이상 인식하지 않는다. config에 남아 있어도 무시되며, 자동 모드를 다시 켜려면 1회 토글 발화로 `changelog_deploy.auto_approve: true`를 새로 저장한다.

### `synology-expose` 섹션

`synology-expose` 스킬이 사용한다.

```json
{
  "synology-expose": {
    "instances": [
      {
        "name": "NAS 이름 (예: 집 NAS)",
        "ddns": "your-nas.synology.me",
        "domains": ["example.com"],
        "email": "your@email.com",
        "dns_provider": "cloudflare",
        "default": true
      }
    ]
  }
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `name` | ✅ | NAS 식별 이름 |
| `ddns` | ✅ | Synology DDNS 주소 |
| `domains` | ✅ | 외부 노출에 사용할 도메인 목록 |
| `email` | ✅ | SSL 인증서 발급용 이메일 |
| `dns_provider` | ✅ | DNS 공급자 (예: `cloudflare`, `route53`) |
| `default` | — | 여러 인스턴스 중 기본 선택 여부 |

### `ssh` 섹션

`ssh` 스킬이 사용한다.

```json
{
  "ssh": {
    "instances": [
      {
        "name": "서버 식별 이름",
        "host": "your-server.example.com",
        "port": 22,
        "user": "username",
        "auth": "key",
        "key_path": "~/.ssh/id_rsa",
        "password": null,
        "default": true
      }
    ]
  }
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `name` | ✅ | 서버 식별 이름 |
| `host` | ✅ | 서버 주소 (IP 또는 도메인) |
| `port` | ✅ | SSH 포트 (기본 22) |
| `user` | ✅ | SSH 접속 사용자명 |
| `auth` | ✅ | 인증 방식: `key` 또는 `password` |
| `key_path` | — | `auth: key`일 때 PEM 키 경로 |
| `password` | — | `auth: password`일 때 비밀번호 |
| `default` | — | 여러 인스턴스 중 기본 선택 여부 |

### `output` 섹션 (#525)

산출물 md를 저장하는 스킬(`analyze`·`plan`·`report`·`review`·`note`)이 공유한다.

```json
{
  "output": { "root": "docs/projectops" }
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `root` | — | 산출물 저장 루트. **생략하면 `docs/projectops`** (기존 동작 유지). 상대경로는 저장소 루트 기준, 절대경로도 가능 |

해석은 `scripts/common/paths.py`의 `resolve_output_root()`가 단일 담당한다.
스킬이 경로 문자열을 직접 조립하지 않고 각 스킬 CLI의 `get-output-path`를 거친다 — 상세는 `references/doc-output-path.md`.

---

## 8. 새 스킬에 Config 추가하는 방법

새 스킬이 config가 필요한 경우:

1. `skill_id`(스킬 폴더명)를 키로 `config.json`에 섹션 추가
2. 이 파일(§7)에 스키마 문서화
3. `skills/config.json.example`에 예시 추가
4. SKILL.md에 `references/config-rules.md §2~3` 참조 명시

**절대 별도 config 파일(`skill-name.config.json` 등)을 새로 만들지 않는다.**
