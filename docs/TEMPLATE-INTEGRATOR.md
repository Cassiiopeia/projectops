# Template Integrator — ⚠️ 지원 종료 (EOF)

> **`template_integrator.sh` / `.ps1`은 v4.3.0에서 지원이 종료되었고 (#458), 안내용 shim도 저장소에서 제거되었습니다 (#800).**
> 예전 `curl .../template_integrator.sh | bash` 명령은 이제 404를 받습니다. 아래 `npx projectops`를 쓰세요.

## 대체 경로 — npx projectops

기존 프로젝트 통합·업데이트·스킬 설치는 전부 npx 한 가지 경로로 통일되었습니다.

```bash
# 대화형 마법사 (macOS / Linux / Windows 공통)
npx projectops

# 비대화형 (CI 등)
npx projectops --mode full --type spring,react --force

# Agent Skills만 설치
npx projectops --mode skills

# 전체 옵션
npx projectops --help
```

- **요구사항**: Node.js 20.12 이상 → https://nodejs.org
- 구 스크립트의 모든 기능(타입 감지·버전 감지·워크플로우 복사·version.yml 생성·되돌리기·배포/publish 축 질문)은 npx 마법사가 동일하게 제공합니다.
- 선택 값은 기존과 동일하게 `version.yml`의 `metadata.template.options.*`에 저장됩니다.

## 구 플래그 → npx 대응

| 구 스크립트 | npx |
|---|---|
| `--mode full/version/workflows/issues/skills` | 동일 (`--mode ...`) |
| `--type spring,react` | 동일 (`--type ...`) |
| `--deploy docker-ssh\|vercel\|none` | 동일 |
| `--publish nexus,npm,github-packages` | 동일 |
| `--secret-backup` | 동일 |
| `--force` | 동일 |

자세한 사용법은 [NPX 마법사 가이드](NPX-WIZARD.md), [README](../README.md), `npx projectops --help`를 참고하세요.
