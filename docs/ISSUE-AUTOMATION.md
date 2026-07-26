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
## Guide by SUH-LAB

### 브랜치
```
20260112_#145_로그인_기능_추가
```

### 커밋 메시지
```
feat : 로그인 기능 추가 https://github.com/user/repo/issues/145
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
(branch_prefix / max_branch_length / timezone / commit_template / commit_type_map / comment_marker / show_guide — 섹션 없으면 기본값)

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
- name: "긴급"
  color: "d73a4a"
  description: "긴급 처리 필요"

- name: "작업중"
  color: "74D7CB"
  description: "작업이 진행 중인 상태"

- name: "담당자확인"
  color: "FBC61E"
  description: "담당자 확인 필요, 대기중 상태"
```

### 기본 제공 라벨

| 라벨 | 용도 |
|------|------|
| 긴급 | 긴급 처리 필요 |
| 문서 | 문서 관련 |
| 작업전 | 작업 시작 전 준비 상태 |
| 작업중 | 작업이 진행 중인 상태 |
| 담당자확인 | 담당자 확인 필요, 대기중 상태 |
| 피드백 | 담당자 확인 후 수정 필요 |
| 작업완료 | 작업 완료 상태 (이슈 폐쇄) |
| 보류 | 작업 일시 중단 상태 |
| 취소 | 작업 취소됨 |

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

| 템플릿 | 파일 | 용도 |
|--------|------|------|
| 버그 리포트 | `bug_report.md` | 버그 신고 |
| 기능 요청 | `feature_request.md` | 기능 추가/개선 |
| 디자인 요청 | `design_request.md` | UI/UX 디자인 |
| QA 요청 | `qa_request.md` | 테스트 요청 |

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
2. 워크플로우 권한 확인 (Issues 쓰기 권한)

### 라벨 동기화 안됨

**확인 사항**:
1. `.github/config/issue-labels.yml` 파일 YAML 문법 확인
2. 라벨 이름에 특수문자 없는지 확인

---

## 관련 문서

- [PR Preview](PR-PREVIEW.md) - `@projectops server` 명령어
- [Flutter 빌드 트리거](FLUTTER-TEST-BUILD-TRIGGER.md) - `@projectops build app/apk build/ios build` 명령어
- [트러블슈팅](TROUBLESHOOTING.md)
