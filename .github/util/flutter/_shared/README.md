# Flutter 마법사 공통 자산 (`_shared/`)

`testflight-wizard` · `playstore-wizard` · `firebase-wizard` 세 마법사가 **공유하는 정본**입니다.

---

## 왜 공유하나

세 마법사는 원래 각자 복사본을 들고 있었습니다. 그 결과:

- 컴포넌트 CSS **377줄이 두 마법사에 글자 단위로 동일하게** 중복돼 있었고,
- firebase는 그 중 20종을 아예 갖지 못해 툴팁·모달·검증 표시가 없었으며,
- `.step-indicator` 클래스가 마법사마다 **정반대 의미**로 쓰였고,
- iOS 마법사에만 개선이 쌓이고 나머지 둘로 전파되지 않았습니다.

전부 "복사본이 각자 늙어간" 결과입니다. 그래서 공유로 바꿨습니다.

### 폴더만 떼어가면요?

마법사 폴더는 **원래도 폴더 단위로만 동작**합니다 (`<script src="xxx-wizard.js">`가 외부 파일).
`_shared/`는 같은 `flutter/` 트리 안이라 복사 엔진이 통째로 함께 옮깁니다.

폴더 하나만 떼어가면 공통 CSS가 빠지지만, 레이아웃은 Tailwind CDN이 담당하므로
**페이지는 그대로 읽히고 마감만 덜 다듬어집니다.** 조용히 망가지지 않습니다.

---

## 파일

| 파일 | 역할 |
|------|------|
| `wizard.css` | 3종 공통 컴포넌트 스타일 (툴팁·코드블록·모달·토스트·업로드·커스텀 Secret 등) |
| `wizard-common.js` | 3종 공통 유틸 (이스케이프·클립보드·파일 변환·OS 감지·상태 저장·변경 이력 모달) |
| `check-consistency.py` | 3종이 다시 갈라지면 검출하는 정합성 검증기 |
| `test_wizard_cli.py` | Python CLI 계약과 `--dry-run` 안전성 회귀 테스트 |

---

## 규칙

### 1. 로드 순서를 지킨다

```html
<link rel="stylesheet" href="../_shared/wizard.css">
...
<script src="../_shared/wizard-common.js"></script>
<script src="testflight-wizard.js"></script>   <!-- 공통보다 뒤 -->
```

공통이 먼저 로드돼야 마법사 JS가 필요 시 의도적으로 덮어쓸 수 있습니다.
순서가 뒤바뀌면 공통이 마법사 구현을 덮어써 조용히 동작이 바뀝니다.

### 2. 공통 유틸을 마법사 JS에서 재정의하지 않는다

같은 이름으로 다시 정의하면 정본이 무력화됩니다.
`check-consistency.py`가 중복 정의를 잡아냅니다.

### 3. 무엇을 공통에 두고 무엇을 각자 두나

| 공통 (`_shared/`) | 각 마법사 |
|---|---|
| 마법사 흐름과 무관한 순수 유틸 | 단계 이동·상태 스키마(`saveState`/`loadState`) |
| 3종이 똑같이 쓰는 컴포넌트 스타일 | 마법사 고유 색상·브랜드 스타일 |
| 변경 이력 모달·보안 경고 같은 공통 UI 동작 | 산출물 생성(`generateXxx`)·단계별 검증 |

단계 수도 흐름도 다르므로 **흐름 관련 코드는 각자 둡니다.** 억지로 합치지 마세요.

### 4. `.step-indicator` 는 "개별 단계 항목"이다

전체 컨테이너가 아닙니다. 과거 firebase가 컨테이너 의미로 써서 충돌했습니다.

```html
<div class="flex justify-between ...">            <!-- 컨테이너: Tailwind -->
  <div class="step-indicator ..." data-step="1">  <!-- 항목 -->
    <div class="step-circle ...">1</div>
    <span>시작</span>
  </div>
</div>
```

### 5. Python CLI는 명명 플래그가 정본이다

```bash
python3 testflight-wizard.py setup --project-path . --bundle-id com.x.y ... --dry-run
```

구 위치인자 호출도 계속 받습니다 — 마법사 HTML이 이미 배포한 명령어가 그 형식이기 때문입니다.
공통 옵션 `--dry-run` / `--no-backup` / `--non-interactive` 는 3종 모두 지원해야 합니다.

`--dry-run`은 **선언만 하면 안 됩니다.** 파일을 바꾸는 모든 원시 동작
(쓰기·복사·이동·삭제·디렉터리 생성·keytool)은 게이트 함수를 거쳐야 하고,
"쓰고 다시 읽어 검증"하는 단계를 위해 메모리 오버레이로 실제 실행과 같은 경로를 타야 합니다.

---

## 검증

```bash
# 3종 정합성 (CSS·JS·링크·버전 동기화·CLI 계약·첫 사용자 안내)
python3 .github/util/flutter/_shared/check-consistency.py

# CLI 계약 + dry-run 안전성 회귀 테스트
python3 -m pytest .github/util/flutter/_shared/test_wizard_cli.py -q
```

마법사를 수정했다면 **둘 다 통과시킨 뒤 커밋하세요.**
`version.json`을 고쳤다면 해당 마법사의 `./version-sync.sh`도 실행해야 화면에 반영됩니다.
