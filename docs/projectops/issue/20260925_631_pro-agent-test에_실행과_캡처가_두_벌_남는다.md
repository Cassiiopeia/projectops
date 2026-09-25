📝 현재 문제점
---

- #629에서 실행·캡처 능력이 `pro-launch`로 떨어져 나가면, `pro-agent-test`에는 같은 기능이 두 벌 남는다. 문서도 옛 명령을 가리킨다.
- `e2e_cli.py` 문자열은 SKILL.md 7곳, references 16곳, `skills/references/doc-output-path.md:19` 1곳에 나온다. 서브커맨드 이름까지 세면 SKILL.md 약 25곳, target-web 13 · target-server 6 · devices 6 · target-other 4곳이다.
- 옮기다가 발견한 **기존 결함 2개**
  - `references/social-login.md:119`가 존재하지 않는 명령 `note trap`을 안내한다 (실제 선택지는 show/target/constraint/screen/pitfall/run)
  - `SKILL.md:59`가 "아래 5줄로 SCRIPTS를 찾는다"고 하지만 바로 아래에 그 스니펫이 없다

🛠️ 해결 방안 / 제안 기능
---

- `pro-agent-test`는 **QA 절차만** 남기고 실행·캡처는 `pro-launch`를 스크립트로 부른다.
- 옮긴 명령은 **한 마이너 버전 동안** 그대로 넘겨주고, 결과에 `next: "pro-launch의 launch_cli.py <명령>을 쓴다"`를 싣는다. 다음 마이너에서 제거한다.
- 선행: #629
- 설계: `docs/superpowers/specs/2026-09-25-pro-launch-design.md` §7

⚙️ 작업 내용
---

**CLI**
- [ ] `e2e_cli.py`에 남는 것: `scenario` · `note` · `api`(시나리오 실행, 단건 요청은 `common` / `launch http` 경유) · `other`
- [ ] 옮긴 명령(`doctor` `devices` `device` `web` `access` `logs` `db` `shrink` `get-output-path`, `detect`의 실행 탐지)은 launch_cli로 넘겨주는 얇은 층으로 바꾸고 `next`로 안내한다
- [ ] `detect`는 launch 결과에 agent-test 몫(`note target` 기록)을 덧붙여 돌려준다
- [ ] 저수준 헬퍼는 `scripts/common/`(#629)에서 가져오고 e2e_cli 안의 복사본을 지운다
- [ ] 저장 폴더: `~/.projectops/agent-test/<repo>/`에는 learned.json · 시나리오 · flows만 남는다 (이전은 #629의 `state.py`가 한다)

**문서**
- [ ] SKILL.md "실행 수단 한눈에" 표를 QA 명령 + "실행·캡처는 pro-launch" 두 덩어리로 다시 쓴다
- [ ] references 중 붙는 법(target-app · devices · target-web · target-server 일부)은 pro-launch references로 옮기고 링크만 남긴다
- [ ] 셸 예시의 `e2e_cli.py web …` 등을 `launch_cli.py …`로 바꾼다. `$SHOT_DIR` `$DEV` 변수 이름은 그대로라 예시 본문은 대부분 유지된다
- [ ] `skills/references/doc-output-path.md:19` 갱신
- [ ] 기존 결함 2개 수정: `note trap` → 실제 명령(`note pitfall`)으로, SKILL.md:59 스니펫 복원

**테스트**
- [ ] 남는 테스트(scenario · note · api · other 계열)가 새 import 경로로 통과
- [ ] 넘겨주기 층 테스트: 옛 명령을 부르면 같은 결과 + `next` 안내
- [ ] `CLI_TO_SKILL`에 `e2e_cli.py → pro-agent-test` 추가 (현재 목록에 없다). 모든 서브커맨드가 SKILL.md에 호출 예로 있어야 한다

**완료 기준**
- [ ] `pytest skills/pro-agent-test/tests skills/pro-launch/tests scripts/tests` 통과
- [ ] 실측: 기존 시나리오 하나(앱 1 · 웹 1)를 끝까지 밟아 회귀가 없다
- [ ] `grep -rn "e2e_cli.py web\|e2e_cli.py shrink\|e2e_cli.py devices" skills/` 결과가 넘겨주기 층 설명 외에는 0

🙋‍♂️ 담당자
---

- 백엔드: 
- 프론트엔드: 
- 디자인: 
