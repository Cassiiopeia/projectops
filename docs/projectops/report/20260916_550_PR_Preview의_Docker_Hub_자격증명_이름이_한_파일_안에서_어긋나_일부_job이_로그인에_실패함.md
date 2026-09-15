# PR Preview의 Docker Hub 자격증명 이름이 한 파일 안에서 어긋나 일부 job이 로그인에 실패함

## 개요

`PROJECT-SPRING-PR-PREVIEW` 워크플로우가 같은 파일 안에서 Docker Hub 자격증명 Secret 이름을
두 벌 혼용하고 있었다. 다수파이자 같은 타입의 다른 배포 워크플로우와 일치하는
`DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN`으로 통일했다.

설치 후 검증 기능(#549)을 붙이자마자 Secret 수집 결과에서 드러난 문제다. 한 배포 세트가
`DOCKER_PASSWORD`와 `DOCKERHUB_TOKEN`을 동시에 요구하는 것이 비정상 신호였다.

## 문제의 형태

| 위치 | 수정 전 | 수정 후 |
|---|---|---|
| 351·352·1013·1014행 등 다수 job | `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` | 그대로 |
| **1816·1817행 "Docker Hub 로그인" step** | `DOCKER_USERNAME` / `DOCKER_PASSWORD` | `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` |
| 1825행 이미지 태그 조립 | `DOCKER_USERNAME` | `DOCKERHUB_USERNAME` |

같은 타입의 다른 배포 워크플로우 3종(`SIMPLE-CICD`, `NONSTOP-TRAEFIK-CICD`,
`NONSTOP-NGINX-CICD`)은 전부 `DOCKERHUB_*`만 쓴다. 즉 `DOCKER_*` 쪽이 어긋난 이름이었다.

## 왜 찾기 어려운 버그인가

워크플로우의 **대부분이 정상 동작한다.** 사용자가 안내받은 대로 `DOCKERHUB_USERNAME`과
`DOCKERHUB_TOKEN`만 등록하면 PR Preview의 주요 흐름은 잘 돌아간다. 그런데 1816행 구간의
job만 빈 자격증명으로 Docker Hub 로그인을 시도해 실패하고, 이미지 태그도 `/`로 시작하는
잘못된 문자열이 된다.

"어떤 job은 되고 어떤 job만 안 되는" 형태라, 로그를 봐도 Secret 이름이 다르다는 것을
알아채기 어렵다. Secret은 마스킹되어 값이 보이지 않으므로 더 그렇다.

## 변경 사항

- `.github/workflows/project-types/spring/server-deploy/PROJECT-SPRING-PR-PREVIEW.yaml`:
  `DOCKER_USERNAME` → `DOCKERHUB_USERNAME`, `DOCKER_PASSWORD` → `DOCKERHUB_TOKEN` (3곳)

## 기존 사용자 영향

이 워크플로우를 쓰면서 `DOCKER_USERNAME`을 등록해 둔 레포가 있다면 그 job은 지금까지
동작하고 있었을 것이다. 다만 **같은 파일의 나머지 job이 이미 `DOCKERHUB_*`를 요구하므로,
그런 레포는 어차피 양쪽 모두 등록된 상태**여야 정상 동작했다. 따라서 실질 파급은 없다.

이제는 `DOCKERHUB_*` 한 벌만 등록하면 되고, 배포 방식을 다른 워크플로우로 바꿔도 같은
Secret을 재사용할 수 있다.

## 주의사항

### 같은 목적의 Secret 이름이 두 벌 나오면 의심할 것

설치 후 검증(#549)의 Secret 수집 결과를 볼 때, 한 배포 세트에서 같은 역할의 이름이 두 벌
등장하면 거의 확실히 불일치다. 이번이 그 사례다.

### 다른 타입은 점검했다

- `PROJECT-PYTHON-PR-PREVIEW`는 원래 `DOCKERHUB_*`만 써서 문제없었다.
- 레포 전체에서 `secrets.DOCKER_USERNAME` / `secrets.DOCKER_PASSWORD` 잔여 **0건** 확인.

### 새 배포 워크플로우를 추가할 때

Docker Hub 자격증명은 `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN`으로 통일한다. 다른 이름을
쓰면 사용자가 같은 값을 두 번 등록해야 하고, 이번처럼 일부 job만 실패하는 형태의 버그가 난다.

## 검증 결과

| 항목 | 결과 |
|---|---|
| spring server-deploy Secret 수집 | 9종 → **7종** (중복 쌍 해소) |
| 레포 전체 `DOCKER_*` 잔여 | 0건 |
| YAML 파싱 | 정상 |
| `npm test` | 330/330 통과 |

## 관련

- 발견 경로: #549 설치 후 검증 기능
- 구현 커밋: `ffc10d6`
