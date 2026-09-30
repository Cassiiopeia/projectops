# 앱 빌드 번호와 iOS 버전 이름 재설계 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** iOS 테스트 빌드가 닫힌 버전으로 거부되지 않고, iOS/Android 테스트와 iOS 릴리스의 빌드 번호가 동시 빌드와 순서에 무관하게 항상 우상향하며, 번호 거부를 스스로 복구하게 한다 (#643).

**Architecture:** 번호 규칙은 `build_number.py`, App Store Connect 호출은 `asc_client.py`, iOS 흐름(버전 사전 점검, 거부 분류, 아카이브부터 업로드까지의 재시도)은 `ios_release.py` 한 곳에 둔다. 워크플로는 이 스크립트들을 호출만 한다. iOS 두 워크플로는 서명과 업로드를 한 job으로 합친다.

**Tech Stack:** Python 3.10+ 표준 라이브러리(`urllib`, `plistlib`, `zipfile`, `subprocess`, `argparse`), `openssl` CLI(ES256 서명), GitHub Actions YAML, pytest, Node(`npm test`).

**Spec:** `docs/superpowers/specs/2026-09-30-app-build-number-design.md`

## Global Constraints

- 작업 브랜치는 `develop`. 시작 전 `git pull --rebase origin develop`. 커밋은 `/pro-commit`으로, 내가 만든 파일만 명시해 스테이징한다. push는 사용자 요청 시에만.
- 스크립트는 표준 라이브러리 전용, Python 3.10+ 문법까지. 외부 패키지 금지.
- 스크립트 CLI 규약: argparse 서브커맨드, stdout은 JSON 한 줄(`ok`, 데이터, `summary`, `next`), 로그는 stderr, `GITHUB_OUTPUT`이 설정되어 있으면 `key=value`를 덧붙임, `if __name__ == "__main__": sys.exit(main())`.
- 기준 시각 `EPOCH_2024 = 1704067200` (2024-01-01 00:00:00 UTC). 번호 = max(현재 UTC 초 - EPOCH_2024, 하한들).
- `version.yml`에는 어떤 번호도 쓰지 않는다. Android 릴리스(Play, Firebase CICD, 셀프호스트)는 건드리지 않는다.
- 재시도 최대 5회. 재업로드 판단용 ASC 재조회는 최대 3회, 20초 간격.
- ASC 인증 환경변수 이름: `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_KEY_PATH`. 빈 문자열은 "없음"으로 취급.
- ASC 베이스 URL `https://api.appstoreconnect.apple.com`, 목록 limit 200, HTTP timeout 30초, JWT 수명 1200초.
- 사용자 노출 문구(댓글, 로그, md)에 가운뎃점(U+00B7)과 em dash(U+2014)를 쓰지 않는다.
- 워크플로 수정 시 기존 테스트 제약 유지: job이 자기 자신을 `needs.<id>`로 참조 금지, 모든 `run:` 블록 `bash -n` 통과(heredoc 종료자 컬럼 0), IOS-TEST 파일에 `fastlane deploy`와 `DEPLOY_MODE="store_only"` 리터럴 유지, 릴리스 파일의 `STORE_WHATS_NEW_OVERRIDE`/`INPUT_WHATS_NEW_OVERRIDE` 리터럴 줄 유지.
- 워크플로 YAML은 로컬 파서 경고만으로 기존 로직을 고치지 않는다 (CLAUDE.md "워크플로우 YAML 검증").

## Review Focus

1. **ASC 버전 문자열이 비정상**(`2.1`, `2.1.2b`, 빈 값): `parse_version`이 죽지 않고 2자리는 0을 채우며 비숫자 항목은 판정에서 제외한다 → Task 3 테스트.
2. **fastlane 로그에 ANSI 색상 코드와 한국어 출력이 섞임**: `classify_upload_error`가 색상 코드를 걷어낸 뒤 분류하고 `reason_line`에 색상 코드가 남지 않는다 → Task 3 테스트.
3. **ASC 시크릿이 빈 문자열로 주입됨**(`secrets.X`가 없으면 Actions는 `""`를 넣는다): `token_from_env()`가 None을 돌려주고 모든 ASC 의존 경로가 폴백한다 → Task 2 테스트.
4. **`workflow_dispatch`로 실행되어 payload와 PR 번호가 없음**: 스크립트는 payload에 의존하지 않고, 워크플로 댓글 스텝은 기존 가드대로 건너뛴다 → Task 4 테스트(환경변수 최소 집합으로 archive-upload 성공), Task 6 검증 단계.
5. **업로드는 성공했는데 fastlane 뒤 단계(처리 대기, deliver)가 실패**: 재업로드하지 않는다 → Task 4 테스트.

---

## File Structure

| 파일 | 책임 | 작업 |
|---|---|---|
| `.github/scripts/build_number.py` | 번호 규칙 | 생성 |
| `.github/scripts/asc_client.py` | ASC JWT, HTTP, 페이지네이션, 조회 함수 | 생성 |
| `.github/scripts/ios_release.py` | 버전 판단, 거부 분류, 아카이브/서명/검증/업로드 재시도 | 생성 |
| `.github/scripts/test/test_build_number.py` | | 생성 |
| `.github/scripts/test/test_asc_client.py` | | 생성 |
| `.github/scripts/test/test_ios_release.py` | | 생성 |
| `src/core/copy/simple.js` | 사용자 레포 복사 목록 | 수정 |
| `.github/workflows/project-types/flutter/PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml` | iOS 테스트 | 수정 |
| `.github/workflows/project-types/flutter/PROJECT-FLUTTER-IOS-TESTFLIGHT.yaml` | iOS 릴리스 | 수정 |
| `.github/workflows/project-types/flutter/PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml` | 트리거 | 수정 |
| `.github/workflows/project-types/flutter/PROJECT-FLUTTER-ANDROID-TEST-APK.yaml` | Android 테스트 | 수정 |
| `.github/util/flutter/testflight-wizard/templates/ExportOptions.plist` | 신규 설치 템플릿 | 수정 |
| `.github/config/breaking-changes.json` | 경고 등록 | 수정 |
| `docs/FLUTTER-TEST-BUILD-TRIGGER.md`, `docs/FLUTTER-CICD-OVERVIEW.md`, `docs/VERSION-CONTROL.md`, `CLAUDE.md` | 문서 | 수정 |

---

### Task 1: `build_number.py`

**Files:**
- Create: `.github/scripts/build_number.py`
- Test: `.github/scripts/test/test_build_number.py`

**Interfaces:**
- Produces:
  - `EPOCH_2024: int = 1704067200`
  - `time_based_number(now: float | None = None) -> int` (now 생략 시 `time.time()`)
  - `next_build_number(floors: list[int] | None = None, now: float | None = None) -> dict` → `{"build_number": int, "source": "time" | "floor", "built_at_utc": "YYYY-MM-DDTHH:MM:SSZ"}`. 하한 중 None과 0 이하는 무시.
  - `describe(number: int) -> str` → UTC ISO 문자열
  - CLI `next [--floor N ...]`, `describe N`. `next`는 `GITHUB_OUTPUT`에 `build_number=`를 쓴다.

- [ ] **Step 1: Write the failing tests**

```python
def test_time_based_number_is_seconds_since_2024():
    assert bn.time_based_number(now=1704067200 + 86677440) == 86677440

def test_next_uses_time_when_no_floor():
    r = bn.next_build_number(now=1704067200 + 100)
    assert r == {"build_number": 100, "source": "time", "built_at_utc": "2024-01-01T00:01:40Z"}

def test_next_uses_floor_when_larger():
    r = bn.next_build_number(floors=[2026093001], now=1704067200 + 100)
    assert r["build_number"] == 2026093001 and r["source"] == "floor"

def test_next_ignores_none_and_nonpositive_floors():
    assert bn.next_build_number(floors=[None, 0, -5], now=1704067200 + 7)["build_number"] == 7

def test_monotonic_over_time():
    assert bn.time_based_number(now=1704067200 + 10) < bn.time_based_number(now=1704067200 + 11)

def test_describe_roundtrip():
    assert bn.describe(86677440) == "2026-09-30T05:04:00Z"

def test_cli_next_prints_json_and_writes_output(tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"; monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setattr(bn.time, "time", lambda: 1704067200 + 42)
    assert bn.main(["next", "--floor", "5"]) == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["ok"] is True and payload["build_number"] == 42
    assert "build_number=42" in out.read_text()
```

(`86677440` = 1,003일 × 86,400 + 18,240초 = 2026-09-30T05:04:00Z, 스펙 4.1의 예시값.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest .github/scripts/test/test_build_number.py -q`
Expected: FAIL (`ModuleNotFoundError: build_number`)

- [ ] **Step 3: Implement `.github/scripts/build_number.py`**

머리 docstring에 #643, 규칙 한 줄, "번호 규칙의 유일한 위치", 2090년 Android 상한 도달 시 `EPOCH_2024` 교체 안내를 적는다. `main(argv: list[str] | None = None) -> int`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest .github/scripts/test/test_build_number.py -q`
Expected: PASS

- [ ] **Step 5: Commit** (`/pro-commit`, 대상: 위 두 파일)

---

### Task 2: `asc_client.py`

**Files:**
- Create: `.github/scripts/asc_client.py`
- Test: `.github/scripts/test/test_asc_client.py`

**Interfaces:**
- Produces:
  - `BASE_URL = "https://api.appstoreconnect.apple.com"`
  - `class AscError(Exception)` 속성 `status: int | None`
  - `der_to_raw(der: bytes) -> bytes` (DER ECDSA 서명 → 64바이트 r‖s, 각 32바이트 좌측 0 패딩)
  - `make_jwt(key_id: str, issuer_id: str, key_path: str, now: int | None = None, ttl: int = 1200) -> str` (헤더 `{"alg":"ES256","kid":key_id,"typ":"JWT"}`, 페이로드 `{"iss","iat","exp","aud":"appstoreconnect-v1"}`, 서명은 `openssl dgst -sha256 -sign key_path`의 stdout을 `der_to_raw`)
  - `token_from_env() -> str | None` (세 환경변수 중 하나라도 비었거나 없으면 None, 서명 실패도 None + stderr 경고)
  - `request(url: str, token: str, timeout: int = 30) -> dict` (GET, 모듈 수준 함수. HTTP 오류는 `AscError(status)`)
  - `get_all(path: str, params: dict, token: str) -> list[dict]` (`limit=200`, `links.next`를 끝까지 따라감, `data` 항목을 합쳐 반환)
  - `find_app_id(bundle_id: str, token: str) -> str | None` (`/v1/apps?filter[bundleId]=`, `attributes.bundleId == bundle_id` 정확 일치만)
  - `list_app_store_versions(app_id: str, token: str) -> list[dict]` (`/v1/apps/{id}/appStoreVersions`, `filter[platform]=IOS`) → 각 항목 `{"version": str, "appVersionState": str | None, "appStoreState": str | None}`
  - `parse_build_number(value: str | None) -> int | None` (첫 번째 점 앞 성분이 정수면 그 값, 아니면 None)
  - `recent_max_build(app_id: str, token: str) -> int | None` (`/v1/builds?filter[app]=&sort=-uploadedDate` 첫 페이지와 `/v1/apps/{id}/buildUploads?sort=-uploadedDate` 첫 페이지의 `version`/`cfBundleVersion`을 `parse_build_number`로 모아 최대값. 둘 다 실패하면 None)
  - `build_exists(app_id: str, build_number: int, token: str) -> bool` (`/v1/builds?filter[app]=&filter[version]=N` 또는 buildUploads에서 `cfBundleVersion == str(N)`이 하나라도 있으면 True)

- [ ] **Step 1: Write the failing tests**

- `test_der_to_raw_pads_to_64_bytes`: r, s가 각각 31바이트, 33바이트(선행 0x00)인 DER을 손으로 조립해 결과 길이 64와 값 확인.
- `test_make_jwt_verifies_with_openssl` (openssl 없으면 skip): `openssl ecparam -name prime256v1 -genkey -noout | openssl pkcs8 -topk8 -nocrypt`로 tmp에 키 생성 → `make_jwt("KID","ISS",path,now=1000)` → 세 부분 분해, 헤더와 페이로드 JSON이 `{"alg":"ES256","kid":"KID","typ":"JWT"}`, `{"iss":"ISS","iat":1000,"exp":2200,"aud":"appstoreconnect-v1"}`, raw 서명을 DER로 되돌려 `openssl dgst -sha256 -verify pub.pem -signature` 성공.
- `test_token_from_env_none_when_empty(monkeypatch)`: 세 변수를 `""`로 설정 → None. 하나만 unset → None.
- `test_get_all_follows_next(monkeypatch)`: `request`를 가짜로 바꿔 첫 응답 `links.next` 존재, 둘째 응답 없음 → 항목 합계와 호출 횟수 2.
- `test_find_app_id_exact_match`: 가짜 응답에 `com.a.b`, `com.a` 두 앱 → `find_app_id("com.a")`는 `com.a`의 id.
- `test_parse_build_number`: `"45105"→45105`, `"45300.1"→45300`, `"abc"→None`, `None→None`, `""→None`.
- `test_recent_max_build_combines_sources`: builds 첫 페이지 `["214","45104"]`, buildUploads `["45105"]` → 45105. 둘 다 `AscError` → None.
- `test_build_exists_true_and_false`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest .github/scripts/test/test_asc_client.py -q`
Expected: FAIL (모듈 없음)

- [ ] **Step 3: Implement `.github/scripts/asc_client.py`**

`urllib.request.Request`에 `Authorization: Bearer`, `User-Agent: projectops-asc-client`. `links.next`는 절대 URL이므로 그대로 호출. 서명은 `subprocess.run(["openssl","dgst","-sha256","-sign",key_path], input=signing_input, capture_output=True, check=True)`. 이 파일은 CLI가 없는 라이브러리 모듈이다(분리 이슈의 수동 조회 워크플로가 재사용).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest .github/scripts/test/test_asc_client.py -q`
Expected: PASS (openssl 없으면 해당 1건 skip)

- [ ] **Step 5: Commit**

---

### Task 3: `ios_release.py` 판단 함수 (`precheck-version`, `classify-error`)

**Files:**
- Create: `.github/scripts/ios_release.py`
- Test: `.github/scripts/test/test_ios_release.py`

**Interfaces:**
- Consumes: `asc_client.token_from_env`, `find_app_id`, `list_app_store_versions`
- Produces:
  - `parse_version(s: str | None) -> tuple[int, int, int] | None` (정수 1~3개, 부족분 0, 비숫자면 None)
  - `format_version(t: tuple[int, int, int]) -> str`
  - `next_patch(s: str) -> str`
  - `CLOSED_VERSION_STATES = {"ACCEPTED","PENDING_DEVELOPER_RELEASE","PENDING_APPLE_RELEASE","PROCESSING_FOR_DISTRIBUTION","READY_FOR_DISTRIBUTION","REPLACED_WITH_NEW_VERSION"}`
  - `CLOSED_STORE_STATES = CLOSED_VERSION_STATES | {"READY_FOR_SALE","PROCESSING_FOR_APP_STORE","PREORDER_READY_FOR_SALE","DEVELOPER_REMOVED_FROM_SALE","REMOVED_FROM_SALE"}`
  - `closed_max(versions: list[dict]) -> str | None` (`appVersionState in CLOSED_VERSION_STATES or appStoreState in CLOSED_STORE_STATES`인 항목 중 최대, 파싱 불가 제외)
  - `decide_version(current: str, closed: str | None, mode: str) -> dict` → `{"ok": bool, "version": str, "changed": bool, "closed_max": str | None, "reason": str}`
    - `closed is None` 또는 `current > closed`: ok, 그대로
    - test 모드: ok, `next_patch(closed)`, changed True, reason `"{current}는 출시되어 닫힘 → {next}로 빌드"` (current가 closed보다 낮으면 `"{current}가 출시된 {closed}보다 낮음 → {next}로 빌드"`)
    - release 모드: ok False, version=current, reason `"{current}는 이미 출시되어 닫힌 버전입니다. version.yml 버전을 올리세요"`
  - `classify_upload_error(log: str) -> dict` → `{"kind": "duplicate" | "too_low" | "train_closed" | "other", "required_build": int | None, "closed_version": str | None, "reason_line": str}`
    - 먼저 `\x1b\[[0-9;]*m` 제거
    - train_closed: `90186` 또는 `train version '(?P<v>[\d.]+)' is closed`, `90062` 또는 `previously approved version \[(?P<v>[\d.]+)\]`, `90478` 또는 `later version has been closed` (마지막은 closed_version None)
    - too_low: `90061`, `must (contain a )?higher version than that of the previously uploaded version \[(?P<n>\d+)`, `bundle version must be higher than the previously uploaded version: '(?P<n>\d+)'`
    - duplicate: `90189`, `Redundant Binary Upload`, `DUPLICATE`, `-19232`
    - 우선순위 train_closed > too_low > duplicate > other
    - reason_line: 매칭된 줄, 없으면 `ITMS-\d+|ERROR|error|실패`를 포함한 마지막 줄, 그것도 없으면 `"업로드 실패 (사유를 로그에서 찾지 못함)"`. 앞뒤 공백 제거, 300자 절단.
  - CLI `precheck-version --mode test|release --version X --bundle-id B`: ASC 토큰 없거나 조회 실패 시 `{"ok": true, "version": X, "changed": false, "reason": "ASC 조회 불가: <원인> (version.yml 버전으로 진행)", "fallback": true}`. release 모드에서 `ok False`면 exit 1과 `::error::reason`. `GITHUB_OUTPUT`에 `version=`, `changed=`, `reason=`.
  - CLI `classify-error --log PATH`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("s,expected", [("2.1.2",(2,1,2)),("2.1",(2,1,0)),("3",(3,0,0)),("2.1.2b",None),("",None),(None,None)])
def test_parse_version(s, expected): assert ir.parse_version(s) == expected

def test_version_compare_numeric():
    assert ir.parse_version("1.20") > ir.parse_version("1.3")

def test_closed_max_uses_both_state_fields():
    vs = [{"version":"2.1.2","appVersionState":None,"appStoreState":"READY_FOR_SALE"},
          {"version":"2.2.0","appVersionState":"WAITING_FOR_REVIEW","appStoreState":None},
          {"version":"1.45.0","appVersionState":"READY_FOR_DISTRIBUTION","appStoreState":None},
          {"version":"x","appVersionState":"ACCEPTED","appStoreState":None}]
    assert ir.closed_max(vs) == "2.1.2"

def test_developer_rejected_is_open():
    assert ir.closed_max([{"version":"3.0.0","appVersionState":"DEVELOPER_REJECTED","appStoreState":None}]) is None

@pytest.mark.parametrize("current,closed,mode,ok,version,changed", [
    ("2.1.3","2.1.2","test",True,"2.1.3",False),
    ("2.1.2","2.1.2","test",True,"2.1.3",True),
    ("2.1.0","2.1.2","test",True,"2.1.3",True),
    ("2.1.2",None,"test",True,"2.1.2",False),
    ("2.1.2","2.1.2","release",False,"2.1.2",False),
    ("2.1.3","2.1.2","release",True,"2.1.3",False)])
def test_decide_version(current, closed, mode, ok, version, changed):
    r = ir.decide_version(current, closed, mode)
    assert (r["ok"], r["version"], r["changed"]) == (ok, version, changed)
```

`classify_upload_error` 샘플 (각각 kind, required_build, closed_version 단언):
- `"[altool] Invalid Pre-Release Train. The train version '2.1.2' is closed for new build submissions (90186)"` → train_closed, None, "2.1.2"
- `"This bundle is invalid. The value for key CFBundleShortVersionString [2.1.2] in the Info.plist file must contain a higher version than that of the previously approved version [2.1.2]."` → train_closed, None, "2.1.2"
- `"ERROR ITMS-90478: Invalid Version. The build with the version \"4.4\" can't be imported because a later version has been closed for new build submissions."` → train_closed, None, None
- `"The value for key CFBundleVersion [4001] in the Info.plist file must contain a higher version than that of the previously uploaded version [20240719]. With error code STATE_ERROR.VALIDATION_ERROR.90061"` → too_low, 20240719, None
- `"The bundle version must be higher than the previously uploaded version: '86677590'."` → too_low, 86677590, None
- `"ERROR ITMS-90189: \"Redundant Binary Upload. You've already uploaded a build with build number '86677440' for version number '2.1.3'.\""` → duplicate
- `"ENTITY_ERROR.ATTRIBUTE.INVALID.DUPLICATE (-19232)"` → duplicate
- `"\x1b[31m[!] Could not find App with bundle id\x1b[0m\n오류 발생"` → other, reason_line에 `\x1b` 없음
- 빈 문자열 → other, reason_line `"업로드 실패 (사유를 로그에서 찾지 못함)"`

CLI:
- `test_precheck_fallback_without_token`: 환경변수 비움 → exit 0, JSON `fallback True`, `version` 입력값 그대로.
- `test_precheck_release_closed_exits_1`: `ir.asc_client` 함수들을 monkeypatch해 closed 2.1.2 반환, `--mode release --version 2.1.2` → exit 1, stdout JSON `ok False`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest .github/scripts/test/test_ios_release.py -q`
Expected: FAIL (모듈 없음)

- [ ] **Step 3: Implement the functions and the two subcommands in `.github/scripts/ios_release.py`**

`import asc_client`는 같은 폴더 기준(`sys.path.insert(0, str(Path(__file__).resolve().parent))`). 머리 docstring에 #643, 버전 닫힘 규칙 근거(승인 순간 닫힘), "Apple 오류 해석의 유일한 위치"를 적는다.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest .github/scripts/test/test_ios_release.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

---

### Task 4: `ios_release.py archive-upload`

**Files:**
- Modify: `.github/scripts/ios_release.py`
- Test: `.github/scripts/test/test_ios_release.py`

**Interfaces:**
- Consumes: Task 1 `next_build_number`, Task 2 `token_from_env`/`find_app_id`/`recent_max_build`/`build_exists`, Task 3 `classify_upload_error`/`next_patch`
- Produces:
  - `run_cmd(cmd: list[str], cwd: str, env: dict) -> tuple[int, str]` (모듈 수준, stdout+stderr 합친 출력을 실시간으로 stderr에도 흘림. 테스트에서 monkeypatch)
  - `write_runtime_export_options(src: Path, dst: Path) -> Path` (`plistlib`로 읽어 `manageAppVersionAndBuildNumber=False` 설정 후 저장)
  - `verify_ipa(ipa: Path, version: str, build: int) -> list[str]` (불일치 설명 목록, 비면 통과. 대상: `Payload/*.app/Info.plist`, 그 아래 `PlugIns/*.appex/Info.plist`, `Watch/*.app/Info.plist`와 그 `PlugIns/*.appex`, `AppClips/*.app/Info.plist`. `plistlib.loads`로 바이너리/XML 모두 처리. 설명 형식 `"{번들 상대경로}: CFBundleVersion={값} (기대 {build}), CFBundleShortVersionString={값} (기대 {version})"`)
  - 상태 파일 `{APP_ROOT}/ios/build/ios_release_state.json`: `{"version": str, "build_number": int, "attempt": int, "ipa_path": str}`
  - CLI `archive-upload --phase build|upload`
  - 환경변수 입력: `APP_ROOT`(기본 `.`), `IOS_WORKSPACE`(기본 `Runner.xcworkspace`), `IOS_SCHEME`(기본 `Runner`), `VERSION`(필수), `MODE`(`test`|`release`, 필수), `APP_IDENTIFIER`, `IOS_PROVISIONING_PROFILE_NAME`, `BUILD_NUMBER_FLOOR`(선택), `MAX_ATTEMPTS`(기본 5), 나머지 fastlane용 env는 그대로 상속
  - 출력(JSON과 `GITHUB_OUTPUT`): `build_number`, `version`, `attempts`, `ipa_path`, `reason_line`(실패 시), `built_at_utc`

**동작:**

`--phase build`:
1. 하한 = [`BUILD_NUMBER_FLOOR`, ASC 가능 시 `recent_max_build + 1`] → `next_build_number`
2. 아카이브: cwd `{APP_ROOT}/ios`
   `xcodebuild -workspace {IOS_WORKSPACE} -scheme {IOS_SCHEME} -archivePath build/Runner.xcarchive -destination generic/platform=iOS archive CODE_SIGN_STYLE=Manual PROVISIONING_PROFILE_SPECIFIER={profile} "CODE_SIGN_IDENTITY=Apple Distribution" FLUTTER_BUILD_NUMBER={n} CURRENT_PROJECT_VERSION={n} FLUTTER_BUILD_NAME={v} MARKETING_VERSION={v}`
3. `write_runtime_export_options(ios/ExportOptions.plist, ios/build/ExportOptions.runtime.plist)` 후
   `xcodebuild -exportArchive -archivePath build/Runner.xcarchive -exportPath build/ipa -exportOptionsPlist build/ExportOptions.runtime.plist` (이전 `build/ipa`는 먼저 삭제)
4. `build/ipa/*.ipa` 하나를 찾아 `verify_ipa`. 불일치면 exit 1, `reason_line`에 첫 불일치와 "앱 확장의 버전/빌드 번호가 본체와 달라 Apple이 거부합니다" 안내.
5. 상태 파일 저장(attempt 1), 출력.

`--phase upload`:
1. 상태 파일 로드.
2. 반복 (attempt ≤ MAX_ATTEMPTS): env에 `IPA_PATH`, `BUILD_NUMBER`, `APP_VERSION`을 넣고 cwd `{APP_ROOT}/ios`에서 `bundle exec fastlane deploy`. 출력은 `build/upload_attempt_{k}.log`에도 저장.
   - 성공 → 출력 후 exit 0
   - 실패 → `classify_upload_error`
     - `other` → exit 1
     - `train_closed`: release 모드면 exit 1. test 모드면 `closed_version`이 있으면 `next_patch(closed_version)`, 없으면(90478) ASC로 `closed_max` 재계산해 `next_patch`, 그것도 불가하면 exit 1
     - 재시도 전 재업로드 확인: 토큰 없으면 exit 1(`reason_line`에 "ASC 조회 불가로 재업로드 여부를 확인할 수 없어 중단"). `build_exists(현재 번호)`를 최대 3회(20초 간격) 확인해 True면 exit 1(`reason_line` "업로드는 완료됐지만 이후 단계가 실패했습니다: <원래 사유>")
     - 새 번호 = `next_build_number(floors=[BUILD_NUMBER_FLOOR, required_build + 1 if too_low, 직전 번호 + 1])`
     - build 단계 2~4를 새 번호/버전으로 반복, 상태 갱신
3. 소진 시 exit 1, 마지막 `reason_line`.
- 대기는 모듈 수준 `sleep = time.sleep`으로 두어 테스트에서 0초로 바꾼다.

- [ ] **Step 1: Write the failing tests**

테스트 공통 픽스처: `tmp_path`를 `APP_ROOT`로, `ios/ExportOptions.plist`(XML, method app-store) 생성. `run_cmd`를 가짜로 교체:
- `xcodebuild ... archive` → 기록만, (0, "")
- `xcodebuild -exportArchive` → `build/ipa/App.ipa` zip 생성. 안에 `Payload/Runner.app/Info.plist`와 `Payload/Runner.app/PlugIns/Widget.appex/Info.plist`를 가짜의 설정값(archive 호출에서 읽은 `FLUTTER_BUILD_NUMBER`, `FLUTTER_BUILD_NAME`)으로 `plistlib.dumps(fmt=FMT_BINARY)`
- `bundle exec fastlane deploy` → 시나리오별 큐에서 (코드, 로그) 반환
`asc_client` 함수들은 시나리오별로 monkeypatch, `ir.sleep`은 no-op, `time.time`은 호출마다 1초씩 증가하는 가짜.

테스트:
- `test_build_phase_passes_build_settings_and_verifies`: archive 명령에 `FLUTTER_BUILD_NUMBER=`, `CURRENT_PROJECT_VERSION=`, `FLUTTER_BUILD_NAME=2.1.3`, `MARKETING_VERSION=2.1.3` 포함, runtime ExportOptions에 `manageAppVersionAndBuildNumber` False, 원본 ExportOptions 불변, 상태 파일 생성.
- `test_build_phase_fails_on_extension_mismatch`: 가짜 export가 appex에 다른 번호를 씀 → exit 1, `reason_line`에 `Widget.appex` 포함, fastlane 호출 0회.
- `test_upload_success_first_try`: attempts 1.
- `test_upload_duplicate_then_success`: 첫 로그 90189 → build_exists False → 두 번째 성공. 두 번째 번호 > 첫 번호, archive 2회.
- `test_upload_too_low_uses_required_floor`: 로그 `previously uploaded version [99999999]` → 두 번째 번호 == 100000000.
- `test_train_closed_test_mode_bumps_version`: 90186 `'2.1.2'` → 두 번째 archive에 `FLUTTER_BUILD_NAME=2.1.3`.
- `test_train_closed_release_mode_fails`: MODE=release → exit 1, archive 1회.
- `test_no_retry_without_asc_token`: 90189 + 토큰 없음 → exit 1, fastlane 1회.
- `test_no_reupload_when_build_already_exists`: 90189 + build_exists True → exit 1, fastlane 1회, `reason_line`에 "업로드는 완료" 포함.
- `test_other_error_fails_immediately`: exit 1, fastlane 1회.
- `test_attempts_exhausted`: 매번 90189, build_exists False → fastlane 5회 후 exit 1.
- `test_minimal_env_workflow_dispatch`: `VERSION`, `MODE`, `APP_ROOT`만 설정(토큰, 하한, 프로필 없음) → build와 upload 모두 성공 (Review Focus 4).
- `test_upload_passes_final_numbers_to_fastlane`: fastlane 호출 env의 `BUILD_NUMBER`, `APP_VERSION`, `IPA_PATH`가 최종값.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest .github/scripts/test/test_ios_release.py -q -k "phase or upload or train or retry or reupload or attempts or minimal or passes"`
Expected: FAIL

- [ ] **Step 3: Implement the functions and `archive-upload` in `.github/scripts/ios_release.py`**

- [ ] **Step 4: Run all script tests**

Run: `python -m pytest .github/scripts/test/ -q`
Expected: 전부 PASS (기존 테스트 포함)

- [ ] **Step 5: Commit**

---

### Task 5: 사용자 레포 복사 목록

**Files:**
- Modify: `src/core/copy/simple.js:13-43`
- Test: `test/copy-simple.test.js` (기존)

- [ ] **Step 1: `copyScripts()` 목록에 세 파일 추가**

각 항목 위에 주석: `// iOS/Android 테스트 빌드와 iOS 릴리스의 빌드 번호 규칙 (#643). 번호 규칙의 유일한 위치.` → `"build_number.py"`, `// App Store Connect 조회 (#643). ios_release.py가 사용.` → `"asc_client.py"`, `// iOS 버전 사전 점검, 업로드 거부 분류, 아카이브부터 업로드까지 재시도 (#643).` → `"ios_release.py"`.

- [ ] **Step 2: Run**

Run: `npm test`
Expected: PASS (`copy-simple.test.js`가 세 파일의 존재를 확인)

- [ ] **Step 3: Commit**

---

### Task 6: iOS 테스트 워크플로 재구성

**Files:**
- Modify: `.github/workflows/project-types/flutter/PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml`

**Interfaces:**
- Consumes: `ios_release.py precheck-version`, `archive-upload` (Task 3, 4)
- Produces: job `prepare-test-build` 출력 `version`, `version_changed`, `version_reason`, `commit_sha`, `commit_hash`(7자), 기존 `issue_*`, `branch_name`, `pr_number`, `build_flags`. job `build-upload-ios-test`의 스텝 id `build_phase`, `upload_phase` 출력.

- [ ] **Step 1: 머리 주석(L13-18) 갱신**

"버전은 version.yml에서 읽되 App Store에서 출시되어 닫힌 버전이면 다음 패치로 빌드", "빌드 번호는 `.github/scripts/build_number.py` 규칙(시각 기반, 항상 증가)으로 업로드 직전에 결정", "번호 거부 시 자동 재시도 (#643)".

- [ ] **Step 2: `prepare-test-build` 수정**

- `defaults.run.shell: bash`, `timeout-minutes: 30`.
- "Pull latest changes" 다음에 스텝 `커밋 고정` (id `commit`): `SHA=$(git rev-parse HEAD)`, `commit_sha`와 `commit_hash`(앞 7자) 출력.
- ASC 키 설치 스텝 추가(현 deploy job L847-853과 같은 방식, env로 시크릿 전달).
- `테스트 빌드 버전 설정`(L279-303)을 교체: `VERSION=$(./.github/scripts/version_manager.sh get | tail -n 1)` 후 `python3 .github/scripts/ios_release.py precheck-version --mode test --version "$VERSION" --bundle-id "$APP_IDENTIFIER"` (id `test_version`, working-directory 워크스페이스 루트, env `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_KEY_PATH`, `APP_IDENTIFIER: ${{ secrets.IOS_BUNDLE_ID || vars.IOS_BUNDLE_ID }}`). `build_number` 계산과 출력은 삭제, `pr_number`는 payload에서 그대로 출력.
- job outputs: `version: steps.test_version.outputs.version`, `version_changed`, `version_reason`, `commit_sha`, `commit_hash: steps.commit.outputs.commit_hash`. 기존 `build_number` 출력 삭제.
- `릴리즈 노트 생성`(L352-398): `COMMIT_SHA="${{ github.sha }}"` → `steps.commit.outputs.commit_sha`, `테스트 빌드 #$BUILD_NUMBER` → `테스트 빌드`, `BUILD_NUMBER` env 삭제.
- 준비 실패 댓글(L425~)에서 payload `build_number` 표시 삭제.

- [ ] **Step 3: `build-ios-test`와 `deploy-testflight-test`를 `build-upload-ios-test` 하나로 합침**

- `needs: [notify-start, prepare-test-build]`, 기존 `build-ios-test`의 `if`, `defaults.run.shell: bash`, `timeout-minutes: 120`.
- 체크아웃 `ref: ${{ needs.prepare-test-build.outputs.commit_sha }}`, "Pull latest changes" 스텝 삭제.
- 유지: Select Xcode, Install iOS device platform(릴리스 L324-328의 3회 재시도 루프로 교체), project-files 다운로드, .env 보장, Flutter, pub cache, pub get, Ruby, CocoaPods, 인증서, 프로필, ExportOptions 확인, Flutter build(`--build-number=1` 임시값, 주석 "최종 번호는 archive-upload가 아카이브 시 결정").
- 삭제: `Create Archive`, `Export IPA`, `Create build metadata file`, `Upload IPA artifact`, deploy job 전체의 Checkout.
- 추가(순서대로): ASC 키 설치, release-notes 다운로드(`${APP_ROOT}/`), Fastfile 확인, Install Fastlane(기존 L880-886), 진행 댓글 "준비 완료"(기존 L494 스텝), `IPA 빌드` 스텝 id `build_phase`: `python3 "$GITHUB_WORKSPACE/.github/scripts/ios_release.py" archive-upload --phase build` (env `APP_ROOT`, `VERSION: needs.prepare-test-build.outputs.version`, `MODE: test`, `IOS_PROVISIONING_PROFILE_NAME`, `APP_IDENTIFIER`, ASC 3종), 진행 댓글 "IPA 빌드 완료"(기존 L713 스텝, 번호는 `steps.build_phase.outputs.build_number`), `TestFlight 업로드` 스텝 id `upload_phase`: 기존 L888-935의 릴리스 노트 준비와 `export DEPLOY_MODE="store_only"`, `APP_IDENTIFIER`, `API_KEY_PATH`, `RELEASE_NOTES` export를 유지한 뒤 마지막 줄을 `python3 "$GITHUB_WORKSPACE/.github/scripts/ios_release.py" archive-upload --phase upload`로 교체. `bundle exec fastlane deploy`는 스크립트가 호출한다는 주석을 남긴다(`fastlane deploy` 리터럴 유지).
- 빌드 실패 댓글, 최종 성공/실패 댓글(기존 L769, L959, L1022)을 이 job으로 옮기고 `needs.build-ios-test.outputs.step*` 참조를 같은 job의 `steps.progress_step1.outputs.*`, `steps.progress_step2.outputs.*`로 바꾼다. 자기 job을 `needs.`로 참조하지 않는다.
- 최종 실패 댓글에 `steps.build_phase.outputs.reason_line || steps.upload_phase.outputs.reason_line`을 `**사유**: ...` 한 줄로 추가.

- [ ] **Step 4: 모든 댓글의 번호/버전/커밋 출처 교체**

- `github.event.client_payload.build_number` 참조 전부: notify-start 시작 댓글은 `빌드 시 결정`으로 표시, 그 외는 `steps.upload_phase.outputs.build_number || steps.build_phase.outputs.build_number`.
- 버전은 `steps.upload_phase.outputs.version || needs.prepare-test-build.outputs.version`.
- 시작 댓글 이후 첫 댓글("준비 완료")에 `version_changed == 'true'`면 `version_reason`을 한 줄로 표시.
- 커밋은 `needs.prepare-test-build.outputs.commit_hash`.
- `Notify TestFlight Upload Success`의 `github.sha` 에코 삭제 또는 commit_sha로 교체.

- [ ] **Step 5: 검증**

Run: `grep -n "client_payload.build_number\|github.sha\|build-ios-test\|deploy-testflight-test" .github/workflows/project-types/flutter/PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml`
Expected: 결과 없음 (한글이 섞인 줄은 Windows Git Bash grep이 거짓 음성을 낼 수 있으니 Grep 도구로 재확인)

Run: `python -m pytest .github/scripts/test/test_workflow_shell_syntax.py .github/scripts/test/test_release_tag_guard.py .github/scripts/test/test_workflow_permissions.py .github/scripts/test/test_fastlane_lanes.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

---

### Task 7: iOS 릴리스 워크플로 재구성

**Files:**
- Modify: `.github/workflows/project-types/flutter/PROJECT-FLUTTER-IOS-TESTFLIGHT.yaml`

- [ ] **Step 1: `prepare-build` 수정**

- `defaults.run.shell: bash`, `timeout-minutes: 30`.
- pull 다음에 `커밋 고정`(Task 6과 같은 형태), ASC 키 설치(env 전달 방식).
- `현재 버전 정보 가져오기`(L224-235): `get-code` 제거, `precheck-version --mode release --version "$VERSION" --bundle-id "$APP_IDENTIFIER"`로 버전 확정. 닫혔으면 이 스텝이 exit 1로 job을 멈춘다. 출력 `version`.
- job outputs에서 `build_number` 삭제, `commit_sha` 추가.

- [ ] **Step 2: `build-ios`와 `deploy-testflight`를 `build-upload-ios`로 합침**

- `needs: prepare-build`, `defaults.run.shell: bash`, `timeout-minutes: 120`, 체크아웃 `ref: needs.prepare-build.outputs.commit_sha`, pull 삭제.
- 유지: 기존 build-ios 스텝 중 Archive/Export/Upload IPA를 제외한 전부, Flutter build는 `--build-number=1` 임시값.
- 추가: ASC 키 설치, release-notes 다운로드, Fastfile 확인, Install Fastlane, `build_phase`(MODE release), `upload_phase`: 기존 L503-548의 env 블록(`STORE_WHATS_NEW_OVERRIDE: ${{ env.STORE_WHATS_NEW_OVERRIDE }}`, `INPUT_WHATS_NEW_OVERRIDE: ${{ github.event.inputs.whats_new_override }}` 등 리터럴 그대로)과 노트 자르기, `DEPLOY_MODE` export를 유지하고 `export APP_VERSION`/`export BUILD_NUMBER` 두 줄을 삭제(스크립트가 최종값을 넘김), 마지막 줄을 `archive-upload --phase upload`로.
- 실패 시 스텝: `if: failure()`에서 `reason_line`을 `$GITHUB_STEP_SUMMARY`에 `## iOS 릴리스 실패` 아래 한 줄로 쓰고 `echo "::error::$REASON"` (값은 env로 전달).
- 성공 에코의 `github.sha`를 commit_sha로.

- [ ] **Step 3: 검증**

Run: `python -m pytest .github/scripts/test/test_store_whats_new.py .github/scripts/test/test_workflow_shell_syntax.py .github/scripts/test/test_release_tag_guard.py .github/scripts/test/test_workflow_permissions.py .github/scripts/test/test_fastlane_lanes.py -q`
Expected: PASS

- [ ] **Step 4: Commit**

---

### Task 8: 트리거에서 번호 계산 제거

**Files:**
- Modify: `.github/workflows/project-types/flutter/PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml:365-434,449,487,517` 및 머리 주석의 번호 규칙 설명

- [ ] **Step 1: `build_number_calc` 스텝(L365-434) 삭제**

뒤 스텝들의 `if`가 `steps.build_number_calc`를 참조하면 그 조건을 앞 스텝 조건(`steps.source_info.outputs.found == 'true' && steps.check_branch.outputs.exists == 'true'`)으로 바꾼다.

- [ ] **Step 2: dispatch 두 곳(L449, L487)의 `buildNumber`를 `''`로, payload `build_number: buildNumber`는 유지(빈 값, 주석 "호환용, 빌드 워크플로가 번호를 직접 정함 (#643). 다음 minor에서 제거"). L453/L491/L517의 번호 로그 삭제.**

- [ ] **Step 3: 검증**

Run: `python -m pytest .github/scripts/test/test_comment_trigger_guard.py .github/scripts/test/test_workflow_shell_syntax.py -q`
Expected: PASS
Run: Grep 도구로 파일에서 `build_number_calc|buildCount|padStart` 검색
Expected: 없음

- [ ] **Step 4: Commit**

---

### Task 9: Android 테스트 워크플로

**Files:**
- Modify: `.github/workflows/project-types/flutter/PROJECT-FLUTTER-ANDROID-TEST-APK.yaml:298-320,715` 및 번호/커밋 참조

- [ ] **Step 1: 번호와 커밋 결정 스텝(L298-320) 교체**

- 이 스텝 바로 앞에 새 스텝 `빌드 번호 결정` (id `build_no`, working-directory 워크스페이스 루트): `python3 .github/scripts/build_number.py next`. 번호는 스크립트가 `GITHUB_OUTPUT`에 쓴 `steps.build_no.outputs.build_number`로 받는다.
- 기존 스텝: `VERSION`은 그대로, `BUILD_NUMBER="${{ steps.build_no.outputs.build_number }}"`, `COMMIT_SHA=$(git rev-parse HEAD)`(이 스텝이 체크아웃과 pull 뒤에 있는지 확인). payload `build_number`와 `run_number` 분기는 삭제. 출력 `commit_sha`를 추가해 job outputs로 노출.

- [ ] **Step 2: L715의 `COMMIT_SHA="${{ github.sha }}"`를 준비 job 출력의 커밋으로 교체**

댓글과 Firebase 노트의 번호는 기존대로 `needs.prepare-test-build.outputs.build_number`(이제 시각 기반 값).

- [ ] **Step 3: 검증**

Run: `python -m pytest .github/scripts/test/test_workflow_shell_syntax.py .github/scripts/test/test_workflow_permissions.py -q`
Expected: PASS
Run: Grep 도구로 `client_payload.build_number|github.sha|github.run_number` 검색
Expected: 없음

- [ ] **Step 4: Commit**

---

### Task 10: 템플릿, breaking change, 문서

**Files:**
- Modify: `.github/util/flutter/testflight-wizard/templates/ExportOptions.plist`
- Modify: `.github/config/breaking-changes.json`
- Modify: `docs/FLUTTER-TEST-BUILD-TRIGGER.md:86-140`, `docs/FLUTTER-CICD-OVERVIEW.md`, `docs/VERSION-CONTROL.md:25,101-108`, `CLAUDE.md`

- [ ] **Step 1: ExportOptions 템플릿에 `<key>manageAppVersionAndBuildNumber</key><false/>` 추가**

마법사 `version.json`은 올리지 않는다 (템플릿 변경만, 선례 #628).

- [ ] **Step 2: breaking-changes.json에 항목 추가**

키: 구현 시점 `version.yml` 버전의 다음 minor (현재 4.24.0이면 `"4.25.0"`). `severity: "warning"`, `title: "Flutter 테스트 빌드와 iOS 릴리스의 빌드 번호가 시각 기반으로 바뀜"`, `message`: "iOS 테스트, iOS 릴리스, Android 테스트(Firebase) 빌드 번호가 2024-01-01 UTC부터 지난 초(약 8,700만)로 바뀝니다. iOS 번호는 한 번 올라가면 이전 체계로 되돌릴 수 없습니다. iOS 릴리스 번호는 더 이상 version_code와 같지 않고, version_code는 Android 릴리스 전용입니다. Firebase 테스트 빌드를 설치한 폰은 정식 앱 설치 전에 삭제가 필요합니다. 출시되어 닫힌 버전으로 iOS 테스트 빌드를 트리거하면 자동으로 다음 패치 버전으로 빌드됩니다."

- [ ] **Step 3: 문서 갱신**

- `FLUTTER-TEST-BUILD-TRIGGER.md`: 번호 규칙 절을 시각 기반으로 교체, `0.0.0` 설명 삭제, 출시 후 버전 자동 전환과 실패 사유 표시 설명 추가.
- `FLUTTER-CICD-OVERVIEW.md`: iOS 번호 규칙, ASC API 키 역할은 App Manager 이상 권장(Developer는 읽기 권한 미확인, 없으면 폴백), 재시도 동작.
- `VERSION-CONTROL.md`: `version_code`는 Android 릴리스 전용.
- `CLAUDE.md` 핵심 스크립트 절에 한 단락: 빌드 번호 규칙은 `build_number.py` 한 곳, Apple 업로드 오류 해석은 `ios_release.py classify-error` 한 곳, 새 오류 코드는 `test_ios_release.py`에 실제 문구 샘플과 함께 추가.

- [ ] **Step 4: 검증**

Run: `python -m json.tool .github/config/breaking-changes.json > /dev/null && npm test`
Expected: 성공

- [ ] **Step 5: Commit**

---

### Task 11: 전체 검증

- [ ] **Step 1: CI와 같은 명령 전부 실행**

```bash
npm test
python -m pytest .github/scripts/test/ -q
python -m pytest skills/ -q
python -m pytest scripts/tests/ -q
python .github/util/flutter/_shared/check-consistency.py
python .github/util/flutter/_shared/test_wizard_cli.py
```
Expected: 전부 성공

- [ ] **Step 2: 실행 로직 무손상 자가 검증**

Run: `git diff --stat origin/develop` 로 변경 파일이 File Structure 표와 일치하는지 확인. 워크플로 diff에서 이번 작업과 무관한 `uses:`/`with:` 변경이 없는지 확인.

- [ ] **Step 3: 이슈 #643에 구현 완료 댓글** (`/pro-github`, 변경 파일, 테스트 결과 요약)

---

### Task 12: 실측 E2E (`/projectops:pro-agent-test`, 사용자 확인 후)

실제 TestFlight와 Firebase에 업로드하고 macOS 러너 시간을 쓴다. 시작 전 사용자에게 확인받는다. 대상 레포 Twin-Fang/elum에 이 변경을 반영(`npx projectops` 업데이트 또는 검증 브랜치)한 뒤 진행한다.

- [ ] **Step 1: 시나리오 실행** (각각 run URL, 결과, 댓글 스크린샷 또는 본문 기록)
  1. 출시되어 닫힌 버전 상태에서 iOS 테스트 빌드 → 다음 패치로 전환, 시작 후 첫 댓글에 이유, 업로드 성공, ASC에 새 번호 VALID
  2. 두 이슈에서 동시에 iOS 테스트 빌드 → 둘 다 성공, 한쪽 로그에 재시도 기록
  3. 번들 검증: 확장이 있으면 통과 확인, 없으면 확장을 넣은 버려질 브랜치로 1회
  4. 릴리스 `store_prepare` 1회 → deliver가 최종 번호 빌드를 선택
  5. Android 테스트 빌드 1회 → Firebase 업로드, 번호가 시각 기반, 커밋이 실제 HEAD
  6. 실패 사유 표시: 의도적으로 잘못된 `APP_IDENTIFIER` 등 비번호 오류 1회 → 재시도 없이 실패, 댓글에 사유 한 줄

- [ ] **Step 2: 결과를 이슈 #643에 댓글로 기록** (`/pro-github`, 시나리오별 통과/실패와 근거 링크)

- [ ] **Step 3: 이슈 라벨을 `작업완료`로 변경** (이슈는 닫지 않는다)
