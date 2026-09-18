# pro-agent-test — 참가자가 둘 이상인 검증 (기기 여러 대)

이슈: [#583](https://github.com/Cassiiopeia/projectops/issues/583)

## 문제

스킬은 기기를 **하나**만 전제한다. 연결·공유·초대처럼 **참가자가 둘인 흐름**은 밟을 수 없다.

| 없는 것 | 그래서 생기는 일 |
|---|---|
| 기기별 역할 | 문서의 `adb` 가 전부 맨몸이라 `-s` 를 빠뜨리고 엉뚱한 기기로 간다 |
| 기기별 빌드 | 한쪽만 재설치해도 알 방법이 없다 — 같은 버전이면 눈으로 구분 불가 |
| 기기별 좌표 | `note screen` 이 화면당 좌표를 **하나만** 기억한다 |
| 맞물리는 시나리오 | "A에서 만든 값을 B에 넣는다"를 파일로 적을 수 없다 |

**원인은 에이전트가 아니라 문서다.** SKILL.md 11곳 + `target-app.md` 19곳의 `adb` 가 전부 `-s` 없이 적혀 있고, 에이전트는 그것을 복사한다.

## 설계 원칙

1. **py 는 계산만 한다. 실행은 셸에 남긴다.** `adb` 를 CLI 로 감싸지 않는다 — 표면이 너무 넓어(`shell`·`pm`·`dumpsys`·`settings`·`emu`·`logcat`) 감싸면 adb 재구현이 되고, 탈출구를 만들면 거기로 `-s` 없는 명령이 다시 샌다.
2. **대신 하네스를 준다.** `#611` 이 만든 `env.sh` 를 확장한다. 문서에 경로·시리얼을 적지 않으면 에이전트가 지어낼 자리가 없다.
3. **남의 저장소에 설치되는 템플릿이다.** 역할 이름·앱 이름·화면 이름을 문서에 박지 않는다. 예시는 중립적인 것만 쓴다 ([#614](https://github.com/Cassiiopeia/projectops/issues/614)).
4. **선언만으로는 안 지켜진다.** 이 저장소는 같은 실수를 반복했다([#591](https://github.com/Cassiiopeia/projectops/issues/591)·[#601](https://github.com/Cassiiopeia/projectops/issues/601)·[#603](https://github.com/Cassiiopeia/projectops/issues/603)·[#612](https://github.com/Cassiiopeia/projectops/issues/612)). 문서 규약은 테스트로 강제한다.

## 1. 하네스 — 역할을 셸 변수명에 쓰지 않는다 ⚠️

처음 설계는 `export DEV_{역할명}` 이었다. **실측해 보니 동작하지 않는다.**

```
$ export DEV_만드는쪽=emulator-5554
bash: export: `DEV_만드는쪽=emulator-5554': not a valid identifier
$ echo "$DEV_만드는쪽"
만드는쪽                    # ← 터지지 않고 조용히 틀린 값
```

셸 변수명은 `[A-Za-z_][A-Za-z0-9_]*` 뿐이다. 한글·하이픈·공백이 든 역할명은 **에러 없이 엉뚱한 값으로 전개되어** `adb -s` 가 없는 기기를 가리킨다. 역할 이름은 사용자가 자기 말로 짓는 것이므로 어떤 문자든 올 수 있다.

**번호로 고정하고 이름은 값으로 담는다.**

```sh
# {RUN_DIR}/env.sh — get-output-path 와 device 가 함께 쓴다
export AGENT_TEST_RUN="20260918_583_연결_흐름"
export RUN_DIR="..."; export SHOT_DIR="..."; export PKG="com.example.app"

export DEV_COUNT=2
export ROLE1="A"; export DEV1="emulator-5554"   # A = {만드는 쪽}
export ROLE2="B"; export DEV2="emulator-5556"   # B = {받는 쪽}
export DEV="$DEV1"                               # 역할을 안 쓰는 명령의 기본 기기
```

`ROLE{n}` 에 담기는 값은 **시나리오 `roles` 의 키와 같은 문자열**이다. 시나리오가 `"device": "B"` 라고 적으면 에이전트는 `ROLE2=="B"` 를 보고 `$DEV2` 를 쓴다. 사람이 읽을 설명은 시나리오의 `roles[].note` 에 두고 `env.sh` 에는 주석으로만 단다 — 값에 넣으면 이어 붙일 키가 사라진다.

문서는 이렇게만 적는다.

```bash
source "{env_file 값}"
adb -s "$DEV1" shell input tap {x} {y}
adb -s "$DEV2" exec-out screencap -p > "$SHOT_DIR/02.png"
```

기기가 한 대면 `DEV_COUNT=1` 이고 `DEV=$DEV1` 이라 **기존 단일 기기 흐름이 그대로 돈다.**

## 2. `e2e_cli device` — 바인딩과 대조만 한다

| 액션 | 하는 일 |
|---|---|
| `device list` | 붙은 기기 · 해상도 · **설치된 빌드** · 현재 바인딩 · 불일치 경고 |
| `device bind --role {키} --serial {시리얼}` | 역할을 잡고 `env.sh` 를 다시 쓴다. `{키}` 는 **시나리오 `roles` 의 키와 같아야 한다** |
| `device unbind --role {키}` | 해제 후 `env.sh` 재작성 |
| `device show` | 현재 바인딩 |

- 바인딩은 `~/.projectops/agent-test/{repo}/devices.json` 에 둔다 (`learned.json`·`access` 와 같은 자리 — 워크트리를 오가도 남는다).
- `env.sh` 를 쓰는 함수는 **하나**(`_write_env_sh`)다. `get-output-path` 와 `device` 가 둘 다 그것을 부른다. 두 곳에서 각자 쓰면 반드시 어긋난다.
- `device` 는 `--run-dir` 또는 환경변수 `$RUN_DIR` 로 대상 실행 폴더를 안다. 둘 다 없으면 **거부한다** — "최신 폴더 추측"은 틀렸을 때 조용하다.
- 바인딩이 없고 기기가 2대 이상이면 `doctor` 와 `device list` 가 경고한다.

## 3. 빌드 대조 — 버전으로 재면 안 된다

`--dart-define` 만 바뀐 재빌드는 **versionName·versionCode 가 똑같다**. `#603` 이 정확히 그 사고였다. 그래서 **APK 해시**로 잰다.

```bash
adb -s $S shell wm size                              # 해상도
adb -s $S shell pm path {패키지}                      # base.apk 위치
adb -s $S shell sha1sum {경로}                        # 없으면 md5sum → dumpsys lastUpdateTime
adb -s $S shell dumpsys package {패키지} | ...        # versionName · versionCode
```

바인딩된 역할들의 해시가 다르면 `build_mismatch` 를 낸다 — *"같은 버전인데 APK 가 다릅니다. 한쪽만 재설치됐을 수 있습니다."*

세 단계 폴백을 두므로 **어떤 기기에서도 답이 나온다** (Google Play 이미지는 `adb root` 가 안 되지만 `pm path`·`sha1sum` 은 된다).

## 4. 좌표 — `screens` 에 변형 축

```
지금:  screens{화면: {anchor, taps, measured_on}}
바꿈:  screens{화면: {anchor, variants: {"{변형키}": {taps, measured_on, build, updated}}}}
```

- 변형키 = `{역할 키 또는 default}@{해상도}`. 역할 이름을 **값**으로만 쓰므로 어떤 문자든 안전하다 (JSON 키다).
- **하위호환**: 구 포맷은 읽는 순간 `default@{measured_on}` 변형으로 승격한다. 파일은 다음 쓰기에 갱신되고 `_NOTE_SCHEMA` 를 올린다. 기존 프로젝트 파일이 깨지지 않는다.
- 빌드 해시는 값으로 넣어 두고 **꺼낼 때 다르면 경고만** 한다. 막지 않는다 — 재빌드해도 대부분 화면은 안 바뀐다.

## 5. 시나리오 — `roles` · `device` · `capture`

```json
{ "target": "app",
  "roles": { "A": {"note": "{만드는 쪽}"}, "B": {"note": "{받는 쪽}"} },
  "steps": [
    {"device": "A", "screen": "{화면}", "do": "tap '{버튼}'",
     "expect_screen": "{결과}", "capture": "code"},
    {"device": "B", "screen": "{화면}", "do": "input ${code}",
     "expect_screen": "{결과}", "expect_server": "{확인 쿼리}"}
  ]}
```

- `device` 축만으로는 부족하다. **`capture` 와 `${이름}` 이 없으면 "A에서 만든 값을 B에 넣는다"를 여전히 못 적는다** — 이슈가 지목한 바로 그것이다.
- **`${이름}` 을 쓴다. `{이름}` 이 아니다.** 시나리오 템플릿은 이미 `{중괄호}` 를 "여기를 채워라" 표시로 쓴다. 같은 기호를 쓰면 검증기가 둘을 구분하지 못한다.
- `scenario show` 검증 3종: ① `device` 가 `roles` 에 선언됐나 ② `${이름}` 이 **앞선 단계의 `capture`** 에 있나 ③ `roles` 가 2개 이상인데 `target != app` 이면 경고 (웹 다중 컨텍스트는 이번 범위 밖).
- `roles` 없는 기존 시나리오는 **그대로 유효**하다.

## 6. 문서

- `adb` **30곳 전부** → `adb -s "$DEV1"` 형태.
- Phase 0 에 **기기 확정** 절 — 밟기 전 `device list`, 빌드 불일치가 뜨면 거기서 멈춘다.
- **테스트용 빌드 플래그는 켜고 되돌리는 것까지 한 단위** (이슈 요구 3번). `#603` 의 `build-profile.json` 과 연결해 적는다.
- 상세는 `references/devices.md` 신설. SKILL.md 에는 절 하나 + 포인터만 → **788줄이 거의 안 늘어난다.**

### 함정 9건 배치 (이슈 요구 1번)

전부 SKILL.md 에 얹지 않는다. `#581` 이 만든 타겟별 분리를 따른다.

| 어디로 | 무엇 |
|---|---|
| SKILL.md (타겟 무관 판정법) | 화면만 보고 통과시키지 않기 · 목록은 끝까지 세기 · 큰 글씨가 안 먹으면 그 화면이 스케일 단위를 쓰는지 먼저 보기 |
| `references/target-app.md` (앱 전용) | 라우팅 교체(`go`)와 푸시(`push`) 구분 · 좌표 재측정 · 빌드 플래그 3종 |

**함정은 겪은 앱 이야기로 적지 않는다.** 어떤 기술에서 나는 문제인지(Flutter·라우터·dotenv)만 적고, 특정 프로젝트·화면 이름은 넣지 않는다.

## 7. 테스트 — 회귀 방지

| 검사 | 막는 것 |
|---|---|
| `device bind/list/unbind` 계약 | |
| 빌드 해시가 다르면 `build_mismatch` | 한쪽만 재설치된 것을 못 보는 것 |
| 구 `screens` → `variants` 승격 | 기존 프로젝트 기록 파손 |
| `scenario show` 가 미선언 `device`·미정의 `${이름}` 거부 | 밟는 도중 멈추는 것 |
| **역할 이름이 셸 변수명에 들어가지 않는다** | 조용히 틀린 기기로 가는 것 |
| **문서 코드블록의 `adb ` 중 `-s` 없는 것이 0건** | 문서가 다시 에이전트를 잘못 이끄는 것 |

마지막 검사의 예외: `devices`·`start-server`·`kill-server`·`version` 은 기기를 지정하지 않는다.

## 범위 밖

- **웹 다중 컨텍스트.** `web` 은 브라우저 하나·페이지 하나라 같은 구멍이 있지만, 이번에 열면 범위가 두 배가 된다. 스키마(`roles`)가 막지 않도록만 둔다.
- **iOS 다중 시뮬레이터.** `simctl` 은 `-s` 대신 UDID 를 쓴다. 같은 모양이라 `DEV{n}` 에 UDID 를 담으면 되지만, 검증은 Android 로 한다.

---

## 구현하며 바뀐 것

설계대로 만들다 실측에서 드러난 것들. 결정의 방향은 그대로다.

| 설계 | 실제 | 왜 |
|---|---|---|
| `device bind` 는 실행 폴더를 모르면 **거부한다** | 바인딩은 저장하고 `env.sh` 만 나중에 쓴다 | 거부하면 사용자가 방금 한 일이 사라진다. "추측하지 않는다"는 지키되(여전히 추측 안 함) 한 일은 남긴다 |
| 패키지를 바인딩마다 들고 있음 | **프로젝트 단위 한 곳**(`devices.json`)에 둔다 | 역할마다 들고 있으니 누가 `env.sh` 를 다시 쓰느냐에 따라 `PKG` 가 붙었다 없어졌다 했다 |
| 역할이 있을 때만 `DEV` 를 쓴다 | **항상 쓴다.** 기기가 한 대면 그 한 대, 아니면 빈 값 | 문서가 `adb -s "$DEV"` 로 적혀 있어서 `DEV` 가 없으면 `adb -s ` 가 되어 죽는다 |
| `device list` 는 조회만 | 실행 폴더를 알면 **`env.sh` 도 새로 고친다** | 기기는 `get-output-path` 뒤에 부팅되기도 한다. 그때 `DEV` 가 빈 채 남으면 이후 모든 `adb` 가 죽는다 |
| — | `_sh_quote` 로 **모든 값**을 작은따옴표로 감싼다 | 역할 이름뿐 아니라 **경로**에도 `$`·공백·따옴표가 올 수 있다. 큰따옴표로 감싸면 `$` 가 전개되어 조용히 다른 값이 된다 |

### 실측으로 확인한 것

```
$ source env.sh && echo "$ROLE2|$ROLE3|$DEV_COUNT"
받는 쪽|it's-a/role|3        # bash 3.2 (macOS 기본), 한글·공백·아포스트로피·슬래시
```

`export DEV_{역할명}` 으로 되돌려 보면 `test_env_sh_actually_sources_in_bash` 와
`test_role_names_never_become_shell_variable_names` 가 실패한다 — 회귀가 실제로 잡힌다.

> 처음 쓴 변수명 검사가 **한 줄에 `export` 가 둘일 때 앞의 것만** 봐서, 일부러 깨뜨렸는데도
> 통과했다. 테스트를 추가만 하고 넘어갔으면 영영 몰랐을 자리다.
