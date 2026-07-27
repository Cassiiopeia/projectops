🗒️ 설명
---

`.github/workflows/PROJECT-COMMON-PROJECTS-SYNC-MANAGER.yaml`의 `PROJECT_URL` 환경변수에 **특정 개인 프로젝트 보드 주소가 주석 해제된 상태로 커밋**되어 있습니다.

```yaml
PROJECT_URL: 'https://github.com/users/Cassiiopeia/projects/2/views/2'
```

먼저 범위를 명확히 해둡니다. **사용자 프로젝트로는 전파되지 않습니다.** 통합 마법사가 복사하는 소스는 `project-types/common/` 쪽이고, 그 원본은 아래처럼 주석 처리된 플레이스홀더로 올바르게 되어 있습니다.

```yaml
# PROJECT_URL: 'https://github.com/orgs/YOUR-ORG/projects/1'
```

따라서 이 이슈는 사용자 피해 이슈가 아니라 **이 저장소 자체의 위생 문제이자, 원본과 복사본이 어긋난 정합성 문제**입니다.

다만 방치하면 두 가지 위험이 있습니다. 첫째, 이 저장소의 기여자가 이슈 라벨을 바꿀 때마다 저장소 소유자의 개인 보드로 동기화가 시도됩니다. 둘째, 누군가 "루트 워크플로우가 최신"이라고 판단해 루트 파일을 `common/`으로 되돌려 넣으면 그때는 실제로 사용자에게 전파됩니다. 프로젝트 규칙상 공통 워크플로우는 `project-types/common/`과 루트 두 곳을 동일하게 유지하도록 되어 있는데, 이 파일은 그 규칙이 깨진 상태입니다.

🔄 재현 방법
---

1. 이 저장소에서 아무 이슈의 상태 라벨을 변경한다 (`작업전` → `작업중` 등)
2. `PROJECT-COMMON-PROJECTS-SYNC-MANAGER` 워크플로우가 실행된다
3. 동기화 대상이 워크플로우에 하드코딩된 개인 보드로 향한다

정합성 문제는 다음으로 확인됩니다.

1. `.github/workflows/PROJECT-COMMON-PROJECTS-SYNC-MANAGER.yaml`의 `PROJECT_URL` 라인을 확인한다
2. `.github/workflows/project-types/common/PROJECT-COMMON-PROJECTS-SYNC-MANAGER.yaml`의 같은 라인을 확인한다
3. 두 파일의 값이 서로 다르다

📸 참고 자료
---

**두 파일의 현재 상태**

| 파일 | `PROJECT_URL` 상태 | 사용자 전파 |
|---|---|---|
| `project-types/common/...` (배포 원본) | 주석 처리된 플레이스홀더 | 해당 없음 (올바름) |
| `.github/workflows/...` (레포 루트 복사본) | 개인 보드 URL 활성화 | 없음 (복사 소스 아님) |

**관련 규칙**

프로젝트 기여 가이드라인은 공통 워크플로우를 `project-types/common/`(원본)과 `.github/workflows/`(복사본) **두 곳에 동일하게 유지**하도록 규정합니다. 이 파일은 그 규칙에서 벗어나 있습니다.

**참고 — 이 항목의 출처**

`#521`에서 지적된 항목 중 하나입니다. 해당 이슈의 다른 항목(Flutter Secret 이름 오기, Python 배포 워크플로우 위치)은 모두 처리되었으나 이 항목만 남았습니다.

✅ 예상 동작
---

- 저장소에 커밋되는 워크플로우에 특정 개인의 보드 주소가 활성화된 채로 들어 있지 않아야 합니다
- 이 저장소가 자체적으로 Projects 동기화를 사용한다면, 그 설정은 워크플로우 파일에 하드코딩하지 않고 저장소 변수나 secret 등 커밋되지 않는 위치에서 주입되어야 합니다
- 공통 워크플로우의 원본(`project-types/common/`)과 루트 복사본이 동일한 내용을 유지해야 합니다
- 사용자가 이 워크플로우를 받았을 때 자신의 보드 주소를 어디에 넣어야 하는지 파일 안에서 알 수 있어야 합니다 (현재 주석 안내는 이 요건을 충족하고 있으므로 유지)

⚙️ 환경 정보
---

- **대상**: `Cassiiopeia/projectops` — `.github/workflows/PROJECT-COMMON-PROJECTS-SYNC-MANAGER.yaml`
- **영향 범위**: 이 저장소 한정 (사용자 프로젝트 전파 없음 — 복사 소스는 `common/` 원본)
- **관련 이슈**: #521 (이 항목의 최초 지적 — 나머지 항목은 처리 완료)

🙋‍♂️ 담당자
---

- **백엔드**: Cassiiopeia
- **프론트엔드**: -
- **디자인**: -
