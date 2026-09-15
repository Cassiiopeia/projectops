📝 현재 문제점
---

`PROJECT-SPRING-PR-PREVIEW` 워크플로우가 Docker Hub 로그인에 **서로 다른 두 쌍의 Secret
이름을 혼용**한다. 같은 파일 안에서 한쪽은 `DOCKERHUB_*`, 다른 한쪽은 `DOCKER_*`를 쓴다.

| 사용 위치 | Secret 이름 |
|---|---|
| 351, 352, 1013, 1014행 (다수 job) | `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` |
| **1816, 1817행 (Docker Hub 로그인 step 하나)** | `DOCKER_USERNAME` / `DOCKER_PASSWORD` |
| 1825행 (이미지 태그 조립) | `DOCKER_USERNAME` |

같은 타입의 다른 배포 워크플로우 3종(`SIMPLE-CICD`, `NONSTOP-TRAEFIK-CICD`,
`NONSTOP-NGINX-CICD`)은 전부 `DOCKERHUB_*`만 쓴다. 즉 **`DOCKER_*` 쪽이 어긋난 이름**이다.

**영향**: 안내받은 대로 `DOCKERHUB_USERNAME`·`DOCKERHUB_TOKEN`만 등록하면, 1816행 구간의
job은 빈 자격증명으로 Docker Hub 로그인을 시도해 실패한다. 이미지 태그도 `/`로 시작하는
잘못된 문자열이 된다. 워크플로우 대부분이 정상 동작하므로 **이 job만 골라 실패하는 형태라
원인을 찾기 어렵다.**

이 문제는 설치 후 검증 기능(#549)이 도입되자마자 Secret 수집 결과에서 드러났다. 한 배포
세트가 `DOCKER_PASSWORD`와 `DOCKERHUB_TOKEN`을 동시에 요구하는 것이 비정상 신호였다.

🛠️ 해결 방안 / 제안 기능
---

어긋난 `DOCKER_USERNAME` / `DOCKER_PASSWORD` 참조를 다수파인 `DOCKERHUB_USERNAME` /
`DOCKERHUB_TOKEN`으로 통일한다. 같은 타입의 다른 배포 워크플로우와 이름이 일치하므로,
사용자는 배포 방식을 바꿔도 같은 Secret을 재사용할 수 있다.

**기존 사용자 영향**: 이 워크플로우를 이미 쓰면서 `DOCKER_USERNAME`을 등록해 둔 레포가
있다면, 그 job은 지금까지 동작하고 있었을 것이다. 이름을 통일하면 해당 레포는
`DOCKERHUB_*`를 등록해야 한다. 다만 같은 파일의 나머지 job이 이미 `DOCKERHUB_*`를
요구하므로, 그 레포는 **어차피 양쪽 모두 등록된 상태**여야 정상 동작했다. 따라서 실질
파급은 없다고 본다.

⚙️ 작업 내용
---

- `PROJECT-SPRING-PR-PREVIEW.yaml`의 `DOCKER_USERNAME` / `DOCKER_PASSWORD` 참조 3곳을
  `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN`으로 교체
- 해당 타입 배포 세트 전체에서 Secret 이름이 한 벌로 수렴하는지 재검증
- 설치 후 검증(#549)으로 수집되는 Secret 목록이 중복 쌍 없이 나오는지 확인

🙋‍♂️ 담당자
---

- 백엔드: Cassiiopeia
