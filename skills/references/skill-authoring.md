# 스킬 문서 작성 규칙

스킬 문서(SKILL.md · references)를 **쓰거나 고칠 때** 읽는다. 스킬을 실행할 때는 필요 없다.
서브커맨드 설계는 `mcp-subcommand-rules.md`, 설정 스키마 추가는 `config-rules.md` §8.

## 참조 문서 경로 규칙 (#543)

참조 문서는 **두 종류**이고 경로 표기가 다르다. 섞으면 스킬이 문서를 못 찾고, 규정된 절차 대신
임의 판단으로 진행하게 된다.

| 종류 | 어디에 있나 | SKILL.md에서 쓰는 표기 |
|------|------------|----------------------|
| **공용 문서** (common-rules, config-rules, personas 등) | `skills/references/` | `../references/<파일>.md` |
| **스킬 고유 문서** (그 스킬만 쓰는 체크리스트 등) | `skills/<skill>/references/` | `references/<파일>.md` |

SKILL.md에서 접두사 없이 `references/<파일>` 형태로 쓰면 **자기 스킬 폴더 안**을 가리킨다. 공용 문서는
거기 없으므로 반드시 `../`를 붙인다.

> 이 규칙을 어겨 16개 스킬 50곳이 존재하지 않는 경로를 지시했고, 실제로 이슈 생성 절차 문서를 찾지
> 못해 중복 검사·승인 게이트를 건너뛴 사고가 있었다 (#543).

**같은 폴더 안(`skills/references/` 문서끼리)에서 서로를 참조할 때는 접두사 없이 파일명만 쓴다** —
`config-rules.md`. `references/`를 붙이면 자기 폴더 아래의 없는 하위 폴더를 가리키게 된다.

검증은 손으로 돌리지 않는다. CI가 매번 돌린다 (#612).

```bash
python3 -m pytest scripts/tests/test_skill_docs.py -q -k reference_paths
```

`test_skill_doc_reference_paths_exist`가 `references/` 접두사가 붙은 참조를 전수 확인한다. 예전에는
이 자리에 붙여넣기용 Python 스니펫이 있었는데, 손으로 돌려야 해서 아무도 돌리지 않았고 heredoc 금지
규약을 문서 자신이 어기고 있었다.

## 공통 규칙 문서에 무엇을 두나 (#828)

`common-rules.md`는 모든 스킬이 시작할 때 읽으므로 **모든 스킬에 해당하는 절대 규칙만** 짧게 둔다.
특정 스킬·상황에만 필요한 상세는 주제별 문서(`commit-convention.md`, `sensitive-info.md`,
`work-start-protocol.md`, `script-invocation.md`, `agent-conduct.md`)나 그 스킬의 `references/`로 옮기고,
`common-rules.md`에는 같은 제목의 한 줄 포인터를 남긴다 — 다른 문서가 절 이름으로 참조하기 때문이다.
