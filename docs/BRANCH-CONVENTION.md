# 브랜치 네이밍 규칙 (BRANCH CONVENTION)

> 이 문서는 템플릿 유지보수자용이다. 최종 사용자 안내는
> ① 이슈 헬퍼 댓글의 접이식 안내(사용 시점) ② 의존 워크플로우 헤더 주석(사용자 레포로 복사됨)이 담당한다.

## 형식

```
{prefix}YYYYMMDD_#이슈번호_정규화제목
예: 20260712_#427_드롭다운_디자인_변경
```

- 생성: `.github/scripts/issue_helper.py` (이슈 생성 시 댓글 제안) / `scripts/common/gh_branch.py` (pro-github 스킬) — **두 구현의 결과가 일치해야 한다**
- prefix(예: `feat/`)는 선택 — `version.yml`의 `metadata.template.options.issue_helper.branch_prefix`
- 코어부(`YYYYMMDD_#번호_제목`)는 고정 — 아래 소비자들이 기계 파싱한다

## 소비자 (이 형식을 깨면 죽는 것들)

| 소비자 | 파싱 방식 | 깨질 때 증상 |
|---|---|---|
| `PROJECT-FLUTTER-ANDROID-TEST-APK.yaml` | `sed 's/.*#\([0-9]*\).*/\1/p'` | 빌드 노트에 이슈 정보 누락 |
| `PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml` | 동일 | 동일 |
| `PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml` | `/#(\d+)/` + 안내 댓글(`Guide by ProjectOps` 또는 옛 `Guide by SUH-LAB`)의 `### 브랜치` 코드블록 | 이슈 댓글 빌드가 브랜치를 못 찾음 |
| `scripts/common/issue_number.py` (pro-commit/report/review) | worktree `\d{8}_(\d+)_` / 브랜치 숫자 패턴 | 커밋 메시지·보고서에서 이슈 번호 미인식 |

## 댓글 계약 (이슈 헬퍼가 생성하는 댓글)

`### 브랜치` 제목 + 코드블록 구조는 불변이다.
구버전 BUILD-TRIGGER가 사용자 레포에서 계속 실행되므로 하위호환이 필수다.

서명 문구(기본 `Guide by ProjectOps`)는 `issue_helper.guide_signature` 설정으로 바꿀 수 있다. 구버전 소비자가 옛 문구 `Guide by SUH-LAB`를 찾기 때문에
댓글에는 눈에 보이지 않는 HTML 주석으로 옛 표식을 항상 한 줄 남긴다. 소비자를 새로 만들 때는 두 문구를 모두 허용한다.

## 확장 규칙 (agent 필독)

- 새 워크플로우가 이 브랜치 규칙에 의존하게 되면:
  1. `issue_helper.py`의 `GUIDE_LINES`에 (파일명, 안내 문구) 한 줄 추가 — 파일 실존 기반이라
     해당 워크플로우가 없는 레포에는 안내가 표시되지 않는다 (거짓 안내 차단)
  2. 그 워크플로우 헤더에 "⚠️ 브랜치 규칙 의존" 표준 주석 블록 추가
  3. 이 문서의 소비자 표에 행 추가
