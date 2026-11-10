# 핵심 스크립트 규칙

> **언제 읽나:** `.github/scripts/` (버전 · 체인지로그 · 빌드 번호 · 이슈 헬퍼 · 초기화) 와 `.sh` 를 건드리거나, 레포 루트에 템플릿 전용 파일을 추가할 때
> `CLAUDE.md` 에서 옮긴 정본입니다. `CLAUDE.md` 에는 요약과 이 문서로 가는 링크만 있습니다.

## 핵심 스크립트

### version_manager (.py가 실 로직, .sh는 위임 shim — #448)
```bash
.github/scripts/version_manager.sh get            # 또는: python .github/scripts/version_manager.py get
.github/scripts/version_manager.sh increment       # patch +1 (기본)
.github/scripts/version_manager.sh increment --bump minor   # 4.2.45 → 4.3.0
.github/scripts/version_manager.sh increment --bump major   # 4.2.45 → 5.0.0
.github/scripts/version_manager.sh set 2.0.0
.github/scripts/version_manager.sh sync
.github/scripts/version_manager.sh get-code
.github/scripts/version_manager.sh increment-code
```
> v4.2부터 로직은 `version_manager.py`(stdlib 전용 — yq/jq 불필요)에 있고 `.sh`는 Python 위임 shim이다. Windows에서는 `python .github/scripts/version_manager.py get`을 직접 실행한다. **integrator 복사 목록에 `.sh`+`.py` 한 쌍이 모두 있어야 한다** (`truncate_release_notes.*`도 동일).

#### ⚠️ semver 자동 승격 축 (#546 — agent 필독)

릴리스 시 승격 폭은 `version.yml`의 `metadata.template.options.semver_auto`가 정한다.

| 값 | 동작 |
|---|---|
| **키 없음** (기존 통합 레포 전부) | 항상 `patch +1` — 구 동작 그대로 |
| `true` | 릴리스 구간 커밋 제목으로 major/minor/patch 결정 |
| `false` | 항상 `patch +1` |

- **키가 없으면 신규·기존 모두 `true`로 기록된다.** (구 정책: 기존 레포는 `false`로 남겼으나 소유자 결정으로
  바꿨다.) 대신 예고 없이 버전이 튀지 않게 **업데이트가 처음 켠 때 완료 화면이 경고**한다
  (`semverAutoNewlyOn`). 저장된 값은 명시적 `false`까지 그대로 존중한다.
- **마법사는 이 축을 묻지 않는다** (#485 질문 부담 축소 방향 유지). 켜려면 `version.yml`을 직접 고친다.
- 판정 규칙과 커밋 타입 대응은 "커밋 컨벤션 필수 규칙" 절 참조. `version_code`는 이 옵션과
  무관하게 매 릴리스 +1이다.
- **`PROJECT-COMMON-VERSION-CONTROL`(main 직접 push)도 `semver_auto`를 따른다 (#805, #815).** 켜져 있으면
  개발 브랜치 유무와 상관없이 push 구간 커밋 제목으로 major/minor/patch를 정하고, 명시적 `false`일 때만 patch다.
  (예전엔 이 경로가 항상 patch 고정이라 옵션이 조용히 무시됐다. "커밋 컨벤션을 신뢰할 수 없다"는 이전 이유는 소유자 결정으로 폐기.)
- VERSION-CONTROL 가드는 `version.yml` **파일 이름이 아니라 `version:` 값 변경**으로 릴리스 머지를 판정한다 (#806).
  설정만 바꾼 push는 릴리스가 아니므로 버전이 올라간다.

### 빌드 번호와 iOS 업로드 판단 (#643, agent 필독)

앱 빌드 번호와 Apple 업로드 오류 해석은 **각각 한 곳에서만** 정한다. 워크플로 yaml에 번호 계산이나 오류 문구 grep을 다시 적지 않는다.

| 무엇 | 어디 | 규칙 |
|---|---|---|
| 빌드 번호 | `.github/scripts/build_number.py` | `max(2024-01-01 UTC부터 지난 초, ASC 최근 번호+1, 거부 메시지 요구값+1)`. iOS 테스트, iOS 릴리스, Android 테스트 공통 |
| Apple 업로드 오류 해석 | `.github/scripts/ios_release.py classify-error` | `duplicate` / `too_low` / `train_closed` / `other`로 분류. 재시도 여부도 이 분류로 정한다 |

- `version_code`는 **Android 릴리스 전용**이다 (Play Store, Firebase CICD). iOS와 테스트 빌드 번호에 쓰지 않는다.
- **새 Apple 오류 코드(ITMS-...)를 다루려면** `classify_upload_error`에 **실제 오류 문구**를 근거로 패턴을 넣는다. 문구를 지어내지 않는다.
- iOS 릴리스는 닫힌 버전이면 버전 이름을 바꾸지 않고 실패한다. 테스트 빌드만 다음 패치로 전환한다.

### changelog_manager.py
```bash
python3 .github/scripts/changelog_manager.py update-from-summary
python3 .github/scripts/changelog_manager.py generate-md
python3 .github/scripts/changelog_manager.py export --version 1.2.3 --output release_notes.txt
python3 .github/scripts/changelog_manager.py classify-bump --commits-file commits.txt  # major|minor|patch
```

### changelog_providers/ (릴리스 노트 생성 사다리 — 전부 .py, #455·#566)

`RELEASE-CHANGELOG`의 fallback-summary job이 `ladder.py`를 호출한다. **마법사는 provider를 묻지 않는다** (#566) — 사용자의 목적은 "릴리스 노트가 잘 나오는 것"이지 생성기 선택이 아니다.

**생성 사다리** (위에서부터 시도, 실패하면 아래로)

| 순서 | 경로 | 조건 | 비용 |
|---|---|---|---|
| ① | PR 본문에 이미 있으면 그대로 사용 | 배포 스킬·CodeRabbit·사람이 작성 | — |
| ② | `openai_compatible.py` | AI 키가 등록됐을 때만 | 무료 등급 가능 |
| ③ | `commit.py` — 커밋 분석 | 위가 안 될 때 | **무료·무제한** |
| (별도) | `copilot.py` — Copilot CLI | `provider: copilot`을 **명시**했을 때만 | **Premium Request 소모** |

> **⚠️ 기본 경로에 과금 요소를 두지 말 것 (#569).** Copilot은 요청 수로 과금되므로
> 기본 사다리에서 제외했다. 남의 저장소에 설치되는 템플릿이라 **설치한 사람이 모르는
> 사이에 비용이 발생해선 안 된다.** 기본값은 언제나 "돈이 들지 않는 것"이다.

**AI 키는 서비스별 전용 이름으로 등록한다** — `MODEL_API_KEY` 하나로는 무슨 서비스인지
사람도 코드도 알 수 없었다.

| Secret 이름 | 서비스 | 무료 |
|---|---|---|
| `GEMINI_API_KEY` | Google Gemini | ✅ 일 500회 |
| `GROQ_API_KEY` | Groq | ✅ |
| `MISTRAL_API_KEY` | Mistral | ✅ |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | OpenAI / Anthropic | ❌ |
| `MODEL_API_KEY` | 구 이름 — 키 접두사로 서비스 추정 | 하위호환 |

**④는 AI·네트워크 무의존이라 항상 완주한다.** 어느 경로든 마지막이 `commit`이므로 "릴리스 노트가 비는" 상황은 생기지 않는다.

| provider 저장값 | 동작 |
|---|---|
| 미설정 | 레포 루트에 `.coderabbit.yaml`이 있으면 `coderabbit`, 없으면 `commit`. 어느 쪽이든 키가 있으면 사다리가 외부 AI를 자동으로 집는다 (#821) |
| `copilot` | Copilot → (키 있으면 Gemini) → commit |
| `openai`/`gemini`/`claude`/`groq`/`mistral`/`ollama` | 해당 provider → commit (`MODEL_API_KEY` 필요, ollama는 `changelog.base_url`) |
| `github-ai` | **서비스 종료(2026-07-30)** — 호출하지 않고 조용히 흡수, 업데이트 시 `commit`으로 이전 |
| `coderabbit` | 기다리지 않는다. 본문에 요약이 있으면 ①에서 존중될 뿐 |

> 미설정 판정(명시값 → `.coderabbit.yaml` → `commit`)은 워크플로우 "Read version info" 스텝과 `changelog_cli.py` `_read_release_branches` **두 곳이 같은 규칙**이어야 한다.

> **⚠️ 모델명에 버전을 박지 말 것 (#566).** `gemini-1.5-flash`가 404로 죽어 있었다. `openai_compatible.py`의 preset은 `-latest` 별칭을 쓴다. gemini는 **`gemini-flash-lite-latest`** 가 기본인데, 무료 등급에서 상위 Flash는 RPD 20인 반면 Lite는 500이라 자동화에 쓸 수 있는 쪽이 Lite뿐이기 때문이다(실측).
>
> **⚠️ 외부 서비스를 기본값으로 두지 말 것.** 기본 경로(①·②·④)에는 외부 API 키가 필요 없다. 남의 레포에 설치되는 템플릿이므로, 설치한 사람이 모르는 사이에 키를 요구하거나 과금이 발생해선 안 된다.

**생성 결과 안내** (`changelog_notice.py`): 어떤 경로로 만들어졌는지 Job Summary에 매번 남기고, **AI를 하나도 쓰지 못했을 때만** PR에 댓글로 대안을 안내한다. 댓글은 마커로 갱신하므로 이메일 알림은 처음 한 번만 간다 — 매 릴리스 알림은 소음이 되고, 소음이 되면 아무도 읽지 않는다.

npx 복사 엔진(`src/core/copy/simple.js`)이 provider .py들을 사용자 프로젝트에 복사한다 — **새 provider를 추가하면 복사 목록에도 넣는다** (빠지면 사용자 레포에서 import 실패).

### issue_helper.py (이슈 브랜치/커밋 댓글 — #478에서 내재화)
이슈 생성/제목 수정 시 `PROJECT-COMMON-SUH-ISSUE-HELPER.yaml`이 실행. 외부 액션 의존 없음 (stdlib 전용).
설정: `version.yml` `metadata.template.options.issue_helper` (branch_prefix/commit_template/commit_type_map/timezone/show_guide 등 — 없으면 기본값).
브랜치 코어(`YYYYMMDD_#번호_제목`)와 댓글의 `### 브랜치` 코드블록은 불변 계약 — 소비자 목록은 `docs/BRANCH-CONVENTION.md`.
서명 문구는 `guide_signature` 설정(기본 `Guide by ProjectOps`)이고, 구버전 소비자가 찾는 옛 문구 `Guide by SUH-LAB`는 숨김 주석으로 항상 남긴다 (#749).
구 MODULE 워크플로우의 커스텀 설정은 마이그레이션이 자동 이관한다 (`rules/settings-extractors.js`).

### template_integrator.sh / .ps1 — 제거됨 (EOF #458 → 삭제 #800)
**두 스크립트는 v4.3.0에서 안내용 shim으로 바뀌었고, #800에서 파일 자체를 지웠다.** 옛 `curl .../template_integrator.sh | bash`는 이제 404다. `src/` 주석에 지운 스크립트의 줄번호·함수명(`.sh L1234 등가`)을 적지 않는다 — 가리키는 파일이 없다. 이유는 현재형으로 적는다 (#916).
통합/업데이트/스킬 설치는 전부 **`npx projectops`** 한 경로다. 배포/publish 축·secret 백업 등 모든 옵션은 npx 마법사가 질문하며, 선택 값은 `version.yml`의 `metadata.template.options.*`에 동일하게 저장된다.

**초기화/통합 시 복사되지 않는 템플릿 전용 파일**:
```
CLAUDE.md, CONTRIBUTING.md, LICENSE
CHANGELOG.md, CHANGELOG.json
docs/, .github/scripts/test/
.claude-plugin/, .codex-plugin/, .agents/, .cursor/, skills/, scripts/
package.json, harness/         # pi 패키지 매니페스트 + Persona Harness
plugins/                       # extras 선택 플러그인 (projectops-extras)
hooks/                         # Claude Code 플러그인 훅 (세션 종료 시 pro-launch 기기 반납 #953 · raw 기기 명령 차단 #954)
```

#### ⚠️ 레포 루트에 "마켓플레이스/템플릿 전용" 파일·폴더를 추가할 때 (agent 필독)

이 레포는 **두 정체성**을 동시에 가진다 — 이 점이 일반 레포와 다른 핵심이다.

1. **템플릿 레포**: GitHub "Use this template"로 새 프로젝트를 만들면 `.github/scripts/template_initializer.py`(.sh는 위임 shim)가 마켓플레이스/템플릿 전용 파일을 **삭제**한다.
2. **마법사 배포원**: `npx projectops`(src/)가 기존 프로젝트에 템플릿을 통합할 때 그 파일들을 **복사 대상에서 제외**한다 (`src/core/exclusions.js`).

따라서 레포 루트에 새 파일/폴더를 추가했는데 그게 **이 레포에서만 의미 있고 사용자 프로젝트로 흘러가면 안 되는 것**(플러그인 매니페스트, skill, pi 패키지 파일, 내부 문서 등)이라면, **아래 2곳(+필요 시 3번째)을 반드시 함께 수정**한다. 한 곳만 고치면 새 프로젝트가 오염되거나 마법사가 불필요한 파일을 복사한다 — 실제로 자주 빠뜨리는 함정이다.

| # | 파일 | 수정할 위치 | 동작 |
|---|------|------------|------|
| 1 | `.github/scripts/template_initializer.py` | 삭제 목록 `CLEANUP_TARGETS` (`CHANGELOG.json` 항목 근처) | `("파일명", "설명")` 항목 추가 (**삭제**) |
| 2 | `src/core/exclusions.js` | `DOCS_TO_REMOVE` 등 제외 배열 | 파일/폴더명 추가 (**복사 제외**) |
| 3 | `.github/workflows/PROJECT-TEMPLATE-PLUGIN-VERSION-SYNC.yaml` | 버전 동기화 step + `git add` | 버전 필드가 있는 매니페스트(`package.json` 등)면 동기화 step 추가 |

> (구 `template_integrator.sh`/`.ps1`의 `plugin_items_to_remove` 배열은 #458 EOF로 사라졌다 — 이제 npx `exclusions.js`가 유일한 복사 제외 지점이다.)
>
> **체크 순서**: 새 루트 파일 추가 → "이게 사용자 프로젝트에도 필요한가?" 자문 → **아니오면 위 1·2를 모두 수정**. 버전을 `version.yml`과 맞춰야 하는 매니페스트면 3번도 추가. 수정 후 `python -m py_compile .github/scripts/template_initializer.py`와 `npm test`(감시 검사)로 확인한다.
>
> **반대로**, 추가한 게 사용자 프로젝트에도 같이 가야 하는 공통 자산(워크플로우·스크립트·설정)이라면 위 목록에 넣지 않는다 — 제외하면 통합 대상 프로젝트가 그 기능을 못 받는다.

#### ⚠️ macOS는 bash 3.2 + BSD 도구다 — `.sh` 작성·검증 시 절대 잊지 말 것 (agent 필독, 실측)

> **핵심: 윈도우(`.ps1`·Git Bash)에서 잘 돌아도 macOS에서 깨질 수 있다.** macOS 기본 `/bin/bash`는 라이선스 문제로 **3.2.57(2007년)에 박제**돼 있고, 기본 grep/sed도 **BSD 계열**이다. `.sh`는 항상 **`/bin/bash`(3.2) + BSD 도구**로 검증한다. "윈도우에서만 테스트했다"가 실제 사용자(macOS) 버그를 통째로 놓치게 한 주원인이다. (실측: 이슈 #415·#418 — 윈도우 정상, macOS만 깨짐.)

**bash 3.2에서 못 쓰는 것 (4+ 전용 → macOS에서 조용히 오작동)**
- **연관배열 `declare -A` 금지.** bash 3.2는 미지원 → 모든 문자열 키가 **인덱스 0으로 뭉개져** "키가 1개만 남는" 버그가 된다(실측 #418: @wizard env 키가 6개인데 1개만 수집). 동적 key-value가 필요하면 eval 동적변수 + 16진 키 인코딩 헬퍼(구 integrator의 `_kv_*` 패턴, 3.2/4 공용)를 쓴다.
- **`declare -g` 금지.** bash 3.2에서 `invalid option`. 최상위 레벨이면 어차피 전역이니 `-g` 없이 선언한다.
- `mapfile`/`readarray`, `${var,,}`/`${var^^}`(대소문자), `&>>`도 4+ 전용 → 사용 금지.

**BSD 도구 함정 (macOS 기본 grep/sed ≠ GNU)**
- **`grep -P`/`-oP`/`\K` 금지** (PCRE는 GNU 전용). `grep -E`로 라인 잡고 `sed -E`로 추출한다. (실측 #415: `grep: invalid option -- P`로 버전 감지 실패.)
- **`grep`이 매치 0건이면 `exit 1`** → `set -e`에서 `var=$(grep ...)` 단독 대입이 스크립트를 죽인다. `|| true`로 흡수하거나 `| head`/`| sed` 파이프로 끝낸다(pipefail 없으면 파이프 마지막 명령 코드만 봄). (실측 #415.)
- `sed -i`는 BSD가 `sed -i ''` / `sed -i.bak` 형태로 인자가 다르다. `readlink -f`·`date -d`·`xargs -r`도 BSD 미지원.

**`set -e` + 함수 끝 종료코드 (메뉴 아닌 일반 함수도 해당)**
- 위 "var=$(menu_fn)" 함정의 일반화: **함수의 마지막 명령이 비-0이면**, 그 함수가 호출부의 마지막 명령일 때 `set -e`가 스크립트를 통째로 죽인다. `[ -d x ] || return`(폴더 없으면 1 전파), `[ cond ] && cmd`(조건 거짓이면 1), `command -v foo && ...`(미설치면 1), `cp ... && ...`(실패면 1) 모두 위험. → early return은 `return 0` 명시, 끝줄 `조건 && 명령`은 `{ ...; } || true`로 감싼다. (실측 #415: Nexus/Secret 메뉴·interactive_mode·codex 제거·config cp 등 5곳.)

**검증 방법**: `bash -n`(문법)만으론 부족하다. **반드시 `/bin/bash`(3.2)로 실제 실행**한다. 함수만 떼어 `source` 후 호출해 실제 입력으로 **종료코드 0 완주**를 확인한다. `which bash`가 brew bash(`/opt/homebrew/bin/bash`, 4+)를 가리키면 `/bin/bash`로 명시 실행해 3.2를 강제한다.
