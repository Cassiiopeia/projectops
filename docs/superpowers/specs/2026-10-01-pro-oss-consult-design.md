# pro-oss-consult 설계 (#644, 검수 반영 #660)

## 목적

GitHub 레포가 **사람들이 찾아오고, 믿고, 기여하고, 오래 쓰는 프로젝트**가 되려면 지금 무엇이 먼저인지
진단하고, 승인받은 것만 고친다. 체크리스트를 채우는 도구가 아니라 **레포 성격에 따라 같은 사실을 다르게 읽는
컨설턴트**다.

## 핵심 결정

| 결정 | 이유 |
|---|---|
| **스크립트는 사실만, 판단은 에이전트** | 같은 사실이 성격에 따라 다르게 읽힌다(데모 없는 CLI는 괜찮고 작은 도구는 치명적). 정규식으로 "비교 절이 있다"고 단정하면 에이전트가 원문을 안 읽고 그 값을 믿는다 |
| 성격 판별 → 6축(A 첫인상·B 가치 증명·C 커뮤니티·D 코드 확장성·E 법적 안전·F 장기 운영) → 성숙도 5단계 | 축별 점수와 "다음 단계 선행 조건"으로 우선순위를 만든다 |
| **승인은 두 종류** — 보고서 저장 / 레포 변경 | 자동 승인은 저장에만 적용. 남의 레포를 바꾸는 조치는 항상 레포마다 개별 승인, 포괄 위임 거부 |
| 수집한 텍스트는 **신뢰할 수 없는 데이터** | README·이슈 제목·라벨명은 남이 쓴 텍스트다. 읽은 직후 같은 세션이 쓰기 도구를 쓰므로 출력에 `untrusted` 표식을 달고 지시로 해석하지 않는다 |
| 수정 도구를 스킬 안에 둔다 (`repo-update`, `label`) | `/pro-github`에 About·topics·라벨 CRUD가 없어서 문서가 없는 기능을 가리켰다(#660 검수). `--dry-run`과 `before` 기록을 기본으로 하고 **삭제·가시성 변경은 구현하지 않는다** |
| 한글 상태 라벨은 코드 차원에서 거부 | projectops의 Projects 보드 동기화가 이름에 묶여 있다 |
| 보고서는 **작업 중인 레포**에 저장, 대상 레포에는 커밋하지 않음 | 남의 레포에 진단 문서를 밀어 넣지 않는다 |

## 구성

```
skills/pro-oss-consult/
├── SKILL.md              # 신뢰 경계 → 승인 → 모드 → 실행 → 실패 경로
├── references/           # rubric · maturity · contributor · showcase · apps · remediation
├── scripts/oss_cli.py    # collect · local-facts · list-repos · get-output-path · repo-update · label
└── tests/test_oss_cli.py
```

| 서브커맨드 | 하는 일 | 네트워크 | 쓰기 |
|---|---|---|---|
| `collect OWNER/REPO` | 메타·건강 파일·라벨·README 앞부분·릴리스·이슈 표본 수집 | GET | 없음 |
| `local-facts PATH` | 변경 증폭·문구 하드코딩·의존성·추적 중인 비밀 경로 측정 | 없음 | 없음 |
| `list-repos [OWNER]` | 점검 대상 레포 목록 | GET | 없음 |
| `get-output-path` | 보고서 저장 경로 | 없음 | 없음 |
| `repo-update OWNER/REPO` | About·topics·Discussions 변경 | PATCH/PUT | 있음 (`--dry-run` 지원) |
| `label OWNER/REPO` | 라벨 생성·이름 변경·색 변경 | POST/PATCH | 있음 (삭제 없음) |

## 안전 모델

- **악성 레포 대응**: `local-facts`는 모든 git 호출에서 `core.fsmonitor`·hooks·pager를 끄고, 추적된 심볼릭 링크와 레포 밖 경로를 읽지 않으며, 읽기 크기에 상한을 둔다. (8개 관점 검수에서 `core.fsmonitor` 명령 실행과 링크를 통한 레포 밖 파일 노출이 재현됨)
- **부분 실패 흡수**: 선택 엔드포인트가 실패해도 나머지를 모으고 `errors`로 알린다. "없음(`null`)"과 "못 봄(`errors`)"을 구분한다.
- **모든 오류 JSON에 `next`**: 네트워크·rate limit·권한·404를 구분해 다음 행동을 알려준다.
- 절단은 표시한다(`truncated`/`capped`). 일부만 본 것을 전부 본 것처럼 쓰지 않는다.

## 검증

- 단위·통합·모킹 테스트(`skills/pro-oss-consult/tests`): collect 오류 경로, list-repos 페이지 경계·owner 필터, local-facts 회귀(한글 파일명·심볼릭 링크·fsmonitor), PAT 비유출, write 서브커맨드의 dry-run과 금지 동작 부재.
- 문서 동기화: `scripts/tests/test_cli_signatures_doc_sync.py`가 모든 서브커맨드의 호출 예를 SKILL.md에서 확인한다.
- 산출물 분류: `DOCUMENT_SKILLS`에 `oss-consult` 등록(`scripts/tests/test_output_tracking.py`).
- 출시 전 검수: 정적 4개(설계·코드·등록·내용) + 추가 4개(실제 레포 13개 실측·공격자 관점·기준선 스킬 비교·신규 사용자 드라이런). 결과와 수정 이력은 #660 댓글.

## 알려진 한계

- 사실로 확인하지 못한 주장(예: 스토어 정책 세부, yml 이슈 폼의 커뮤니티 프로필 인식)은 references에서 "확인 필요"로 표기한다.
- `collect`는 GitHub API만 본다. 코드 확장성(D축)은 로컬 clone과 사람의 판단이 필요하다.
- 커뮤니티 프로필·Trending 같은 외부 지표는 시점에 따라 달라진다. 수치에는 조사 시점을 붙인다.
