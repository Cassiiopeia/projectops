# 시작하기

## 하고 싶은 일별로 실행할 것

| 하고 싶은 일 | 실행할 것 |
|--------------|-----------|
| 새 프로젝트를 시작한다 | GitHub에서 **Use this template** 클릭 (1분 내 자동 초기화) |
| 기존 프로젝트에 통합한다 | `npx projectops` |
| Agent Skills만 설치한다 | `npx projectops --mode skills` |
| 통합 상태·저장소 설정을 진단한다 | `npx projectops --mode doctor` (읽기 전용) |

Node.js 20.12 이상이 필요합니다. 비대화형 실행 예: `npx projectops --mode full --type spring,react --force`

옵션 전체는 `npx projectops --help`, 마법사 동작은 [NPX 마법사 가이드](/NPX-WIZARD)를 참고하세요.

## 최소 설정

워크플로우가 동작하려면 저장소에 Secret 하나가 필요합니다.

```
Repository Settings → Secrets → Actions → New repository secret
Name: _GITHUB_PAT_TOKEN
Value: Personal Access Token (repo, workflow 권한)
```

Organization 저장소라면 다음도 확인합니다.

```
Settings → Actions → General
├─ Allow GitHub Actions to create and approve pull requests
└─ Read and write permissions
```

## Agent Skills만 쓰고 싶다면

```bash
# Claude Code
claude plugin marketplace add Cassiiopeia/projectops
claude plugin install projectops@projectops-marketplace --scope user

# Gemini CLI
gemini extensions install https://github.com/Cassiiopeia/projectops

# Cursor 등 전체 설치 메뉴
npx projectops --mode skills
```

도구별 설치 방식과 Skill 목록은 [Agent Skills 가이드](/SKILLS)에 있습니다.

## 다음에 볼 문서

- [버전 관리](/VERSION-CONTROL) — `version.yml`과 자동 버전 증가
- [체인지로그 자동화](/CHANGELOG-AUTOMATION) — 릴리스 PR 흐름
- [이슈 자동화](/ISSUE-AUTOMATION) — 브랜치명·커밋 메시지 안내
- [문제 해결](/TROUBLESHOOTING)
