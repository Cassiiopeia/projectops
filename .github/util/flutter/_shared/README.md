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
| `wizard-i18n.js` | 언어 전환 엔진 (en 기본·ko 전환, 선택 저장) + 공통 문구 사전. common 마법사도 이 파일을 로드한다 (#769) |
| `wizard-common.js` | 3종 공통 유틸 (이스케이프·클립보드·파일 변환·OS 감지·상태 저장·변경 이력 모달) + testflight·playstore에 같던 흐름 기본 구현(`showStep`·`prevStep`·`saveState`·`clearState`·커스텀 Secret) |
| `check-consistency.py` | 3종이 다시 갈라지면 검출하는 정합성 검증기 |
| `check_i18n.py` | 사전 키 누락(en·ko)·안 쓰는 키·HTML 한글 잔존 검사 (check-consistency.py 가 함께 실행) |
| `test_wizard_cli.py` | Python CLI 계약과 `--dry-run` 안전성 회귀 테스트 |

---

## 규칙

### 1. 로드 순서를 지킨다

```html
<link rel="stylesheet" href="../_shared/wizard.css">
...
<script src="../_shared/wizard-i18n.js"></script>     <!-- 언어 엔진: 공통 유틸보다 먼저 -->
<script src="../_shared/wizard-common.js"></script>
<script src="testflight-wizard-i18n.js"></script>     <!-- 마법사 문구 사전 -->
<script src="testflight-wizard.js"></script>          <!-- 공통보다 뒤 -->
<script src="testflight-wizard-export.js"></script>   <!-- 단계별 분할 파일: 본 파일 뒤 -->
```

마법사 JS는 `<name>-wizard*.js` 여러 개로 나눌 수 있다. 분할 파일에는 **함수 선언만** 둔다
(상태·초기화 코드는 본 파일). 검증기가 폴더의 `<name>-wizard*.js`를 전부 읽고, HTML이 각각을
공통 JS 뒤에 로드하는지 확인한다.

공통이 먼저 로드돼야 마법사 JS가 필요 시 의도적으로 덮어쓸 수 있습니다.
순서가 뒤바뀌면 공통이 마법사 구현을 덮어써 조용히 동작이 바뀝니다.

### 2. 공통 유틸을 마법사 JS에서 재정의하지 않는다

같은 이름으로 다시 정의하면 정본이 무력화됩니다.
`check-consistency.py`가 중복 정의를 잡아냅니다.
흐름이 달라 덮어써야 하면 `INTENTIONAL_OVERRIDES`에 이유와 함께 등록합니다
(현재 firebase: `showStep`·`prevStep`·`addCustomSecret`·`updateCustomSecretKey`·`renderCustomSecrets`).
공통 흐름 함수는 마법사 JS의 전역 `state`·`STORAGE_KEY`·`updateProgress`·`initializeStep`·`saveCurrentStepData`를 부릅니다.

### 3. 무엇을 공통에 두고 무엇을 각자 두나

| 공통 (`_shared/`) | 각 마법사 |
|---|---|
| 마법사 흐름과 무관한 순수 유틸 | 갈라진 단계 이동(`goToStep`/`nextStep`)·상태 복원(`loadState`) |
| testflight·playstore에 글자 단위로 같던 흐름 함수 | `initializeStep`·`saveCurrentStepData` 등 단계 내용 |
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

### 5. 화면 문구는 영문이 기본이고 한국어는 사전에 둔다 (#769)

- **정적 마크업**: HTML 본문은 영문으로 쓰고 `data-i18n="키"`를 단다. 한국어는 `<name>-wizard-i18n.js`의 `ko`에 둔다.
  placeholder·title은 `data-i18n-placeholder`·`data-i18n-title`.
- **JS 문구**(토스트·동적 렌더): `translate('키', {값})` — 사전 `en`·`ko` 둘 다 둔다.
- **복사해 쓰는 산출물**(명령어·yaml·Fastfile·Secret 이름·JSON 키)은 번역하지 않는다. 두 언어에서 바이트 단위로 같다.
- `data-i18n`은 글자·인라인 태그만 든 요소에 단다. 입력칸·버튼·JS가 고쳐 쓰는 요소를 감싸면 언어 전환 때 지워진다.
- 키는 문자열 그대로 쓴다(조립 금지) — 검증기가 안 쓰는 키를 잡는다.
- 사전은 JSON 형식이다(`check_i18n.py`가 파싱). 블록 안 주석·후행 쉼표 금지.
- 언어 결정: 주소 `?lang=` > 저장된 선택 > 브라우저 언어가 `ko*`면 한국어 > 영문.
  바꾸면 `wizardlanguagechange` 이벤트가 나가고, 동적 영역은 각 마법사가 다시 그린다.

### 6. Python CLI는 명명 플래그가 정본이다

```bash
python3 testflight-wizard.py setup --project-path . --bundle-id com.x.y ... --dry-run
```

구 위치인자 호출도 계속 받습니다 — 마법사 HTML이 이미 배포한 명령어가 그 형식이기 때문입니다.
공통 옵션 `--dry-run` / `--no-backup` / `--non-interactive` 는 3종 모두 지원해야 합니다.

### 7. `.py` 공통 블록은 글자 단위로 같게 둔다

testflight·playstore `.py`의 `# >>> 공통 블록: 쓰기 게이트`·`# >>> 공통 블록: 인자 계약` 구간은
두 파일이 같아야 하고, 검증기가 비교한다. 공용 모듈로 빼지 않는 이유: `.py`는 단일 파일로
실행·배포된다(firebase ZIP은 `.py` 하나만 담는다). 인코딩·개행 처리는 블록 밖
`_READ_KWARGS`·`_WRITE_KWARGS`로 마법사마다 둔다. firebase는 위치인자 호출 이력이 없어
argparse로 같은 플래그를 받고, dry-run은 함수 인자로 전달한다.

`--dry-run`은 **선언만 하면 안 됩니다.** 파일을 바꾸는 모든 원시 동작
(쓰기·복사·이동·삭제·디렉터리 생성·keytool)은 게이트 함수를 거쳐야 하고,
"쓰고 다시 읽어 검증"하는 단계를 위해 메모리 오버레이로 실제 실행과 같은 경로를 타야 합니다.

---

## 검증

```bash
# 3종 정합성 (CSS·JS·링크·버전 동기화·CLI 계약·.py 공통 블록·첫 사용자 안내)
python3 .github/util/flutter/_shared/check-consistency.py

# CLI 계약 + dry-run 안전성 회귀 테스트
python3 -m pytest .github/util/flutter/_shared/test_wizard_cli.py -q
```

마법사를 수정했다면 **둘 다 통과시킨 뒤 커밋하세요.**
`version.json`을 고쳤다면 해당 마법사의 `./version-sync.sh`도 실행해야 화면에 반영됩니다.
