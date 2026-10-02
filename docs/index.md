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

설치가 끝나면 이슈 등록부터 릴리스까지 이 저장소 자신이 같은 도구로 운영됩니다.

![이슈 등록부터 릴리스까지 실제 화면](./images/demo/demo.gif)
