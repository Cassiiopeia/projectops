# Skills 개발 규칙

> **언제 읽나:** `skills/`, `scripts/common/`, `plugins/` 를 건드리거나 스킬 CLI 서브커맨드 · config · 산출물 경로를 추가할 때
> `CLAUDE.md` 에서 옮긴 정본입니다. `CLAUDE.md` 에는 요약과 이 문서로 가는 링크만 있습니다.

### ⚠️ 테스트 코드는 사용자에게 나가지 않는다 (#591)

`skills/` 는 Cursor·GitHub Copilot 설치 소스라 **통째로 `~/.cursor/skills/`·`~/.copilot/skills/` 로 복사된다** (#200).
스킬 CLI 가 import 하는 `scripts/`(common 등)도 옆 `~/.cursor/scripts/`·`~/.copilot/scripts/` 로 함께 복사된다 — 빠지면 CLI 가 import 에서 죽는다.
그래서 `skills/*/tests/`·`scripts/tests/`·`conftest.py`를 거르지 않으면 우리 테스트가 남의 컴퓨터에 쌓인다.
두 어댑터가 함께 쓰는 `src/core/ide/skills-copy.js`의 `SKIP_IN_COPY`·`TEST_PATH`가 막는다.
`scripts/` 의 관리자 전용 파일(`README.md`·`build_troubleshooting.py`·`sync_extras.py`)은 `SHARED_SCRIPTS_DEV_ONLY` 가 뺀다 (#988).
**스킬을 추가하거나 이름을 바꾸면 `scripts/projectops_cli.py`의 `SKILL_CLIS`와 `RESOLVER_REVISION`(+1)을 함께 고친다 (#1080 실사고: 번호를 안 올려 기존 사용자의 고정 진입점이 새 스킬을 `bad_args`로 거부).**
**`scripts/` 최상위에 관리자 전용 파일을 새로 두면 이 목록에 넣는다.** 런타임이 쓰는 항목을 넣으면 설치본 CLI가 import 에서 죽는다.
**스킬에 새 보조 파일을 추가할 때 "이게 스킬을 쓰는 사람에게 필요한가"를 자문한다.**

## Skills 개발 가이드

### 폴더 구조
```
skills/
├── {skill-name}/SKILL.md
├── config.json.example       # 전체 config 구조 예시 (모든 skill_id 섹션 포함)
└── references/
    ├── common-rules.md       # 절대 규칙, 커밋 컨벤션, 작업 시작 프로토콜
    ├── personas.md           # 5 전문가 페르소나 + 6 마인드셋 (harness/PERSONA.md single source) — 로드하는 스킬 없음 (harness 사본)
    ├── approval-and-questions.md # 산출물 skill 8종의 승인 게이트 + 시작 전 핵심 질문 표준 (#526)
    ├── config-rules.md       # config 경로·스키마·읽기/쓰기 표준
    ├── mcp-subcommand-rules.md # skill CLI(<scope>_cli.py) 서브커맨드 MCP-style 설계 표준 (JSON+next, 코드 템플릿)
    ├── doc-output-path.md
    ├── project-detection.md
    ├── code-style-detection.md
    ├── tech-flutter.md
    ├── tech-react.md
    └── tech-spring.md
```

### 핵심 원칙

1. **config는 agent가 Read/Write tool로 직접 처리** — `config-get` CLI 호출 금지
2. **config 경로·스키마는 `references/config-rules.md` 참조** — skill 내 직접 기술 금지
3. **GitHub API는 각 skill의 `<scope>_cli.py` 서브커맨드로 호출** (`scripts/common/gh_client` 경유) — `gh` CLI 금지
4. **OS 호환성**: Python 실행 시 `PYTHON=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)` 패턴 사용
5. **skill 시작 시 필독**: `references/common-rules.md` → (config 필요 시) `references/config-rules.md` → (기술별) `tech-*.md`
5.5. **산출물(md)을 만드는 skill이면** `references/approval-and-questions.md`를 따른다 — 시작 전 핵심 질문, 저장 전 승인 게이트, 첫 실행 1회 자동화 제안. 저장 경로는 각 skill CLI의 `get-output-path`로 받고 직접 조립하지 않는다 (#525·#526)
6. **Python 행동 로직은 재사용 스크립트 파일 + MCP-style 표준** — 아래 "Python 행동 스크립트 표준" 절을 따른다. SKILL.md에 긴 Python heredoc 인라인 금지.

### Python 행동 스크립트 표준 (필수)

스킬이 Python으로 외부 시스템(GitHub API, SSH 등)을 호출할 때 반드시 이 패턴을 따른다.
이 표준은 Windows Git Bash + macOS 양쪽에서 깨지지 않도록 실측 검증된 것이다.

> **skill CLI(`skills/pro-*/scripts/<scope>_cli.py`)에 새 서브커맨드를 추가할 때는 `skills/references/mcp-subcommand-rules.md`를 먼저 읽는다.** 입력 계약·JSON 스키마(`ok`/`verdict`/`summary`/`next`)·gh_client와 command 레이어 분리·테스트 패턴을 코드 템플릿과 체크리스트로 정리해 둔 구체적 구현 레퍼런스다. 모범 사례는 `actions`·`deploy-status` 서브커맨드.

#### 1. 로직은 재사용 스크립트 파일에 둔다

- **진입 파일은 얇게, 서브커맨드는 패키지로, 파일당 450줄.** 진입 `<scope>_cli.py`는 파서·등록만 두고 서브커맨드 구현은 옆 패키지에 둔다 (모범: `skills/pro-launch/scripts/pro_launch/`).
- `skills/{skill-name}/scripts/{name}.py` 에 행동 로직을 고정 파일로 저장한다.
- SKILL.md는 **호출법만** 기술한다 (서브커맨드·인자·환경변수). 긴 Python 코드를 SKILL.md에 인라인하지 않는다.
- 이유: SKILL.md는 LLM이 매번 재입력하는 문서다. redirect strip 같은 핵심 로직을 인라인하면 재입력 시 누락·오타 위험.

#### 2. MCP-style 서브커맨드 — 입력 해석은 agent, 실행은 .py

- .py는 `argparse` 서브커맨드로 **명확한 입력 계약**을 갖는다 (예: `show-run RUN_ID`, `joblog JOB_ID`, `resolve-pr PR_NUM`).
- .py는 URL 파싱·PR→run 추적 같은 **해석을 하지 않는다**. agent가 사용자 입력(URL/PR/브랜치/빈입력)을 해석해 정확한 서브커맨드·인자를 넘긴다.
- SKILL.md에 "이런 입력 → 이런 서브커맨드" 라우팅 규칙을 명시해 agent가 제대로 판단하게 한다.
- 효과: .py는 단독 실행·테스트 가능(MCP tool처럼 예측 가능), agent는 유연하게 입력 해석.

#### 3. 인자는 환경변수로 전달 — heredoc·/tmp·stdin pipe 금지

- 민감값(PAT 등)과 인자는 **환경변수**로 넘긴다. heredoc 본문 보간·`/tmp` 임시파일·`curl | python` stdin pipe 전부 금지.
- 이유 (실측):
  - `/tmp` 경로 → Windows Git Bash에서 깨짐.
  - `curl | python3` → Windows에서 Exit code 49.
  - heredoc `{변수}` 보간 → 한글·특수문자 이스케이프 깨짐.

```bash
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
GH_PAT="..." GH_OWNER="..." GH_REPO="..." \
  PYTHONIOENCODING=utf-8 "$PYTHON" "$PROJECT_ROOT/skills/{skill}/scripts/{name}.py" show-run 12345
```

#### 4. 출력은 언제나 JSON — 내부에 `next` 힌트 필드

- 모든 서브커맨드는 **항상 JSON**을 stdout으로 출력한다 (plain text 모드 없음, `--json` 옵션도 두지 않는다).
- JSON에 `ok`(성공 여부), 데이터 필드, 그리고 **`next`**(agent가 이어서 호출할 다음 서브커맨드 힌트)를 담는다.
- agent는 단일 JSON 형식만 파싱 → 다음 행동을 정확히 판단.

```json
{"ok": true, "run_id": 12345, "conclusion": "failure",
 "failed_jobs": [{"job_id": 678, "name": "build", "failed_steps": ["Flutter build"]}],
 "next": "joblog 678"}
```

#### 5. 표준 라이브러리 우선 — 진짜 목표는 mac/Windows 양쪽 동작 + 내부망 대응

- "의존성 0"이 목표가 아니다. **진짜 목표는 mac·Windows 어디서든 깨지지 않고, 내부망(폐쇄망)에서 `pip install` 불가해도 돌아가는 것**이다.
- 따라서 가능하면 표준 라이브러리(`urllib.request`/`json`/`argparse`)로 해결한다 — 추가 설치 없이 양쪽 OS·내부망에서 바로 동작하기 때문.
- 표준 라이브러리로 안 되는 일이면 **외부 패키지를 당연히 쓴다**. 다만 스크립트 내에서 설치 시도(`pip install ... -q`) + 실패 시 수동 설치 안내를 둬서 내부망에서도 우아하게 처리한다. (예: secret 암호화 PyNaCl)

#### 6. redirect 시 Authorization 헤더 strip (필수 보안·동작)

- GitHub job logs 등 일부 엔드포인트는 Azure Blob(SAS URL)로 302 redirect된다.
- urllib 기본 동작은 `Authorization` 헤더를 redirect 대상까지 전달 → Azure가 `403 AuthenticationFailed`.
- redirect 시 `Authorization` 헤더를 제거하는 핸들러를 반드시 둔다:

```python
class StripAuthRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            new.headers.pop("Authorization", None)
            new.unredirected_hdrs.pop("Authorization", None)
        return new
opener = urllib.request.build_opener(StripAuthRedirect)
```

### config 구조

모든 스킬의 config는 **단일 파일** `~/.projectops/config/config.json` 하나로 관리한다.
skill_id를 키로 각 스킬의 설정을 네임스페이스로 분리한다.

| 스킬 | config 섹션 키 | 비고 |
|------|--------------|------|
| `commit`, `github`, `changelog-deploy`, `report` | `github` | PAT + repos 공유 (이슈 생성 승인/담당자 설정 `issue.*` 키 포함) |
| `synology-expose` | `synology-expose` | NAS 인스턴스 정보 |
| `ssh` | `ssh` | SSH 서버 접속 정보 |
| `presentation` | `presentation` | 새 덱 기본값(언어·제한시간·덱 위치·내보내기 형식) + projects[] |

### 새 스킬에 config 추가하는 방법

1. `skill_id`(스킬 폴더명)를 키로 `config.json`에 섹션 추가
2. `skills/references/config-rules.md` §7에 스키마 문서화
3. `skills/config.json.example`에 예시 추가
4. SKILL.md에 `references/config-rules.md §2~3` 참조 명시

**별도 config 파일(`skill-name.config.json` 등)을 새로 만들지 않는다.**

### skill별 CLI 커맨드 (3-layer 아키텍처)

각 skill이 자체 `scripts/<scope>_cli.py`를 보유한다. 서브커맨드가 많은 CLI는 **진입 파일 + 같은 폴더의 패키지**로 나뉜다 — 진입 파일은 파서와 등록만, 서브커맨드 구현은 패키지(`pro_github/`·`pro_agent_test/`·`pro_ui_design/`·`figma_tools/`·`oss_consult/`·`pro_launch/`, 워크트리는 `scripts/git_worktree/`). 호출 패턴 = self-contained 5줄 (`skills/references/common-rules.md` §"skill별 py 분산 호출" 참조).

| skill | cli 파일 | 주요 서브커맨드 |
|---|---|---|
| github | `skills/pro-github/scripts/github_cli.py` | create-issue, get-issue, get-issues, list-issues, update-issue, close-issue, reopen-issue, search-issues, add-comment, list-comments, edit-comment, delete-comment, list-labels, add-labels, remove-label, set-labels, add-assignees, remove-assignees, create-pr, list-prs, update-pr, get-pr, add-pr-comment, close-pr, reopen-pr, merge-pr, normalize-title, create-branch-name, get-commit-template, explore, create-repo, secrets, actions, upload-image, delete-image, get-output-path |
| commit | `skills/pro-commit/scripts/commit_cli.py` | get-issue-number, get-issue, normalize-title, sanitize-message, get-commit-template, resolve-style |
| report | `skills/pro-report/scripts/report_cli.py` | get-output-path, add-comment |
| review | `skills/pro-review/scripts/review_cli.py` | get-output-path |
| changelog-deploy | `skills/pro-changelog-deploy/scripts/changelog_cli.py` | actions, deploy-status, list-prs, update-pr, create-pr, detect-release-context (`release_language`: 노트 언어는 `version.yml` `language` — 워크플로우와 같은 규칙, 스토어 언어·고정 문구 — #977) |
| testcase | `skills/pro-testcase/scripts/testcase_cli.py` | get-output-path (#525·#623) |
| init-worktree | `skills/pro-init-worktree/scripts/worktree_cli.py` | recall, record (지난번 복사한 로컬 파일 세트를 기억 — #839) |
| figma | `skills/pro-figma/scripts/figma_cli.py` | get-output-path, coverage, assets, conform, diff, screens, fetch, ingest, check-fresh, token (링크 종류 판별·화면 목록 · 저장된 토큰으로 REST 직접 가져오기(MCP 불필요, 과거 버전 `--version`) · diff `--mask-data`·`--mask-node` 로 mock 데이터 영역 제외, `--solids`(한쪽에만 있는 색면)·`--rows`(글줄 높이), conform 자리 검사·시스템 노드 자동 제외, svg-check(렌더러가 버리는 SVG 요소) · MCP 결과 파일 저장 · 시안 변경 확인 · Figma 토큰 등록 — 토큰은 `launch.credentials`의 `provider: figma` 항목을 쓴다, #1017), store-specs, store-check (스토어 이미지 규격 정본 `figma_tools/store_specs.json` · 언어별 판정, #884), store-compose (앱 캡처+문구 > 언어별 스토어 이미지 HTML·렌더 스크립트, 산출물은 `get-output-path`의 run_dir/store 아래에만, #1021), store-upload-plan, store-upload-mark, store-upload-status (콘솔 업로드 체크리스트 · 단계별 기록, 업로드는 pro-launch web, 심사 제출 금지, #1021), store-pages (언어별 랜딩 페이지 + hreflang + sitemap, run_dir/store/site, #1021) |
| agent-test | `skills/pro-agent-test/scripts/e2e_cli.py` | detect, scenario, note, api, other (실행·캡처 명령은 pro-launch 로 넘겨준다 — #631) |
| launch | `skills/pro-launch/scripts/launch_cli.py` | doctor, detect, devices, device, app, web, desktop (PC 화면의 창, #985), render, http, access, db, logs, cred, ssh, local (이 맥 sudo, #784), shrink, mask, redact (올리기 전 이미지 덮기·글자 가리기, #1082), recall, learn, forget, kb (공식 트러블슈팅 search·show·list·propose, #889), journal, harness (사이트·작업별 안내서 폴더 list·show·match·new — 맞는 주소·호스트·앱 식별자·창 이름 응답에 자동 표시, #1023·#1024), get-output-path |
| desktop-control | (자체 CLI 없음) `skills/pro-launch/scripts/launch_cli.py` | `desktop` 그룹을 그대로 쓴다: doctor, setup, session, windows, tree, find, click, type, press, focus, wait, shot |
| ui-design | `skills/pro-ui-design/scripts/ui_design_cli.py` | start, status, stop, choices, tokens, check, capture, decide, decision (#1080), config (show·set·options), get-output-path, board, copy-lint, ascii, rewrite-images (업로드 결과로 본문 이미지 경로 치환 — #974) |
| code-consult | `skills/pro-code-consult/scripts/arch_cli.py` | detect, scan, assets, deps, cochange (같이 바뀌는 파일·숨은 결합, #1109), copies (이름·값·파일 사본 전수 조사, 레포 밖 `--out`만), diff, rule-docs, ledger (check·freeze·tighten), conventions (install·check), install-tests, get-output-path |
| image | `skills/pro-image/scripts/image_cli.py` | providers, harness, kind, run, check, remove-bg, fit, render-svg, board, record, history (#1102) |
| presentation | `skills/pro-presentation/scripts/presentation_cli.py` | start, status, stop, import, recording add, check, export (--pdf · --pptx, 검수 포함), get-output-path (#1097) |
| oss-consult | `skills/pro-oss-consult/scripts/oss_cli.py` | collect, local-facts, list-repos, get-output-path (**사실만 모은다 — 판단은 에이전트**, #644), repo-update, label (레포를 바꾸는 유일한 경로 — `--dry-run`·`before` 기록, **삭제·가시성 변경은 구현하지 않는다**, #660) |

공유 도메인 로직은 `scripts/common/`에 있다 (gh_client, config, paths, title, issue_number, gh_branch, manifest, emit, bootstrap).

> **⚠️ 산출물 경로를 SKILL.md에 박아 쓰지 않는다 (#623 — agent 필독).** 산출물 루트는
> 설정(`output.root`)으로 바뀐다. `docs/projectops/<스킬>/...`를 직접 조립하면 루트를 옮긴
> 팀에서 **조용히 틀린다** — 실제로 `testcase`는 엉뚱한 곳에 쓰고, 읽는 스킬은 빈 폴더를
> 뒤져 "산출물 없음"으로 판단했다. 산출물 경로는 항상 CLI의 `get-output-path`로 받는다.
> 문서에는 산문 언급이 아니라 실제 호출 줄을 적고, 그 서브커맨드가 CLI에 실재하는지 확인한다.
>
> **증거물(스크린샷·덤프·렌더)과 문서(보고서·계획)는 다르다 (#621).** 어느 쪽인지는
> `common/paths.py`의 `EVIDENCE_SKILLS`/`DOCUMENT_SKILLS`가 단독으로 알고, 증거 스킬이면
> `resolve_output_path`가 폴더에 `.gitignore`를 자동으로 심는다 (루트 `.gitignore`는 건드리지
> 않는다). **새 산출물 스킬은 두 집합 중 하나에 반드시 넣는다** — 안 넣으면 테스트가 막는다.

> **⚠️ 선택 위치 인자를 여러 개 줄줄이 두지 않는다 (#622 — agent 필독).** argparse는 값을
> **왼쪽부터** 채우므로, `run_id`/`job_id`/`pr_number`/`branch`처럼 서브커맨드마다 다른 값을
> 각각의 칸으로 두면 **첫 칸에만 들어간다**. `github_cli.py`의 `actions`가 그랬고
> `joblog`·`resolve-pr`·`resolve-branch` 셋이 **문서에 적힌 그대로 불러도 깨졌다**
> (`show-run`·`list-failed`만 우연히 맞아서 오래 안 보였다). 위치 인자는 **하나**로 두고
> 서브커맨드가 해석한다 (`changelog_cli.py`가 처음부터 그 방식이다).

> GitHub API 호출은 각 skill의 `<scope>_cli.py` 서브커맨드 우선. 새 동작이 필요하면 `skills/references/mcp-subcommand-rules.md` 기준으로 `common/gh_client` 헬퍼 + cli 서브커맨드 + 테스트를 추가한다. 신규 skill에 py 필요하면 `skills/pro-skill-creator/templates/python_cli_script.py` 골격을 복사.

### 이슈·완료 댓글의 증거 첨부 (#1082)

이미지·캡처·E2E 결과·로그는 **묻지 않고 첨부하고, 올리기 전에 반드시 직접 본다.** 규칙 정본은 `skills/references/evidence-attach.md`. 가리기 규칙 정본은 `scripts/common/redact.py`이고 extras 사본은 `scripts/sync_extras.py`가 만든다.

### Agent 주의사항

| 상황 | 처리 |
|------|------|
| config 없음 | 대화형 수집 — 억지 추론 금지 |
| repo owner/repo 불명확 | `git remote get-url origin` 추출 → 실패 시 config `github_repos` 참조 |
| GitHub API 401 | PAT 만료 안내 + `/pro-github`에서 재등록 유도 (`references/config-rules.md §2~5`) |
| `gh` CLI 사용 시도 | 금지 — curl로 대체 |
| 공통 워크플로우 수정 | `project-types/common/`과 `.github/workflows/` 루트 **두 곳 동일하게** 유지 |
| GitHub 댓글에 마크다운 표 | `array.join('\n')` 패턴 사용 (template literal 들여쓰기 시 표 깨짐) |

## 알려진 스킬 동작 문제 및 해결 가이드

### 1. `pro-github` 스킬 자동 트리거 실패

**문제**: 사용자가 "PR 올려줘", "댓글 달아줘" 등을 요청해도 `pro-github` 스킬이 자동으로 트리거되지 않고, 다른 스킬(brainstorming 등)이 먼저 실행됨.

**원인**: `superpowers:using-superpowers` 규칙에서 어떤 스킬이든 1% 가능성이면 먼저 호출하도록 강제되는데, `brainstorming` 등 범용 스킬이 더 넓은 설명을 가지고 있어 우선 매칭됨. `pro-github` description의 트리거 키워드("PR 만들어줘", "댓글 달아줘")가 있어도 다른 스킬보다 낮은 우선순위로 처리됨.

**해결 방법 (사용자 관점)**:
- GitHub 작업 시 명시적으로 `/pro-github` 슬래시 커맨드를 입력
- 또는 메시지 앞에 "github:" 접두어 사용 ("github: PR 올려줘")

**해결 방법 (스킬 개발 관점)**:
- `skills/pro-github/SKILL.md`의 description에 더 구체적인 트리거 키워드 추가 필요
- 또는 `pro-github`를 Skill routing 표에 더 명확한 패턴으로 등록
- PR 생성, 이슈 댓글, GitHub API 작업은 **반드시 `/pro-github` 명시 호출** 원칙을 CLAUDE.md에 명시

### 2. `pro-github` 스킬 실행 시 Repo 자동 감지 실패 (워크트리 환경)

**문제**: 스킬이 `git remote get-url origin`으로 현재 디렉토리의 repo를 감지하는데, Claude Code가 **projectops** 레포 컨텍스트에서 실행 중이면 `TEAM-ROMROM/RomRom-BE`가 아닌 `Cassiiopeia/projectops`를 origin으로 잡음.

**원인**: 작업 대상 레포(RomRom-BE)가 별도 워크트리에 있거나, 현재 Claude Code 세션의 primary working directory가 다른 레포인 경우 발생.

**해결 방법**:
- 스킬 호출 시 대상 레포를 명시: `/pro-github TEAM-ROMROM/RomRom-BE 이슈 #653 PR 생성`
- config의 `repos` 목록에 등록된 레포는 이름으로 지정 가능: "RomRom-BE PR 올려줘"

### 3. Windows 환경 Python `urllib` 에러 (Exit code 49)

**문제**: `curl ... | python3 -c "..."` 파이프라인에서 `Exit code 49` 오류 발생. Python이 정상 설치되어 있어도 bash 파이프에서 python3 경로 인식 실패.

**원인**: Windows Git Bash 환경에서 `python3` 명령이 Windows Store python stub을 가리키거나, 파이프 stdin 처리 방식 차이.

**해결 방법 (스킬 개선 필요)**:
- Windows 환경에서 GitHub API JSON 파싱은 `curl | python3 -c` 대신 **PowerShell `Invoke-RestMethod`** 사용
- 또는 curl 응답을 파일로 저장 후 파싱: `curl ... -o /tmp/out.json && python3 /tmp/out.json`
- `skills/pro-github/SKILL.md`에 Windows 대응 PowerShell 코드블록 추가 필요

**임시 해결**: Claude가 PowerShell tool을 직접 사용하여 `Invoke-RestMethod`로 GitHub API 호출

### 4. PR head 브랜치명 422 오류 (한글 브랜치명)

**문제**: 브랜치명에 한글이 포함된 경우(`20260420_#653_FCM_푸시_페이로드에_라우팅용_데이터_포함_필요`) GitHub API PR 생성 시 `422 Validation Failed: head invalid` 오류.

**원인**: PowerShell `ConvertTo-Json`이 한글 포함 문자열을 올바르게 인코딩하지 못하거나, GitHub API가 URL-encoded 브랜치명을 다르게 처리.

**해결 방법**:
- PR 생성 전 실제 remote 브랜치 존재 여부를 먼저 확인: `git ls-remote origin "브랜치명"`
- 브랜치명이 push되어 있는지 확인 후 API 호출
- `head`에 `owner:branch` 형식 사용: `"TEAM-ROMROM:브랜치명"`
