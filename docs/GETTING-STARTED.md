# 시작하기

## 하고 싶은 일별로 실행할 것

| 하고 싶은 일 | 실행할 것 |
|--------------|-----------|
| 새 프로젝트를 시작한다 | GitHub에서 **Use this template** 클릭 (1분 내 자동 초기화) |
| 기존 프로젝트에 통합한다 | `npx projectops` |
| Agent Skills만 설치한다 | `npx projectops --mode skills` |
| 통합 상태·저장소 설정을 진단한다 | `npx projectops --mode doctor` (읽기 전용) |

Node.js 20.12 이상이 필요합니다. 비대화형 실행 예: `npx projectops --mode full --type spring,react --force`

옵션 전체는 `npx projectops --help`, 마법사 동작은 [NPX 마법사 가이드](./NPX-WIZARD.md)를 참고하세요.

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

## 설치부터 첫 릴리스까지

전체 흐름을 짧게 따라갑니다. 단계마다 자세한 문서를 연결해 두었습니다.

**1. 준비물을 확인합니다.** Node.js 20.12 이상과 Git이 필요합니다. Python 3는 Agent Skills를 쓸 때만 필요합니다.

**2. 설치합니다.** 레포 루트에서 실행하고 질문에 답합니다.

```bash
npx projectops
```

**3. 생긴 파일을 확인합니다.** `version.yml`, `.github/workflows/PROJECT-*.yaml` 워크플로우,
`.github/scripts/`·`.github/config/`·`.github/util/` 보조 파일, 이슈·PR 템플릿,
`.github/.projectops/`(설치 기록)가 생깁니다. 모두 커밋합니다. [CLI 레퍼런스](./CLI.md)를 참고하세요.

**4. 설치 상태를 점검합니다.** 읽기만 합니다. 빠진 Secret과 아직 채워야 할 값을 알려 줍니다.

```bash
npx projectops --mode doctor
```

**5. 개발 브랜치를 만듭니다.** 작업은 `develop`에 모입니다. 릴리스는 `develop`에서 `main`으로 갑니다.

```bash
git checkout -b develop && git push -u origin develop
```

**6. 이슈를 엽니다.** 봇이 그 이슈의 브랜치명과 커밋 메시지를 댓글로 달아 줍니다.
[이슈 자동화](./ISSUE-AUTOMATION.md)를 참고하세요.

**7. 커밋합니다.** 안내된 메시지를 씁니다: `이슈 제목 : 타입 : 바꾼 내용 https://.../issues/N`.
타입이 다음 버전을 정합니다.

| 커밋 타입 | 다음 버전 |
|---|---|
| `feat!` (호환이 깨지는 변경) | major: 1.4.2 > 2.0.0 |
| `feat` | minor: 1.4.2 > 1.5.0 |
| 그 외 (`fix`, `docs`, `chore` 등) | patch: 1.4.2 > 1.4.3 |

한 릴리스 안에서는 가장 높은 것이 이깁니다. [버전 관리](./VERSION-CONTROL.md)를 참고하세요.

**8. `develop`을 푸시합니다.** 이슈 브랜치를 `develop`에 합치고 푸시합니다. 푸시만으로는 릴리스되지 않습니다.

**9. `develop` → `main` 릴리스 PR을 엽니다.** 직접 열거나 `/pro-changelog-deploy` 스킬로 엽니다.
그러면 워크플로우가 릴리스 노트 작성, 버전 확정, `CHANGELOG.md`·`CHANGELOG.json` 갱신,
PR 자동 머지, 태그 생성까지 합니다. 배포 워크플로우는 `main`에서 돕니다.
[체인지로그 자동화](./CHANGELOG-AUTOMATION.md)를 참고하세요.

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

도구별 설치 방식과 Skill 목록은 [Agent Skills 가이드](./SKILLS.md)에 있습니다.

## 자주 묻는 질문

**기존 워크플로우를 덮어쓰나요?**
아니요. 직접 고친 워크플로우는 그대로 둡니다. 새 템플릿은 비교용으로 `.github/.projectops/incoming/`에 저장합니다.

**AI 키가 필요한가요?**
아니요. 릴리스 노트는 커밋 분석으로 만듭니다. 키도 네트워크도 필요 없습니다.

**`develop`을 푸시했는데 릴리스가 안 됩니다.**
정상입니다. 릴리스는 `develop` → `main` PR을 열어야 시작됩니다.

**릴리스 PR이 자동 머지되지 않습니다.**
저장소 설정에서 "Allow auto-merge"를 켜고 브랜치 보호 규칙을 확인하세요.
[문제 해결](./TROUBLESHOOTING.md)을 참고하세요.

**아무것도 바꾸지 않고 먼저 볼 수 있나요?**
네. `npx projectops --mode options`와 `npx projectops --mode doctor`는 읽기만 합니다.
더 많은 질문: [다른 릴리스 도구와 비교](./COMPARE.md).

## 다음에 볼 문서

- [버전 관리](./VERSION-CONTROL.md) — `version.yml`과 자동 버전 증가
- [체인지로그 자동화](./CHANGELOG-AUTOMATION.md) — 릴리스 PR 흐름
- [이슈 자동화](./ISSUE-AUTOMATION.md) — 브랜치명·커밋 메시지 안내
- [문제 해결](./TROUBLESHOOTING.md)
