---
title: release-please, semantic-release, changesets와 비교
description: projectops를 release-please, semantic-release, changesets와 비교하고, 더 작은 도구가 맞는 경우를 정리했습니다.
---

# 다른 릴리스 도구와 비교

projectops는 이슈, 브랜치, 릴리스 PR, 버전, 체인지로그, 배포까지 전체 사이클을 GitHub 저장소에 설치합니다. 그중 일부만 필요하다면 더 작은 도구가 맞을 수 있습니다.

| | projectops | release-please | semantic-release | changesets |
|---|---|---|---|---|
| 버전 결정 근거 | 커밋 제목 (`feat` → minor, `feat!` → major) | Conventional Commits | Conventional Commits (설정 가능) | PR마다 쓰는 changeset 파일 |
| 릴리스 전 검토 단계 | 릴리스 PR(develop → main), 자동 머지 | 직접 머지하는 릴리스 PR | 기본은 없음, push하면 릴리스 | "Version Packages" PR |
| 체인지로그 | 릴리스 PR에서 작성 (커밋 분석 또는 AI 요약) | 자동 생성 | 자동 생성 (플러그인) | changeset 파일을 모아 작성 |
| 프로젝트 타입별 CI/CD 워크플로우 | 있음 (Spring, Flutter, React, Python, Node는 npm 배포) | 없음 | 없음 | 없음 |
| 사이클을 굴리는 에이전트 스킬 | 있음 | 없음 | 없음 | 없음 |
| 저장소에 추가되는 것 | 약 60개 파일 | 워크플로우 1개와 설정 파일 | 설정 파일과 CI 단계 | `.changeset/` 폴더와 CI 단계 |

## 무엇을 고를까요?

- **버전과 체인지로그만 필요:** release-please나 semantic-release가 더 가볍습니다.
- **모노레포에서 npm 패키지를 내고 PR마다 변경 내용을 적고 싶음:** changesets가 맞습니다.
- **전체 사이클을 한 번에 설치하고 그 위에 에이전트 스킬까지:** projectops가 그 용도입니다.

## projectops가 맞지 않는 경우

- GitHub를 쓰지 않는 경우. GitHub Actions, 이슈, PR을 전제로 합니다.
- 저장소 파일을 최소로 두고 싶은 경우. 전체 설치는 약 60개를 추가합니다 (v4.84.0 실측: `--type basic` 56개, `--type spring` 60개).
- 워크플로우 템플릿을 버전에 고정해야 하는 경우. `npx projectops@<version>`은 설치기만 고정하고, 템플릿은 현재 `main`에서 받습니다.

## 자주 묻는 질문

**기존 워크플로우를 덮어쓰나요?**
아니요. 직접 고친 워크플로우는 유지하고, 새 템플릿은 비교할 수 있게 옆에 저장합니다. [NPX 마법사 가이드](./NPX-WIZARD.md)를 보세요.

**AI 키가 필요한가요?**
아니요. 릴리스 노트는 키도 네트워크도 필요 없는 커밋 분석으로 만들어집니다. 키는 요약 품질만 높입니다. [체인지로그 자동화](./CHANGELOG-AUTOMATION.md)를 보세요.

**어떤 운영체제에서 동작하나요?**
Windows, macOS, Linux에서 동작합니다. 릴리스마다 세 운영체제에서 Node 20과 24로, 이름에 한글과 공백이 있는 폴더에 설치해 확인합니다.

**아무것도 바꾸지 않고 살펴볼 수 있나요?**
`npx projectops --mode options`로 모든 옵션을 읽을 수 있고, `npx projectops --mode doctor`는 기존 설치를 읽기만 합니다.

다음: [시작하기](./GETTING-STARTED.md)
