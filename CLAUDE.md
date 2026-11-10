# Projectops

완전 자동화된 GitHub 프로젝트 관리 템플릿

---

## ⚠️ 작업 브랜치 규칙 (agent 필독)

**이 프로젝트는 `develop` 브랜치에서 직접 작업하는 것을 기본값으로 한다. `main`은 프로덕션(default) — 직접 커밋·push 금지.**

- 별도 지시가 없으면 feature 브랜치를 만들지 말고 `develop`에서 작업·커밋·푸시한다.
- `develop` push 전에는 **항상 `git pull --rebase origin develop`** 으로 먼저 동기화한다 (릴리스 시 버전 확정 커밋이 develop에 추가되므로 로컬이 뒤처지기 쉽다).
- 릴리스(배포)는 develop→main PR로만 진행한다 (`/pro-changelog-deploy`). main 직접 push는 안전망(VERSION-CONTROL 가드)이 버전만 보전할 뿐 지원 경로가 아니다.
- `git push`는 **사용자가 명시적으로 요청한 경우에만** 실행한다.
- 사용자가 명시적으로 브랜치 작업을 요청한 경우에만 feature 브랜치를 사용한다.
- 커밋은 **`/pro-commit`을 사용한다.** 브랜치명에서 이슈 번호를 뽑아 컨벤션에 맞는 메시지를 만들고, 스테이징 대상도 함께 확인시켜 준다.

### 여러 에이전트가 동시에 작업한다 (agent 필독)

**여러 Claude Code 세션이 같은 `develop`에서 동시에 작업한다.** 각 세션은 서로의 존재나
작업 내용을 알지 못한다. 내가 만들지 않은 변경이 언제든 작업트리에 나타날 수 있다는
전제로 움직인다.

| 상황 | 대응 |
|---|---|
| 작업 시작 전 | `git pull --rebase origin develop`로 최신 상태를 먼저 받는다 |
| 커밋 전 | `git status`로 **내가 만들지 않은 변경**이 섞였는지 확인한다 |
| 스테이징 | `git add -A`보다 **내가 건드린 경로만** 명시해 담는다 |
| 브랜치가 바뀌어 있음 | 다른 세션이 옮긴 것일 수 있다. 임의로 되돌리지 말고 현재 브랜치를 존중한다 |
| 푸시 거부(non-fast-forward) | 강제 푸시하지 않는다. rebase로 통합한 뒤 다시 푸시한다 |

**금지**

- `git push --force` / `--force-with-lease` — 다른 세션의 커밋이 사라진다
- `git checkout .` · `git reset --hard` — 다른 세션의 미커밋 작업을 날린다
- 내 작업과 무관한 파일을 함께 커밋하는 것 — 원인 추적이 불가능해진다

의도를 모르는 변경이 작업트리에 있으면 **건드리지 말고 그대로 둔다.** 내 변경만 커밋하고
나머지는 그 세션이 처리하도록 남겨두는 것이 안전하다.

### 브랜치 3개념 (agent·마법사 필독 — #482)

혼동 주의: 프로젝트에는 브랜치가 **3개념**이 있고, version.yml 필드명이 직관과 어긋난다.

| 개념 | 뜻 | version.yml 필드 | 표준값 |
|------|-----|-----------------|--------|
| **기본(배포) 브랜치** | 레포 default·프로덕션. push되면 배포가 도는 곳 | `default_branch` | `main` |
| **개발(릴리스 소스) 브랜치** | 개발을 모아 기본 브랜치로 올리는 릴리스 PR의 head | `development_branch` (구 `deploy_branch`) | `develop` |
| 배포 트리거 브랜치 (선택) | 푸시되면 **배포 워크플로**가 도는 곳. 기본 브랜치와 나눌 때만 둔다 (develop > main > deploy) | `metadata.template.options.deploy_trigger_branch` | 없음 = 기본 브랜치 |
| 이슈 브랜치 | 작업 단위 (`YYYYMMDD_#번호_제목`) | — | — |

> ⚠️ **키 이름은 `development_branch`가 정본이다 (#915).** 구 이름 `deploy_branch`는 "배포 브랜치"로 오독되는 이름이라 정본에서 내렸고, 하위호환용으로만 남는다.
> - **읽기**: 모든 소비자가 `development_branch` → 없으면 `deploy_branch` → 없으면 `develop` 순으로 읽는다 (`src/core/version-yml.js` `readDevelopmentBranch`, `changelog_cli.py` `_parse_release_branches`).
> - **쓰기**: 생성기는 두 키를 **같은 값으로 함께** 쓴다 — 구 키만 읽는 구버전 스킬(플러그인은 레포와 따로 업데이트된다)이 조용히 `develop`로 폴백하지 않게 하기 위해서다. 업데이트(마법사 재실행)가 구 키만 있는 파일을 두 키로 다시 쓴다.
> - 워크플로우는 런타임에 이 키를 읽지 않는다 (설치 시 브랜치명을 치환해 넣는다).
> - 사용자 노출 문구에서 이 브랜치를 "배포 브랜치"라 부르지 말고 "개발(릴리스 소스) 브랜치"로 칭한다. CLI 플래그 `--deploy-branch`와 내부 변수명 `deployBranch`는 그대로다.

---

## ⚠️ 이슈 처리 규칙 (agent 필독)

**이 프로젝트는 이슈가 완료되면 완료 라벨을 붙이고 이슈를 닫는다(close).** (2026-10-10 소유자 결정으로 변경 — 이전엔 닫지 않고 라벨만 바꿨다.)

- 작업이 끝나면 이슈 상태 라벨을 **`status: done`**(기존 한글 레포는 `작업완료`)으로 바꾼 뒤 **이슈를 닫는다.**
  `finish-issue {owner} {repo} {번호} [--outcome done|cancelled|in-progress]`로 한다 — 상태 라벨만 바꾸고(`type:`·`area:` 등 다른 라벨 유지) 닫는다.
  `set-labels`는 라벨 **전체를 교체**하므로 `set-labels ... "status: done"`만 넘기면 다른 라벨이 전부 지워진다. `add-labels`만 쓰면 이전 상태 라벨이 남아 상태가 두 개가 된다.
- **완료 기준을 지킨다** — 구현이 main(또는 개발 브랜치)에 반영되고, 검증과 보고서(`/pro-report`)까지 끝난 것만 닫는다.
  사용자가 특정 이슈를 **명시적으로 완료 처리하라고 하면** 이 기준을 다시 따지지 않고 처리한다.
  남은 하위 작업이 있으면 닫지 않고 `status: in progress`로 둔다. 취소된 작업은 `status: cancelled`와 함께 닫는다.
- 라벨 변경과 close는 `/pro-github`(`github_cli.py finish-issue`)로 처리한다. 일부 단계만 실패하면 `failed_steps`의 단계만 `set-labels`(기존 라벨에서 상태만 바꾼 전체 목록) / `close-issue`로 다시 한다.
- **릴리스 워크플로우도 닫는다 (#771, `close_on_release`).** 완료 라벨이 붙은 이슈 중 릴리스 구간 커밋이 URL로 참조한 것을 닫는다. 에이전트가 먼저 닫아도 충돌하지 않는다(이미 닫힌 이슈는 건너뛴다). 이 저장소는 `version.yml`에서 켜져 있다.
- **업데이트는 사용자가 지운·제외한 워크플로우를 되살리지 않는다 (#810).** baseline에 있는데 없는 파일, `options.excluded_workflows`에 적힌 파일, 개발 브랜치가 원격에 없는데 `develop`에서만 도는 파일은 건너뛰고 `incoming/`에 사본을 남긴다. 새 조건부 설치 경로를 추가하면 `copy/workflows.js`의 `skipNew` 게이트를 거치게 한다.
- **상태 라벨은 영문 표준(`status: todo` 등)과 기존 한글(`작업전` 등)을 둘 다 쓴다 (#776).** `label_style`이 표기를 정하고(신규 `en`, 기존 `ko` 유지), 스킬 공통 라벨 함수와 Projects 동기화는 두 표기를 서로 바꿔 인식한다.

---

## ⚠️ 건드리기 전에 읽을 문서 (agent 필독)

**아래 표의 대상을 수정하기 전에 해당 문서를 먼저 Read 한다.** 이 파일에는 모든 작업에 걸리는 규칙만 있고, 영역별 규칙은 문서로 옮겼다.
각 줄의 사고는 그 문서를 안 읽고 고쳐서 실제로 났던 것이다.

| 건드리는 것 | 먼저 읽을 문서 | 안 읽고 고치면 났던 사고 |
|---|---|---|
| 워크플로우 YAML (`.github/workflows/`, `project-types/`), 배포/publish 축, 댓글 트리거, 이슈·PR 템플릿 | [`docs/architecture/agent/workflows.md`](docs/architecture/agent/workflows.md) | `permissions:` 누락으로 댓글 스텝 실패(#595) · 없는 fastlane lane 호출(#601) · 빌드 플래그 한 층만 적용(#603) · 리네임 후 구 워크플로가 계속 실행(#470) · 공통 워크플로 원본과 복사본 불일치 · 로컬 YAML 파서 오류를 실제 고장으로 오판 |
| Flutter 마법사 (`.github/util/flutter/`) | [`docs/architecture/agent/wizards.md`](docs/architecture/agent/wizards.md) | 공통 유틸 재정의로 정본 무력화 · 로드 순서 뒤바뀜 · `check-consistency.py` 미실행(#521) |
| `.github/scripts/` (버전 · 체인지로그 · 빌드 번호 · 이슈 헬퍼), `.sh`, 레포 루트의 템플릿 전용 파일 | [`docs/architecture/agent/scripts.md`](docs/architecture/agent/scripts.md) | 기본 경로에 과금 요소(#569) · macOS bash 3.2 에서만 깨짐(#415 · #418) · 템플릿 전용 파일을 한 곳에만 등록 · 모델명에 버전을 박아 404(#566) |
| `src/` CLI · 마법사 (옵션, 실행 기록, breaking changes), 문서·GIF 언어, 한글 줄 예산 | [`docs/architecture/agent/installer.md`](docs/architecture/agent/installer.md) | 옵션 정본과 코드 불일치(#851) · `trace.emit` 오타로 기록 통째 누락(#561) · 완료 화면이 로그에서 빠짐 |
| `skills/`, `scripts/common/`, `plugins/`, 스킬 CLI · config · 산출물 경로 | [`docs/architecture/agent/skills.md`](docs/architecture/agent/skills.md) | `SKILL_CLIS` · `RESOLVER_REVISION` 미갱신(#1080) · 산출물 경로 하드코딩(#623) · 선택 위치 인자 여러 개(#622) · 테스트 파일이 사용자 PC 로 복사(#591) |

- 이 표에 없는 새 영역 규칙은 이 파일이 아니라 위 문서 중 맞는 곳에 쓴다. 이 파일에는 한 줄 요약과 링크만 더한다.
- 스킬 CLI 를 고칠 때의 "Python 행동 스크립트 표준"은 `skills.md`, "템플릿 전용 파일 추가" 규칙은 `scripts.md` 에 있다.

---

## 프로젝트 개요

### 지원 프로젝트 타입
| 타입 | 설명 | 버전 동기화 파일 |
|------|------|-----------------|
| `spring` | Spring Boot | `build.gradle` |
| `flutter` | Flutter | `pubspec.yaml` |
| `react` | React.js / Next.js | `package.json` |
| `node` | Node.js | `package.json` |
| `python` | FastAPI/Django | `pyproject.toml` |
| `react-native` | React Native CLI | `Info.plist` + `build.gradle` |
| `react-native-expo` | Expo | `app.json` |
| `basic` | 범용 | `version.yml`만 |

> **멀티타입**: 단일 레포에 여러 타입 공존 시 `--type spring,react,python` csv로 지정. `version.yml`의 `project_types` 배열에 저장되며, 첫 항목이 primary 타입이다 (단수 `project_type` 키는 v4.1.0에서 제거됨 — SSOT).
>
> **모노레포 경로**: 타입별 프로젝트가 서브폴더에 있으면(예: `app/`, `client/`, `ai/`) `version.yml`의 `project_paths` 맵(타입 → 레포 루트 기준 상대경로)으로 지정한다. integrator가 통합 시 마커 파일(`pubspec.yaml`·`package.json`·`pyproject.toml`·`build.gradle` 등)을 자동 감지·확인하며, 키가 없으면 루트 기준(기존 동작 100% 유지). 비대화형은 `--paths "flutter=app,react=client"`(`.ps1`은 `-Paths`). `version_manager.sh`가 이 경로를 따라 서브폴더 버전 파일을 동기화하므로, `PROJECT-COMMON-VERSION-CONTROL` 워크플로우는 무수정으로 모노레포를 커버한다.

---

## 폴더 구조

```
projectops/
├── .github/
│   ├── workflows/
│   │   ├── PROJECT-TEMPLATE-INITIALIZER.yaml
│   │   ├── PROJECT-COMMON-*.yaml
│   │   └── project-types/
│   │       ├── common/          # 공통 원본 (+ secret-backup/ opt-in, deploy/vercel/ 배포타겟)
│   │       ├── flutter/         # Flutter 전용 (스토어 배포 워크플로우 루트 포함)
│   │       ├── spring/          # Spring 전용 (server-deploy/ + publish/{nexus,github-packages}/)
│   │       ├── python/          # Python 전용 (CI 루트 + server-deploy/)
│   │       ├── react/           # React/Next.js 공용 (next 타입은 v4.1.0에서 흡수됨)
│   │       └── node/            # Node 전용 (publish/npm/)
│   ├── scripts/
│   │   ├── version_manager.sh    # + version_manager.py (실 로직, #448)
│   │   ├── changelog_manager.py
│   │   ├── truncate_release_notes.sh  # + .py (실 로직, #448)
│   │   └── template_initializer.sh
│   ├── util/
│   │   ├── flutter/
│   │   │   ├── playstore-wizard/
│   │   │   ├── testflight-wizard/
│   │   │   ├── firebase-wizard/
│   │   │   └── oauth-wizard/          # Kakao·Google 로그인 (#156)
│   │   └── common/
│   │       ├── projects-sync-wizard/
│   │       ├── github-projects-sync-worker/
│   │       └── github-secrets-converter/
│   ├── ISSUE_TEMPLATE/
│   └── PULL_REQUEST_TEMPLATE.md
├── .claude-plugin/              # 플러그인 매니페스트
├── skills/                      # 플러그인 Skills (마켓플레이스 전용)
├── scripts/                     # 플러그인 Scripts (마켓플레이스 전용)
├── .cursor/skills/
├── docs/                        # 상세 문서
├── version.yml
└── CHANGELOG.md / CHANGELOG.json
```

---

## 모든 작업 공통 규칙

### ⚠️ Windows는 cp949와 비ASCII 경로까지 봐야 검증이다 (agent 필독)

**영문 경로와 UTF-8 모드로 통과한 것은 Windows 검증이 아니다.** 일반 사용자 환경은 시스템 코드페이지가 cp949이고 폴더 이름에 한글과 공백이 있다.

| 함정 | 증상 | 지키는 방법 |
|---|---|---|
| `fs.cpSync` + 비ASCII 경로 (Node 22 이상) | 메시지 없이 프로세스 종료, 임시 폴더 잔존 | `fsutil.copyPathSync`. 규칙 `no-fs-cpsync` |
| `subprocess.run(text=True)`만 쓰기 | 한글 출력에서 `stdout`이 `None`, 다음 줄에서 크래시 | git은 `encoding="utf-8", errors="replace"`, 그 외 `errors="replace"`. 규칙 `no-subprocess-text-without-errors` |
| Windows용 안내 명령에 `&&` | PowerShell 5.1 파싱 오류 | `;`로 잇는다 |

- **`PYTHONUTF8=1`이 켜진 개발 PC에서는 위 결함이 전부 숨는다.** 확인할 때 `unset PYTHONUTF8 PYTHONIOENCODING`으로 재현한다.
- 전역 git `core.longpaths`도 마찬가지다. 새 사용자처럼 빈 `HOME`으로 돌려 본다.
- 스모크(`matrix-smoke`)는 3 OS, Node 20과 24에서 비ASCII 공백 경로 설치까지 돈다.

### ⚠️ 테스트는 감시용 5개만 둔다 (agent 필독)

AI가 작업마다 쌓은 테스트(약 250개 파일, 3만 줄)를 걷어 내고, **여러 파일에 흩어진 약속이 서로 맞는지 보는 감시 검사만** 남겼다.
사람이 눈으로 놓치는 것만 잡고, 작고 빠르다.

| 파일 | 지키는 것 |
|---|---|
| `test/rename-consistency.test.js` | 스킬 개수·목록이 폴더 ↔ 매니페스트 ↔ README·CLAUDE.md에서 같다 |
| `test/options-schema.test.js` | CLI 플래그·`version.yml` 옵션이 정본(`src/core/options-schema.js`)과 같다 |
| `scripts/tests/test_skill_docs.py` | 스킬 description이 짧고(300자) 영어다 |
| `scripts/tests/test_korean_line_budget.py` | 영문 표면의 한글 줄이 늘지 않는다 (아래 절) |
| `.github/scripts/test/test_workflow_permissions.py` | 모든 워크플로우가 `permissions:`를 선언한다 |

- **새 테스트 파일을 커밋하지 않는다.** 구현 확인은 스크래치 폴더의 임시 테스트나 직접 실행으로 하고 지운다.
- 감시 검사를 더 두려면 "여러 파일의 약속이 어긋나는 것을 사람이 놓친 실제 사고"가 있을 때만 사용자와 상의한다.
- `PROJECT-TEMPLATE-CI`: develop은 ubuntu 1대에서 위 5개 + 마법사 정합성(`check-consistency.py`) + CLI 스모크, main은 3 OS에서 CLI 스모크(macOS bash 3.2·Windows `.cmd` 차이 #415·#418).

---

## Skills (Claude Code 플러그인)

**플러그인명**: `projectops`

```bash
claude plugin marketplace add Cassiiopeia/projectops
claude plugin install projectops@projectops-marketplace --scope user
```

> 설계·계획·구현은 이 플러그인이 아니라 `superpowers`(brainstorming → writing-plans → executing-plans)가 맡는다. 아래 표(코어 18종 + extras 3종)에는 분석·계획·구현 스킬이 없다.

| 명령어 | 용도 |
|--------|------|
| `review` | 코드 리뷰 |
| `testcase` | QA 테스트케이스 |
| `init-worktree` | Git worktree 생성 |
| `commit` | 이슈 기반 커밋 자동화 |
| `github` | GitHub 전반: 이슈 생성/조회/수정/댓글/라벨/담당자, PR 생성/머지/조회, 레포 탐색, Actions 로그, Secret 관리, **이미지 첨부**(이슈 본문·댓글·PR) |
| `report` | 구현 보고서 생성 |
| `changelog-deploy` | develop push → main으로 릴리스 PR(deploy PR) → 버전 확정 + automerge / automerge 실패 시 재트리거 |
| `synology-expose` | 시놀로지 서비스 외부 노출 가이드 (**extras 선택 플러그인** `projectops-extras` — `plugins/projectops-extras/`, 공유 문서 사본은 `scripts/sync_extras.py`로 동기화) |
| `code-consult` | **AI가 짠 코드 관리** (#1107에서 extras → 코어) — 코딩 규칙 기준 점검·한 항목씩 리팩터링(전후 실행 대조)·변경분 검사(낡은 주석·중복)·위반 동결 목록(`docs/architecture/rules/`, 줄을 지울 수만 있음). CLI `arch_cli.py`는 표준 라이브러리 전용이고 `scripts/common`을 쓰지 않는다 (#867) |
| `skill-bug` | **projectops 스킬 버그 보고** (**extras**) — 어느 레포 세션에서든 의심되면 불러, 세션 기록에서 명령·결과·흐름·로그·스크린샷을 모아 개인정보를 지우고 `Cassiiopeia/projectops`에 이슈(같은 이슈 있으면 댓글)로 묻지 않고 올린 뒤 하던 일로 돌아간다. 판정·수정은 하지 않는다 (CLI `bug_cli.py`). Claude Code에서는 extras 훅(`plugins/projectops-extras/hooks/skill_bug_watch.py`, 규칙 정본 `skill_bug_rules.py`)이 모든 pro- CLI의 실패 후 우회(스킬별 우회 표)·도구가 답한 기능 없음·같은 사용법 오류 2회·같은 실패 3회·CLI 내부 예외를 잡아 백그라운드 서브에이전트로 자동 보고시키고(세션당 3건, `skill-bug.auto_report: false`로 끔), `skill_bug_notice.ts`가 토스트를 띄운다 (#997). 자동 보고 본문은 이슈만 받은 에이전트가 재현·수정할 수 있게 `bug_cli.py alarm`·`excerpt --tool-use-id`·`context`가 모은 사실(원본 응답·앞뒤 흐름·환경)로 채운다 (#1000) |
| `disk-cleanup` | **디스크 용량 정리** (**extras**, macOS·Windows·Linux, 스택 무관 — 알려진 위치표 + 홈 아래 큰 폴더를 크기로 찾는 `largest`) — 읽기 전용 `scan` 먼저, safe·decide·keep 3단계로 나눠 safe만 한 번 확인 후 정리, decide(열린 이슈 worktree·DerivedData·Gradle 캐시·에뮬레이터)는 사용자가 이름을 댈 때만. worktree 제거는 GitHub에서 닫힘 확인 > 사용 중·최근 활동 거절 > 백업(패치·무시된 .env 포함) > `git worktree remove`, 브랜치 유지. 모든 삭제는 `disk_cli.py` 게이트를 거치고 `--yes` 없으면 계획만 (#1091) |
| `ssh` | 원격 서버 SSH 접속 및 명령 실행 (AWS EC2, 시놀로지 NAS, Linux 서버 등) |
| `skill-creator` | skill 생성/리뷰/개선 (CREATE·REVIEW·IMPROVE 3모드) |
| `agent-test` | **앱·웹·서버를 실제로 실행해 밟는다** (E2E·증적) — 문서만 쓰는 `testcase`와 다르다 |
| `figma` | **시안 → 코드 → 대조** 한 묶음. 덤프 항목을 세어 작업 목록으로 삼고, 옮긴 뒤 픽셀로 맞댄다 (#619에서 옮기기·대조를 `figma-verify`로 합쳤고, #854에서 이름을 `figma`로 되돌렸다) |
| `launch` | **능력 스킬** — 앱·웹·서버를 띄우고 조작하고 찍는다. 다른 스킬이 `launch_cli.py` 를 스크립트로 부른다 (#629) |
| `desktop-control` | **이 컴퓨터 화면의 프로그램 조작** (웹 페이지·에뮬레이터가 아닌 설치 마법사·OS 대화상자·데스크톱 앱). 요소를 읽고, 마우스를 움직이지 않고 누르고, 설치 전에는 묻고, 보안 확인 창은 사용자에게 넘긴다. `launch`의 `desktop` 명령 묶음 위에 얹은 절차 스킬이라 자체 CLI가 없다. 지금은 Windows만 (macOS는 #985) |
| `ui-design` | **시안을 로컬 주소에 띄워 비교하고 고른다** (#1080) — 레포 토큰·글꼴 반영, 애니메이션 비교, 여러 화면 연결 프로토타입, PNG·GIF 이슈 공유, 안 되면 디자이너 요청서(#634). 판단과 시안 제작은 에이전트, `ui_design_cli.py`는 서버·사실 수집·캡처만. 설정 `ui-design` 섹션 + 옵션 표(`pro_ui_design/options.py`), 프로젝트 지식은 레포 범위 하네스 `ui-design`, 스킬 연결은 `decision.json` |
| `image` | **프로젝트 화풍에 맞는 이미지 에셋 생성** (#1102) — 에이전트가 레포 하네스(`docs/image-harness/`: STYLE·캐릭터·종류 가이드·참조·기록)로 요청을 브리프·영어 프롬프트로 바꾸고, 이미지 도구는 우선순위(기본 codex 구독 > antigravity > claude-vector SVG, `image.priority`·`image.providers`로 추가)로 고른다. `image_cli.py`는 실행·결과 수거·PNG 변환·배경 제거(가짜 체크무늬·키 컬러)·크기 맞춤·비교판·기록만, 표준 라이브러리 전용(Pillow 있으면 사용). Codex는 ChatGPT 구독 로그인만 허용(API 키 환경변수 제거) |
| `presentation` | **발표 덱을 HTML로 짓고 말로 연습한다** (#1097) — 덱 폴더(장마다 slide.html·script.md·notes.md·takes.md, 빌드 없음), 장별 말하기 코칭 하네스(`references/coaching.md`, 사용자 방향성은 덱 `memory.md` + `~/.projectops/presentation/memory.md`), 자동 새로고침 연습 화면, 녹화 자막으로 장별 시간 비교, PDF·글자 PPT 내보내기와 검수. 코칭·구간 판단은 에이전트, `presentation_cli.py`는 서버·가져오기·자막·검사·내보내기만 |
| `oss-consult` | **오픈소스 컨설팅** — 레포 성격을 판별하고 6축(첫인상·가치 증명·커뮤니티·코드 확장성·법적 안전·장기 운영)으로 깐깐하게 채점, 성숙도 단계와 선행 조건을 짚고 승인받은 것을 고친다. 단일 레포·전체 일괄 (#644) |

---

## Skill routing

이 프로젝트에서 사용 가능한 스킬 호출 규칙:

| 요청 유형 | 호출 스킬 |
|----------|----------|
| **이슈 만들어줘, 이슈 등록, 버그 리포트, PR 생성, PR 올려줘, PR 머지, 이슈 댓글, 댓글 달아줘/수정/삭제, 이슈 확인, 이슈 닫기, 라벨 추가/제거, 담당자 추가, PR 조회, GitHub API** | **`pro-github` ← 최우선 트리거** |
| 뭔가 안 됨, 버그, 장애, 원인 파악 | `superpowers:systematic-debugging` |
| 코드 리뷰 | `pro-review` |
| QA 테스트케이스 | `pro-testcase` |
| 이슈 작성 / 이슈 생성 | `pro-github` (이슈 생성 워크플로우 흡수) |
| 커밋 | `pro-commit` |
| 배포 / automerge 실패 재트리거 | `pro-changelog-deploy` |
| 보고서 | `pro-report` |
| 원격 서버 SSH 접속, 로그/상태 확인 | `pro-ssh` |
| **실제로 테스트해줘, 에뮬레이터·시뮬레이터·브라우저로 확인, E2E, 끝까지 밟아줘** | `pro-agent-test` |
| **에뮬레이터 띄워서 찍어줘, 시뮬레이터 스크린샷, 브라우저로 캡처, 모바일 폭으로·빈 목록·500 화면 찍어줘** | `pro-launch` |
| **시안 몇 개 보여줘, 애니메이션 시안 비교, 이 흐름 눌러 보게 해줘, 시안 이슈에 올려줘, 디자인 요청해줘, 디자이너한테 보낼 거 만들어줘, 빈 화면·에러 화면도 그려 달라고 해줘** | `pro-ui-design` |
| **전체적으로 봐줘, 코드 엉망인 것 같은데, AI가 짠 코드 정리, 리팩터링, 커밋 전에 주석·이름 봐줘, 내 코딩 규칙 깔아줘** | `pro-code-consult` |
| **이미지 만들어줘, 그림 그려줘, 배경·캐릭터·아이콘 만들어줘, 어떤 그림체가 어울려** | `pro-image` |
| **발표 연습하자, 발표 자료 만들어줘, 대본 봐줘, 녹화 올렸어, PPT로 뽑아줘** | `pro-presentation` |
| **오픈소스 점검, 레포 컨설팅, trending 가려면, 오픈소스답게 만들어줘, 내 레포 전부 점검, README·라벨·라이선스 괜찮아?** | `pro-oss-consult` |
| **figma 디자인 구현, 시안대로 만들어줘, 시안이랑 같은지 확인, 디자인대로 됐는지, 그림자 빠진 거 없나** | `pro-figma` |
| **설계·기획 (무엇을 왜)** | **`superpowers:brainstorming`** |
| **구현 계획 (어떻게)** | **`superpowers:writing-plans`** |
| **계획 실행** | **`superpowers:executing-plans`** |

> 설계·계획·구현 흐름은 위 superpowers 3종이 담당한다. (옛 분석·계획·구현 스킬 3종은 #849에서 삭제되어 superpowers로 이관됐다.)

## 커밋 컨벤션 필수 규칙

커밋 메시지 앞에 이모지·태그(`🚀[기능개선]`, `⚙️[기능추가]` 등) **절대 포함 금지**.
이슈 제목에서 이모지+태그를 제거한 순수 내용만 사용한다.

- 올바른 예: `RELEASE-CHANGELOG PR 본문 초기화 보호 로직 추가 : feat : ... https://...`
- 잘못된 예: `🚀[기능개선][ChangeLog] RELEASE-CHANGELOG : feat : ...`

커밋은 `pro-commit`이 만든다. `pro-report`는 커밋을 직접 실행하지 않는다(SKILL.md에서 금지) — 커밋 메시지를 제안하는 스킬도 이 규칙을 따른다.

### 커밋 타입이 릴리스 버전을 결정한다 (#546 — agent 필독)

`semver_auto`가 켜진 레포(이 레포 포함)는 **릴리스 구간 커밋 제목으로 버전 승격 폭이 정해진다.**
커밋 타입을 아무거나 고르면 버전이 잘못 나간다.

| 커밋 타입 | 릴리스 결과 |
|---|---|
| `제목 : feat! : 내용` (또는 `feat!:`) | **major** — 4.2.45 → 5.0.0 |
| `제목 : feat : 내용` | **minor** — 4.2.45 → 4.3.0 |
| `fix` / `docs` / `chore` / `refactor` / `test` | patch — 4.2.45 → 4.2.46 |

- **`!`는 호환성이 깨질 때만 붙인다** — 기존 사용자의 설정·API·CLI 인자가 더 이상 동작하지
  않게 되는 변경. 확신이 없으면 붙이지 말고 사용자에게 묻는다.
- 한 릴리스 구간에 섞이면 가장 높은 것이 이긴다 (major > minor > patch).
- `[skip ci]` 포함 커밋과 `Merge`로 시작하는 커밋은 판정에서 제외된다.
- 판정 로직: `.github/scripts/changelog_manager.py` `classify_bump_level()`.

## 기능 구현 워크플로우

새 기능 구현 시 순서:

1. `superpowers:brainstorming` — 설계 및 스펙 확정
2. `superpowers:writing-plans` — 상세 구현 계획
3. `superpowers:executing-plans` — 실제 구현
4. `superpowers:requesting-code-review` — 코드 리뷰 요청
