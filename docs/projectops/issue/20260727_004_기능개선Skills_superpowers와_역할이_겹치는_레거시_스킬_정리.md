📝 현재 문제점
---

스킬이 24종까지 늘었는데, 그중 상당수가 **실제로 쓰이지 않습니다.** 저장소에 쌓인 산출물이 그 사실을 그대로 보여줍니다.

| 산출물 폴더 | 파일 수 |
|---|---|
| issue | 134 |
| report | 156 |
| testcase | 4 |
| review | 2 |
| analyze | 1 |
| plan | 1 |
| troubleshoot | 1 |

외부 시스템과 연동되는 스킬(이슈 등록, 보고서 게시)은 활발히 쓰이는 반면, **설계·계획·구현 계열은 사실상 0건**입니다.

원인은 분명합니다. 그 자리를 `superpowers`(brainstorming → writing-plans → executing-plans)가 이미 채우고 있습니다. 같은 일을 하는 경로가 둘이면 사용자는 매번 어느 쪽을 부를지 판단해야 하고, 실제로는 더 잘 동작하는 쪽만 쓰게 됩니다.

여기에 더해 **단순 안내문 수준의 스킬**이 여럿 있습니다. `pro-design`(70줄), `pro-document`(65줄), `pro-refactor`(77줄) 등은 "이렇게 하세요"를 적어둔 것에 가까워, 그냥 요청하는 것 대비 얻는 것이 거의 없습니다.

역할이 겹치는 경우도 있습니다. `pro-document`(문서화)는 `pro-report`(보고서 생성)와 사실상 같은 일을 합니다.

🛠️ 해결 방안 / 제안 기능
---

쓰이지 않거나 역할이 겹치는 스킬을 정리해 **24종에서 17종으로** 줄입니다. 처리 방식은 두 가지로 나눕니다.

**삭제 (7종)** — 대체재가 명확하고 산출물 실적이 없는 것

| 스킬 | 삭제 사유 | 대체 |
|---|---|---|
| `pro-design` | 안내문 수준, 산출물 0건 | `superpowers:brainstorming` |
| `pro-design-analyze` | 위와 동일 | 〃 |
| `pro-refactor` | 안내문 수준, 산출물 0건 | `superpowers:writing-plans` |
| `pro-refactor-analyze` | 위와 동일 | 〃 |
| `pro-test` | 산출물 0건 | `pro-testcase`(유지) |
| `pro-ppt` | 산출물 0건 | 없음 (필요 시 직접 요청) |
| `pro-document` | `pro-report`와 역할 중복 | `pro-report` |

**숨김 (3종)** — 흐름 자체는 superpowers로 옮겼으나, 기존 사용자를 위해 경로는 남기는 것

| 스킬 | 처리 |
|---|---|
| `pro-plan` | 자동 트리거 차단, 명시 호출(`/pro-plan`) 시에만 동작 |
| `pro-analyze` | 〃 |
| `pro-implement` | 〃 |

파일과 기능은 그대로 두고 description에서 트리거 문구만 제거합니다. 평소에는 superpowers가 잡되, 기존 사용자가 명시적으로 부르면 여전히 동작합니다.

**유지**

`pro-testcase`(실사용 중), `pro-spring-test`(추후 고도화 예정), 그 외 외부 연동 스킬 전부.

⚙️ 작업 내용
---

- `skills/` 하위 7종 폴더 삭제
- 숨김 3종의 description을 명시 호출 전용으로 수정
- 참조 정리: `CLAUDE.md`(스킬 목록·라우팅 표·워크플로우 체인), `README.md`, `docs/SKILLS.md`, `skills/references/common-rules.md`, `skills/references/doc-output-path.md`
- `test/rename-consistency.test.js`의 스킬 목록 검사를 17종으로 갱신
- 라우팅 표에서 설계·계획·구현을 superpowers로 넘기고, 숨김 3종의 위치를 명시

**⚠️ 호환성 영향**

삭제된 7종은 이미 설치한 사용자에게서도 사라집니다. 다만 해당 스킬들은 로컬 파일만 읽고 쓰는 안내형이라 외부 상태를 남기지 않으며, 삭제로 인해 깨지는 파이프라인이 없습니다. 숨김 3종은 명시 호출 경로를 유지하므로 영향이 없습니다.

🙋‍♂️ 담당자
---

- **백엔드**: Cassiiopeia
- **프론트엔드**: -
- **디자인**: -
