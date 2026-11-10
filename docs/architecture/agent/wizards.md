# Flutter 마법사 규칙

> **언제 읽나:** `.github/util/flutter/` 의 마법사(testflight · playstore · firebase · oauth)나 `_shared/` 를 건드릴 때
> `CLAUDE.md` 에서 옮긴 정본입니다. `CLAUDE.md` 에는 요약과 이 문서로 가는 링크만 있습니다.

### ⚠️ Flutter 마법사 4종은 공통 자산을 공유한다 (#521 — agent 필독)

`testflight` / `playstore` / `firebase` / `oauth`(#156) 마법사는 **`.github/util/flutter/_shared/`의 정본을 함께 쓴다.**
과거 각자 복사본을 들고 있다가 CSS 377줄 중복·같은 클래스명 반대 의미·iOS에만 개선 축적 같은 드리프트가 생겨 통합했다.

| 파일 | 역할 |
|------|------|
| `_shared/wizard.css` | 공통 컴포넌트 스타일 (툴팁·모달·토스트·코드블록·커스텀 Secret 등) |
| `_shared/wizard-common.js` | 공통 유틸 (이스케이프·클립보드·파일 변환·OS 감지·상태 저장·변경 이력 모달) |
| `_shared/wizard-i18n.js` | 언어 전환 엔진 (영문 기본·한국어 전환, #769). common 마법사도 로드한다. 한국어는 `<name>-wizard-i18n.js` 사전에 |
| `_shared/check-consistency.py` | 4종 정합성 검증 — **CI(`PROJECT-TEMPLATE-CI`)가 실행한다** (`check_i18n.py`로 사전 키 누락·한글 잔존도 검사) |

**마법사를 건드렸으면 반드시 통과시킬 것:**

```bash
python3 .github/util/flutter/_shared/check-consistency.py
```

- **공통 유틸을 마법사 JS에서 재정의하지 않는다** (정본이 무력화된다 — 검증기가 잡는다).
- **로드 순서 고정**: `wizard.css` → `wizard-common.js` → `<name>-wizard.js`. 공통이 뒤로 가면 마법사 구현을 덮어쓴다.
- **`.step-indicator`는 "개별 단계 항목"이다** (전체 컨테이너 아님). firebase가 반대로 써서 충돌했던 자리다.
- **oauth 마법사는 단계가 동적이다** — 고른 제공자(Kakao·Google)의 단계만 `data-step` 순번을 받아, 공통 `showStep`·`prevStep`을 덮어쓰지 않고 쓴다. `.py`는 위치인자 이력이 없어 argparse이고, 공통 블록은 `쓰기 게이트`만 testflight·playstore와 글자 단위로 같게 둔다.
- **Python CLI 정본은 명명 플래그**(`--project-path` 등)이고, 구 위치인자 호출도 계속 받는다(마법사 HTML이 배포한 명령어가 그 형식).
- **`--dry-run`은 선언만 하면 안 된다.** 쓰기·복사·이동·삭제·디렉터리 생성·`keytool`이 전부 게이트 함수를 거쳐야 하고, "쓰고 다시 읽어 검증"하는 단계 때문에 메모리 오버레이로 실제 실행과 같은 경로를 타야 한다.
- `version.json`을 고쳤으면 해당 마법사의 `./version-sync.sh`를 실행해야 화면 변경 이력에 반영된다.
- `_` 로 시작하는 폴더는 모듈이 아니라 공유 자산이다 (`src/core/copy/util.js`의 모듈 카운트에서 제외됨).

상세: `.github/util/flutter/_shared/README.md`
