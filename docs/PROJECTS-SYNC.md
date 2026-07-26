# GitHub Projects 동기화 가이드

Issue Label과 GitHub Projects Status를 양방향으로 동기화하는 기능입니다.

---

## 📌 개요

### 동기화 방향

| 방향 | 담당 | 설명 |
|------|------|------|
| **Label → Status** | GitHub Actions | Issue에 라벨 추가 시 Projects Status 업데이트 |
| **Status → Label** | Cloudflare Worker | Projects에서 Status 변경 시 Issue Label 업데이트 |

이 문서는 **Label → Status** 동기화 (GitHub Actions)를 다룹니다.

### 동작 방식

1. Issue에 Status Label 추가/변경 (예: `작업중`)
2. `PROJECT-COMMON-PROJECTS-SYNC-MANAGER` 워크플로우 트리거
3. GitHub Projects의 해당 Issue Status를 동일하게 업데이트

---

## 🚀 빠른 시작

### 1단계: 워크플로우 설정

`.github/workflows/PROJECT-COMMON-PROJECTS-SYNC-MANAGER.yaml` 파일을 열면 `PROJECT_URL`이 **주석 처리된 상태**로 배포되어 있습니다. 주석(`#`)을 지우고 실제 URL로 바꿉니다.

```yaml
env:
  STATUS_LABELS: '["작업전", "작업중", "담당자확인", "피드백", "작업완료", "보류", "취소"]'

  # 배포 직후 상태 (비활성)
  # PROJECT_URL: 'https://github.com/orgs/YOUR-ORG/projects/1'

  # ↓ 주석을 지우고 본인 프로젝트 URL로 교체
  PROJECT_URL: 'https://github.com/orgs/MY-ORG/projects/3'
```

> `PROJECT_URL`이 비어 있으면 워크플로우는 실패하지 않고 안내 로그만 남긴 뒤 조용히 종료합니다. 설정 전까지는 아무 동작도 하지 않으므로 안전합니다.

`_GITHUB_PAT_TOKEN` Secret(권한: `repo`, `project`)도 함께 등록해야 합니다.

### 2단계: 끝!

이제 Issue에 Status Label을 추가하면 GitHub Projects에 자동 동기화됩니다.

---

## 📎 지원 URL 형식

다양한 URL 형식을 지원합니다. 복사-붙여넣기만 하면 됩니다.

### Organization 프로젝트

```
https://github.com/orgs/{org}/projects/{number}
https://github.com/orgs/{org}/projects/{number}/views/{view_id}
```

**예시:**
- `https://github.com/orgs/MapSee-Lab/projects/1`
- `https://github.com/orgs/TEAM-ROMROM/projects/6/views/2`

### User (개인) 프로젝트

```
https://github.com/users/{username}/projects/{number}
https://github.com/users/{username}/projects/{number}/views/{view_id}
```

**예시:**
- `https://github.com/users/Cassiiopeia/projects/2`
- `https://github.com/users/Cassiiopeia/projects/2/views/2`

> **💡 Tip**: `/views/{id}` 경로가 포함되어도 자동으로 파싱됩니다. URL 그대로 복사해서 사용하세요.

---

## ⚠️ Organization 프로젝트 사용 시 주의사항

Organization 프로젝트를 사용할 때는 **모든 레포에서 동일한 라벨을 사용**해야 합니다.

### 왜 동일한 라벨이 필요한가요?

- Organization 프로젝트는 여러 레포의 이슈를 하나의 보드에서 관리합니다.
- 각 레포의 Issue Label과 Projects Status를 매칭해야 합니다.
- 라벨 이름이 다르면 동기화가 실패합니다.

### 라벨 동기화 방법

1. **라벨 설정 파일 공유**

   `.github/config/issue-labels.yml` 파일을 모든 레포에 동일하게 유지:

   ```yaml
   # Status Labels (Projects 동기화용)
   - name: "작업전"
     color: "B8B8B8"
     description: "작업 시작 전"
   - name: "작업중"
     color: "1D76DB"
     description: "작업 진행 중"
   - name: "담당자확인"
     color: "5319E7"
     description: "담당자 확인 필요"
   - name: "피드백"
     color: "FBCA04"
     description: "피드백 대기 중"
   - name: "작업완료"
     color: "0E8A16"
     description: "작업 완료"
   - name: "보류"
     color: "D93F0B"
     description: "작업 보류"
   - name: "취소"
     color: "E4E669"
     description: "작업 취소"
   ```

2. **라벨 동기화 실행**

   `PROJECT-COMMON-SYNC-ISSUE-LABELS` 워크플로우로 라벨을 GitHub에 동기화:

   - 수동 실행: Actions → "Sync Issue Labels" → Run workflow
   - 자동 실행: `issue-labels.yml` 파일 변경 시 트리거

3. **Projects Status 옵션 맞추기**

   GitHub Projects에서 Status 필드의 옵션 이름을 라벨과 동일하게 설정:

   ```
   작업전, 작업중, 담당자확인, 피드백, 작업완료, 보류, 취소
   ```

### Organization 설정 체크리스트

- [ ] 모든 레포에 동일한 `issue-labels.yml` 배포
- [ ] 각 레포에서 라벨 동기화 워크플로우 실행
- [ ] GitHub Projects Status 옵션 이름 확인
- [ ] 각 레포의 `PROJECT_URL` 설정 (동일한 Projects URL)

---

## 🔧 설정 상세

### 환경 변수

| 변수 | 설명 | 예시 |
|------|------|------|
| `STATUS_LABELS` | 동기화할 Status Label 목록 (JSON 배열) | `'["작업전", "작업중", ...]'` |
| `PROJECT_URL` | GitHub Projects URL | `'https://github.com/orgs/ORG/projects/1'` |

### GitHub Secrets

| Secret | 설명 | 필요 권한 |
|--------|------|----------|
| `_GITHUB_PAT_TOKEN` | Personal Access Token | `repo`, `project` |

> **권한 설정**: Settings → Developer settings → Personal access tokens → Tokens (classic)
> - `repo` (전체)
> - `project` (전체) - Organization 프로젝트 접근용

---

## 🔍 트러블슈팅

### PROJECT_URL 관련 오류

**증상**: `⚠️ PROJECT_URL이 설정되지 않았습니다.`

**해결**:
1. 워크플로우 파일에서 `PROJECT_URL` 주석 해제
2. 올바른 URL 형식인지 확인

---

**증상**: `❌ PROJECT_URL 형식이 올바르지 않습니다.`

**해결**:
- URL이 지원 형식인지 확인:
  - Organization: `https://github.com/orgs/{org}/projects/{number}`
  - User: `https://github.com/users/{user}/projects/{number}`

### 프로젝트 연결 관련 오류

**증상**: `⏭️ 이슈가 해당 프로젝트에 연결되어 있지 않습니다.`

**해결**:
1. GitHub Projects에서 해당 이슈 추가
2. 또는 이슈 사이드바 → "Projects" → 프로젝트 선택

---

**증상**: `❌ 프로젝트에서 Status 필드를 찾을 수 없습니다.`

**해결**:
1. GitHub Projects에 "Status" 필드가 있는지 확인
2. 필드 이름이 정확히 "Status"인지 확인 (대소문자 구분)

---

**증상**: `❌ 프로젝트에 "작업중" Status 옵션이 없습니다.`

**해결**:
1. GitHub Projects의 Status 필드에 해당 옵션 추가
2. 또는 `STATUS_LABELS` 환경 변수를 프로젝트에 맞게 수정

### 권한 관련 오류

**증상**: `❌ 프로젝트 정보를 가져오는데 실패했습니다.`

**해결**:
1. `_GITHUB_PAT_TOKEN`에 `project` 권한이 있는지 확인
2. Organization 프로젝트의 경우 Organization 소속 계정의 토큰 필요
3. 프로젝트가 private일 경우 접근 권한 확인

---

## 📋 Status Label 커스터마이징

기본 제공 라벨 대신 프로젝트에 맞는 라벨을 사용할 수 있습니다.

### 변경 방법

1. **워크플로우 파일 수정** (2곳)

   ```yaml
   env:
     STATUS_LABELS: '["To Do", "In Progress", "Review", "Done"]'

   jobs:
     sync-label-to-status:
       if: |
         github.event_name == 'workflow_dispatch' ||
         (github.event_name == 'issues' &&
          contains(fromJSON('["To Do", "In Progress", "Review", "Done"]'), github.event.label.name))
   ```

2. **issue-labels.yml 수정**

   ```yaml
   - name: "To Do"
     color: "B8B8B8"
   - name: "In Progress"
     color: "1D76DB"
   - name: "Review"
     color: "5319E7"
   - name: "Done"
     color: "0E8A16"
   ```

3. **GitHub Projects Status 옵션 맞추기**

   Projects 설정에서 Status 필드의 옵션을 동일하게 변경

---

## 📚 관련 문서

- [이슈 자동화 가이드](ISSUE-AUTOMATION.md)
- [버전 관리 시스템](VERSION-CONTROL.md)
