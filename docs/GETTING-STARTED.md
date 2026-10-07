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

워크플로우는 기본 제공 `GITHUB_TOKEN`으로 동작합니다. **개인 액세스 토큰(PAT)은 선택입니다.** 아래 기능이 필요할 때만 저장소 Secret `_GITHUB_PAT_TOKEN`으로 등록합니다.

| 필요한 기능 | 기본 토큰으로 안 되는 이유 | Classic 토큰 권한 |
|---|---|---|
| 브랜치 보호 규칙이 Actions 봇을 막아도 릴리스 PR이 머지되게 | 릴리스 워크플로우가 `--admin`으로 다시 머지하며, 관리자 토큰이 필요하다 | `repo`, `workflow` |
| 이슈 라벨을 GitHub Projects 보드와 동기화 | `GITHUB_TOKEN`은 Projects API를 쓸 수 없다 | `repo`, `project` |
| 비공개 저장소에서 이슈 헬퍼 댓글로 다른 워크플로우를 이어 실행 | `GITHUB_TOKEN`이 만든 이벤트는 다른 워크플로우를 깨우지 않는다 | `repo` |

토큰이 없어도 릴리스 머지 뒤에 돌아야 할 워크플로우는 명시적 dispatch로 실행되므로, 그 용도로는 토큰이 필요 없습니다.

Fine-grained 토큰이라면 **Contents**, **Pull requests**, **Issues**, **Workflows**를 *Read and write*로 주면 첫 번째 기능에 충분할 것으로 봅니다. 다만 아직 끝까지 검증하지 않았고, Projects 동기화는 Classic 토큰으로만 확인했습니다. 실패하면 이슈로 알려 주세요.

```
Repository Settings → Secrets → Actions → New repository secret
Name: _GITHUB_PAT_TOKEN
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
