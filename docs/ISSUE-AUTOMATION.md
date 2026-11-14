# 이슈 자동화

이슈 생성 시 브랜치명/커밋 메시지를 자동 제안하고, 댓글로 QA 이슈를 생성합니다.

---

## 개요

| 기능 | 트리거 | 설명 |
|------|--------|------|
| **Issue Helper** | 이슈 생성 | 브랜치명, 커밋 메시지 자동 제안 |
| **QA 봇** | `@projectops create qa` 댓글 | QA 이슈 자동 생성 |
| **라벨 동기화** | `issue-labels.yml` 변경 | GitHub 라벨 자동 동기화 |

---

## 댓글 명령어

이슈나 PR 댓글로 시작할 수 있는 명령어 전체입니다. 각 명령어는 처리하는 워크플로우가 설치된 경우에만 동작합니다.

| 댓글 | 하는 일 | 쓰는 곳 | 워크플로우 |
|---|---|---|---|
| `@projectops server build [브랜치]` | 임시 Preview 서버 빌드·배포 | PR, 이슈 | `PROJECT-SPRING-PR-PREVIEW.yaml` / `PROJECT-PYTHON-PR-PREVIEW.yaml` |
| `@projectops server status [브랜치]` | Preview 상태 확인 | PR, 이슈 | 위와 같음 |
| `@projectops server destroy [브랜치]` | Preview 삭제 | PR, 이슈 | 위와 같음 |
| `@projectops app build [브랜치]` | Flutter 테스트 빌드, Android + iOS | PR, 이슈 | `PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml` |
| `@projectops apk build [브랜치]` | Flutter 테스트 빌드, Android만 | PR, 이슈 | 위와 같음 |
| `@projectops ios build [브랜치]` | Flutter 테스트 빌드, iOS만 | PR, 이슈 | 위와 같음 |
| `@projectops create qa` | 이 이슈와 연결된 QA 이슈 생성 | PR, 이슈 | `PROJECT-COMMON-QA-ISSUE-CREATION-BOT.yaml` |

- `[브랜치]`를 생략하면 PR은 head 브랜치를, 이슈는 Issue Helper 댓글에 적힌 브랜치를 씁니다. 자세히: [PR Preview](PR-PREVIEW.md), [Flutter 빌드 트리거](FLUTTER-TEST-BUILD-TRIGGER.md)
- `server` 명령어는 위에 적힌 어순 그대로여야 합니다. Flutter 명령어는 `build app` / `build apk` / `build ios`도 받고, QA 봇은 댓글 어딘가에 `@projectops`, `create`, `qa`가 모두 있으면 동작합니다.
- **누가 실행할 수 있나:** 공개 저장소에서는 `OWNER`, `MEMBER`, `COLLABORATOR`의 댓글만 명령을 실행하고 나머지는 무시합니다. 비공개 저장소는 검사하지 않습니다. 목록은 저장소 변수 `PROJECTOPS_TRIGGER_ASSOCIATIONS`에 JSON 배열로 바꿉니다. 예: `["OWNER","MEMBER","COLLABORATOR","CONTRIBUTOR"]` (v4.85.0). JSON이 잘못되면 이 워크플로우들이 모든 댓글에서 실패하니, 변수를 지우면 기본값으로 돌아갑니다.
- Issue Helper가 직접 단 댓글은 명령을 실행하지 않습니다.

---

## Issue Helper

이슈가 생성되면 자동으로 권장 브랜치명과 커밋 메시지를 댓글로 제안합니다.

### 동작 방식

```
1. 이슈 생성
2. Issue Helper 워크플로우 실행
3. 이슈 제목 기반으로 브랜치명/커밋 생성
4. 댓글로 안내
```

### 자동 생성 댓글 예시

```markdown
<!-- Guide by SUH-LAB (구버전 워크플로우 호환용 표식, 화면에는 보이지 않음) -->

Guide by ProjectOps
---

### 브랜치
```
20260112_#145_로그인_기능_추가
```

### 커밋 메시지
```
로그인 기능 추가 : feat : {변경 내용} https://github.com/user/repo/issues/145
```

### 명령어
```bash
git checkout -b 20260112_#145_로그인_기능_추가
```
```

### 브랜치명 규칙

```
YYYYMMDD_#이슈번호_이슈제목_요약
```

- 날짜: 이슈 생성일
- 이슈 번호: `#145` 형식
- 제목: 공백 → 언더스코어, 특수문자 제거

### 워크플로우

**파일**: `PROJECT-COMMON-SUH-ISSUE-HELPER.yaml` (로직: `.github/scripts/issue_helper.py` — v4.3.0 내재화, 외부 액션 의존 없음)

```yaml
on:
  issues:
    types: [opened, edited]
```

**커스터마이징**: `version.yml` → `metadata.template.options.issue_helper`
(branch_prefix / max_branch_length / timezone / commit_template / commit_type_map / comment_marker / guide_signature / show_guide — 섹션 없으면 기본값. `guide_signature` 기본값은 `Guide by ProjectOps`)

---

## QA 봇

Issue나 PR에 `@projectops create qa` 댓글을 작성하면 QA 이슈를 자동 생성합니다.

### 사용법

```
@projectops create qa
```

### 동작 방식

```
1. Issue/PR에 @projectops create qa 댓글 작성
2. QA-ISSUE-CREATION-BOT 워크플로우 실행
3. QA 이슈 템플릿으로 새 이슈 생성
4. 원본 Issue/PR에 링크 댓글
```

### 생성되는 QA 이슈

```markdown
## QA 요청

**원본**: #145 (링크)
**요청자**: @username

### 테스트 항목
- [ ] 기능 테스트
- [ ] UI/UX 테스트
- [ ] 엣지 케이스 테스트

### 테스트 환경
- [ ] 로컬
- [ ] 개발 서버
- [ ] 스테이징
```

### 워크플로우

**파일**: `PROJECT-COMMON-QA-ISSUE-CREATION-BOT.yaml`

```yaml
on:
  issue_comment:
    types: [created]
```

**트리거 조건**:
- 댓글에 `@projectops create qa` 포함
- Issue 또는 PR 모두 지원

---

## 라벨 동기화

`issue-labels.yml` 파일을 수정하면 GitHub 라벨이 자동으로 동기화됩니다.

### 라벨 파일 위치

```
.github/config/issue-labels.yml
```

### 라벨 파일 형식

```yaml
- name: "priority: urgent"
  from_name: 긴급          # 기존 한글 라벨을 이름만 바꿔 이슈에 붙은 상태를 보존한다
  color: "d73a4a"
  description: "Urgent work"

- name: "status: in progress"
  from_name: 작업중
  color: "74D7CB"
  description: "Work in progress"
```

### 라벨 표기: 영문 표준과 한글 (`label_style`)

`version.yml`의 `metadata.template.options.label_style`이 라벨 이름의 표기를 정한다.

| 값 | 의미 | 언제 |
|---|---|---|
| `en` | 영문 표준 (`status: todo` 등) | **신규 설치 기본값** |
| `ko` | 기존 한글 (`작업전` 등) | 이미 설치된 레포는 키가 없으면 유지된다 |

영문으로 바꾸려면 `npx projectops --label-style en`을 실행한다(대화형 업데이트에서는 한 번 제안한다). 라벨 동기화 워크플로우가 `from_name`으로 한글 라벨의 **이름만** 바꾸므로 이슈에 붙은 라벨은 그대로 옮겨진다. Projects 동기화와 스킬은 두 표기를 모두 인식한다.

### 기본 제공 라벨

| 영문 표준 | 기존 한글 | 용도 |
|------|------|------|
| `priority: urgent` | 긴급 | 긴급 처리 필요 |
| `documentation` | 문서 | 문서 관련 |
| `status: todo` | 작업전 | 작업 시작 전 준비 상태 |
| `status: in progress` | 작업중 | 작업이 진행 중인 상태 |
| `status: needs review` | 담당자확인 | 담당자 확인 필요, 대기중 상태 |
| `status: feedback` | 피드백 | 담당자 확인 후 수정 필요 |
| `status: done` | 작업완료 | 작업 완료 상태 |
| `status: on hold` | 보류 | 작업 일시 중단 상태 |
| `status: cancelled` | 취소 | 작업 취소됨 |

### 완료한 이슈는 릴리스가 나갈 때 닫힌다 (`close_on_release`)

완료 표시는 라벨(`status: done` 또는 `작업완료`)이 맡고, 닫는 일은 `PROJECT-COMMON-CLOSE-ISSUES-ON-RELEASE` 워크플로우가 릴리스 머지 때 한다. 릴리스 구간 커밋이 이슈 URL을 참조하고 완료 라벨이 있는 이슈만 닫는다. `version.yml`에 `close_on_release: true`가 있을 때만 동작하며, **신규 설치만 켜진다. 기존 설치는 키가 없어 꺼진 채 유지된다.**

### 워크플로우

**파일**: `PROJECT-COMMON-SYNC-ISSUE-LABELS.yaml`

```yaml
on:
  push:
    paths:
      - '.github/config/issue-labels.yml'
```

---

## 이슈 템플릿

4종의 이슈 템플릿이 자동으로 설치됩니다.

| 템플릿 | 파일 | 언제 쓰나 |
|--------|------|------|
| 버그 리포트 | `bug_report.md` | 되던 것, 또는 되어야 할 것이 안 될 때. 증상·재현 방법·기대 동작을 적습니다 |
| 기능 요청 | `feature_request.md` | 새 기능을 더하거나 기존 기능을 개선할 때 |
| 디자인 요청 | `design_request.md` | 만들기 전에 UI/UX 디자인(화면·에셋)을 요청할 때 |
| QA 요청 | `qa_request.md` | 기능 개발이나 버그 수정이 끝나 테스트를 요청할 때. [QA 봇](#qa-봇)(`@projectops create qa`)이 대신 채워 줍니다 |

같은 폴더의 `projectops-installer-bug.yml`, `projectops-skill-bug.yml`은 projectops 저장소 자체용 양식(설치기·에이전트 스킬 버그)이라 사용자 저장소에는 설치되지 않습니다.

### 템플릿 위치

```
.github/ISSUE_TEMPLATE/
├── bug_report.md
├── feature_request.md
├── design_request.md
├── qa_request.md
└── config.yml          # 템플릿 선택 화면 설정
```

---

## 트러블슈팅

### Issue Helper 댓글이 안 생김

**확인 사항**:
1. `PROJECT-COMMON-SUH-ISSUE-HELPER.yaml` 워크플로우와 `.github/scripts/issue_helper.py` 존재 여부
2. Actions 탭에서 워크플로우 활성화 여부
3. Private 레포에서 연쇄 트리거가 필요하면 `_GITHUB_PAT_TOKEN` Secret 설정 (일반 댓글 생성은 GITHUB_TOKEN으로 충분)

### QA 이슈 생성 안됨

**확인 사항**:
1. 댓글에 정확히 `@projectops create qa` 입력했는지 확인
1. 공개 저장소라면 작성자가 `OWNER`, `MEMBER`, `COLLABORATOR`인지 (목록은 저장소 변수 `PROJECTOPS_TRIGGER_ASSOCIATIONS`로 변경)
2. 워크플로우 권한 확인 (Issues 쓰기 권한)

### 라벨 동기화 안됨

**확인 사항**:
1. `.github/config/issue-labels.yml` 파일 YAML 문법 확인
2. 라벨 이름에 특수문자 없는지 확인

---

## 관련 문서

- [PR Preview](PR-PREVIEW.md) - `@projectops server` 명령어
- [Flutter 빌드 트리거](FLUTTER-TEST-BUILD-TRIGGER.md) - `@projectops app build/apk build/ios build` 명령어
- [트러블슈팅](TROUBLESHOOTING.md)
