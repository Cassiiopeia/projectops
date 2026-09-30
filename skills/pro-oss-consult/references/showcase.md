# 보여주기 플레이북 (README 첫 화면 · 가치 증명)

근거: caveman(스타 약 10.8만), uv, ruff, headroom, rtk, pxpipe, context-mode, oxc, superpowers,
그리고 Trending 18개와 사용자 예시 5개(reclip·PageIndex·openship). **수치는 조사 시점(2026-09-30) 값이다.** 인용할 때 날짜를 붙인다.

이 문서의 "8개 이하"·"5MB 이하" 같은 수치는 **조사한 레포에서 관찰한 경험칙이지 GitHub의 제한이 아니다.** 어길 때 깎는 기준이 아니라
"이 정도가 읽힌다"는 참고값으로만 쓴다.

## 첫 화면 순서 (스크롤 전)

1. 로고·배너 (라이트·다크 두 벌이면 `<picture>`로 전환)
2. 태그라인 한 줄. 알려진 것과 대비하면 강하다 ("ab replacement", "Vectorless RAG")
3. 문제 한 줄
4. **증거 하나**: 전후 비교 표, 차트 하나, 데모 GIF 중 하나
5. 무엇을 측정했는지 캡션 한 줄
6. 설치 한 줄 (`npx ...`, `brew install ...`, 다운로드 버튼)
7. 배지 8개 이하(경험칙). 전부 눌러서 확인 가능한 것만 (context-mode의 `href="#"` 회사 로고는 신뢰를 깎는다)

그 아래: Why / 비교 표 / 맞지 않는 경우 / 문서 링크 / 기여 / 라이선스.
상세(옵션 전체, 설정 레퍼런스, 트러블슈팅)는 문서 사이트로 옮기고 README에서 링크한다.

## 무엇을 재나 (항상 "절감 + 품질이 유지됐다는 증거"를 짝으로)

| 성격 | 절감 | 품질 증거 |
|---|---|---|
| `cli`·`tool` | 실행 시간 (warm·cold 분리) | 출력이 같다 |
| `ai` | 입력·출력 토큰, 비용, 턴 수 | N개 중 몇 개 정답 |
| 라이브러리 | 처리량, 지연, 번들 크기 | 호환율 |
| `template` | 없어진 수작업 단계, 설정 파일·줄 수 전후, 첫 배포까지 시간 | 첫 CI 성공률 |
| `app` | (지표보다) 스크린샷·기능 표 | 스토어 평점·다운로드 수(확인 가능한 링크로) |

AI 스킬은 "아무 지시 없음"이 아니라 **"그냥 간결하게 해"라는 대조군**과 비교한다. caveman은 초기
"최대 75%"가 반박당한 뒤 대조군을 넣고 숫자를 낮춰 HONEST-NUMBERS.md를 냈다. 부풀린 숫자는 역효과다.

## 믿게 만드는 장치

- 재현 명령을 표 **위에** 둔다 (headroom의 "Proof" 절)
- 고정 입력과 seed를 커밋한다. 원본 출력 스냅샷을 커밋하면 CI가 API 키 없이 다시 계산할 수 있다
- 벤치 스크립트가 README의 `<!-- BENCHMARK-TABLE-START -->` ~ `END` 사이에 표를 쓰고,
  차트 스크립트가 그 표를 읽어 SVG를 만든다. 표와 차트가 어긋날 수 없다
- 불리한 결과도 남긴다 ("The day I hide a red row is the day you should stop trusting the green ones")
- 측정 환경·날짜·N·신뢰구간을 적는다
- 사용자가 직접 A/B를 돌릴 명령을 준다 (`caveman trial -- claude`)

## 그리는 법

| 목적 | 방법 |
|---|---|
| 대표 차트 | 정적 SVG 라이트·다크 두 벌 + `<picture>` (uv·ruff 방식: 가로 막대 하나 + 캡션 한 줄) |
| 전후 비교 | 2열 HTML 표, 헤더에 숫자 ("Normal · 69 tokens" / "Caveman · 19 tokens") |
| 데모 | vhs `.tape`을 커밋해 GIF를 다시 만들 수 있게 한다. README에는 5MB 이하 GIF(경험칙, 크면 로딩이 느려진다), 문서 사이트에는 MP4 |
| 살아있는 수치 | CI가 `stats.json`을 갱신하고 shields.io `dynamic/json` 배지가 읽는다 |
| 스타 추이 | star-history 차트 (다크 모드 대응) |
| 소셜 미리보기 | 1280×640 PNG, 1MB 미만(권장값). **API 업로드가 없어 사람이 Settings에서 올린다** (API 부재는 조사 시점 기준, 최신 여부 확인 필요) |

mermaid `xychart`는 조사한 레포 중 쓰는 곳이 없다. GitHub가 렌더하는 mermaid 버전에 따라 지원 여부가 달라질 수 있어(**현재 지원 버전은 확인하지 못했다, 확인 필요**) 렌더가 확인되기 전에는 권하지 않는다. 정적 SVG가 안전하다.

## 문서를 어디에 두나

- **Wiki는 권하지 않는다.** GitHub 문서: "Search engines will only index wikis with 500 or more stars that you configure to prevent public editing."
  즉 **스타 500 이상이면서 공개 편집을 막은 위키만** 색인된다. 그 외에는 색인되지 않는다 (https://docs.github.com/en/communities/documenting-your-project-with-wikis/about-wikis).
  PR 리뷰·번역 관리도 어렵다. Trending 18개 중 Wiki를 실제로 쓰는 곳은 0개, 문서 사이트는 17개였다 (조사 시점 2026-09-30).
- GitHub Pages + Starlight(다국어·랜딩 기본 제공) 또는 Docusaurus·MkDocs·VitePress.
  소스는 `website/`나 `docs/`에 두고 그 경로가 바뀔 때만 배포 워크플로우가 돈다.
- About의 homepage를 문서 사이트로 건다.
