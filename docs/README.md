# projectops 문서 인덱스

프로젝트 전체 소개는 [루트 README](../README.md)를 먼저 보세요. 이 문서는 `docs/` 안의 문서를 목적별로 안내합니다.

---

## 처음 시작한다면

| 문서 | 내용 |
|------|------|
| [NPX 마법사 가이드](NPX-WIZARD.md) | `npx projectops`로 기존 프로젝트에 템플릿 통합·업데이트. 프로젝트 성격(intent), 배포/publish 2축, 레거시 자동 마이그레이션 |
| [Agent Skills 가이드](SKILLS.md) | Claude Code / Cursor / Gemini CLI / Codex CLI에서 쓰는 24종 Skill |
| [통합 스크립트 가이드](TEMPLATE-INTEGRATOR.md) | 구 `template_integrator.sh`/`.ps1` 지원 종료(EOF) 안내 |

---

## 자동화 시스템

| 문서 | 내용 |
|------|------|
| [버전 관리](VERSION-CONTROL.md) | `version.yml`, 자동 버전 증가, 멀티타입·모노레포 경로 |
| [체인지로그 자동화](CHANGELOG-AUTOMATION.md) | 릴리스 PR 흐름, 릴리스 노트 provider 사다리, CodeRabbit 연동 |
| [이슈 자동화](ISSUE-AUTOMATION.md) | Issue Helper 댓글, QA 봇, 라벨 동기화, 이슈 템플릿 |
| [브랜치 네이밍 규칙](BRANCH-CONVENTION.md) | `YYYYMMDD_#번호_제목` 형식과 이 규칙에 의존하는 소비자 목록 (유지보수자용) |
| [GitHub Projects 동기화](PROJECTS-SYNC.md) | Issue Label ↔ Projects Status 양방향 동기화 |
| [Projects 동기화 마법사](GITHUB-PROJECTS-SYNC-WIZARD.md) | Status → Label 방향(Cloudflare Worker) 설정 마법사 |

---

## 배포

| 문서 | 내용 |
|------|------|
| [SSH + Docker 배포 가이드](SSH-DOCKER-DEPLOYMENT-GUIDE.md) | Spring·Python 서버 배포, 무중단 배포(Traefik/Nginx), Flutter APK SMB 업로드 |
| [PR Preview](PR-PREVIEW.md) | 댓글 한 줄로 임시 서버 배포·정리 |

---

## Flutter CI/CD

| 문서 | 내용 |
|------|------|
| [Flutter CI/CD 전체 가이드](FLUTTER-CICD-OVERVIEW.md) | 전체 아키텍처, 워크플로우 목록, **GitHub Secrets 전체 목록** |
| [TestFlight 마법사](FLUTTER-TESTFLIGHT-WIZARD.md) | iOS 배포 설정 자동 생성 |
| [Play Store 마법사](FLUTTER-PLAYSTORE-WIZARD.md) | Android Play Store 배포 설정 자동 생성 |
| [Firebase App Distribution 마법사](FLUTTER-FIREBASE-WIZARD.md) | Firebase 테스터 배포 설정 자동 생성 |
| [테스트 빌드 트리거](FLUTTER-TEST-BUILD-TRIGGER.md) | PR/이슈 댓글로 APK·TestFlight 테스트 빌드 |

---

## 기여자용

| 문서 | 내용 |
|------|------|
| [워크플로우 주석 표준](WORKFLOW-COMMENT-GUIDELINES.md) | 워크플로우 주석 컨벤션, 타입 분류, **파일별 적용 현황 전수 목록** |
| [브랜치 네이밍 규칙](BRANCH-CONVENTION.md) | 규칙 변경 시 깨지는 소비자 목록과 확장 절차 |
| [CONTRIBUTING](../CONTRIBUTING.md) | 기여 절차 |
| [CLAUDE.md](../CLAUDE.md) | agent용 프로젝트 규칙 (작업 브랜치·이슈 처리·확장 규칙) |

---

## 문제 해결

| 문서 | 내용 |
|------|------|
| [트러블슈팅](TROUBLESHOOTING.md) | Actions·버전·체인지로그·PR Preview·SSH 배포·Flutter 빌드 문제 |

---

## 산출물 보관 폴더

| 경로 | 용도 |
|------|------|
| `docs/projectops/` | 스킬 산출물 (이슈·보고서·계획·리뷰 등) |
| `docs/superpowers/` | 설계 문서(specs)·구현 계획(plans) |
| `docs/qa/` | QA 기록 |

> 위 폴더는 **작업 기록물**이라 작성 시점의 사실을 담고 있습니다. 현행 동작은 항상 `docs/` 루트 문서와 실제 워크플로우·소스를 기준으로 확인하세요.
