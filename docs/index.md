---
layout: home

hero:
  name: Projectops
  text: 이슈부터 배포까지
  tagline: 버전·체인지로그·배포는 GitHub Actions가, 이슈·커밋·보고서는 Agent Skills가 알아서 처리합니다.
  image:
    src: /images/hero-card.webp
    alt: npx projectops --mode doctor 실행 화면
  actions:
    - theme: brand
      text: 시작하기
      link: /GETTING-STARTED
    - theme: alt
      text: CLI 레퍼런스
      link: /CLI
    - theme: alt
      text: GitHub
      link: https://github.com/Cassiiopeia/projectops

features:
  - title: 이슈 → 배포 자동화
    details: 이슈 등록부터 릴리스 PR, 자동 머지, 배포까지 하나의 흐름으로 이어집니다.
    link: /ISSUE-AUTOMATION
  - title: 버전 · 체인지로그
    details: 커밋 제목으로 major/minor/patch를 판정하고, 릴리스 노트를 자동 생성합니다. AI 키가 없어도 완주합니다.
    link: /VERSION-CONTROL
  - title: Agent Skills
    details: Claude Code, Cursor, Gemini CLI, Codex CLI에서 쓰는 /pro-* Skills로 이슈·커밋·보고서를 만듭니다.
    link: /SKILLS
  - title: npx 마법사
    details: npx projectops 한 줄로 기존 프로젝트에 워크플로우를 통합하고 업데이트합니다.
    link: /NPX-WIZARD
  - title: PR Preview
    details: 댓글 한 줄로 임시 서버를 배포하고, PR을 닫으면 자동으로 정리합니다.
    link: /PR-PREVIEW
  - title: SSH + Docker 배포
    details: SSH로 접속 가능한 서버에 Docker 배포. Traefik/Nginx 무중단 배포도 지원합니다.
    link: /SSH-DOCKER-DEPLOYMENT-GUIDE
---

## 실제로 이렇게 동작합니다

프로젝트 폴더에서 `npx projectops` 한 줄이면 됩니다. 아래는 샘플 Spring 프로젝트에서 **실제로 실행한 화면**입니다.

![npx projectops 대화형 마법사 실행 화면](./images/cli-wizard.gif)

### ① 이슈를 열면 브랜치명과 커밋 메시지가 자동으로 달립니다

![이슈를 열면 자동 안내 댓글이 달리는 화면](./images/feature-issue.gif)

이슈를 열면 GitHub Actions가 스스로 실행되어 **브랜치명과 커밋 메시지 템플릿**을 댓글로 알려 줍니다. 이 브랜치명으로 작업하면 이슈 번호가 커밋·보고서에 자동으로 연동됩니다.

### ② PR을 열면 변경 요약이 자동으로 달립니다

![PR을 열면 변경 요약 댓글이 달리는 화면](./images/feature-pr-summary.gif)

작업 브랜치로 PR을 열면 커밋을 분석한 **변경 요약**이 댓글로 달립니다. 커밋을 더 올리면 새 댓글을 쌓지 않고 같은 댓글을 갱신합니다.

### ③ 릴리스 PR을 열면 버전 확정부터 머지, 태그까지 자동입니다

![릴리스 PR이 자동으로 머지되고 태그가 생기는 화면](./images/feature-release.gif)

개발 브랜치에서 `main`으로 PR을 열면 릴리스 노트를 쓰고, 커밋 제목(`feat`, `fix` 등)으로 버전을 정해 PR 제목에 반영한 뒤, 자동으로 머지하고 **버전 태그**까지 만듭니다. 위 예시는 `feat` 커밋이라 minor 버전이 올랐습니다.

> 한글 브랜치명에 GitHub이 띄우는 경고 배너는 화면에서 가렸습니다. 그 외에는 가공하지 않은 실제 화면입니다.
