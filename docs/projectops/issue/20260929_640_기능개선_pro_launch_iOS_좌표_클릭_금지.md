📝 현재 문제점
---

- `pro-launch/references/app.md`의 iOS 시뮬레이터 절이 "AppleScript로 Simulator 창 클릭"을 쓸 수 있는 방법 중 하나로 안내하고 있어, 에이전트가 `cliclick`/`osascript`로 화면 좌표를 눌러 테스트하는 일이 생긴다.
- 실사고: iOS 시뮬레이터에서 네이버 로그인을 확인하다가 좌표 클릭이 사용자의 실제 마우스 커서를 움직여, 사용자가 다른 앱에서 작업 중인데 엉뚱한 앱을 눌렀다. 창 위치·크기와 앞에 뜬 창에 의존해 빗나가기도 하고, 무엇이 눌렸는지 알 수 없다.
- 프로젝트가 이미 갖춘 E2E 방식(Maestro 플로우, `tool/e2e_shot.sh`, `integration_test`)을 확인하지 않고 에이전트가 임의로 좌표 방식을 골랐다.

🛠️ 해결 방안 / 제안 기능
---

- iOS 시뮬레이터에서는 좌표로 누르지 않는다. `cliclick`, AppleScript/System Events 창 클릭, CGEvent 등 호스트 마우스를 움직이는 방법을 금지한다.
- 조작이 필요하면 프로젝트에 이미 있는 위젯 텍스트 기반 E2E(Maestro, `integration_test` 등)를 먼저 찾아 쓴다. 없으면 어느 방법을 쓸지 사용자에게 묻는다.
- `simctl`로 좌표 없이 되는 것(실행·종료·딥링크·권한·캡처)은 그대로 쓴다.
- 앱 밖 웹 인증 창은 자동 조작이 안 되므로, 앱이 요청을 보내는 데까지만 자동 확인하고 나머지는 사용자에게 부탁한다.

⚙️ 작업 내용
---

- `skills/pro-launch/references/app.md` "좌표 조작의 제약" 절 교체
- `skills/pro-launch/SKILL.md` 탭·스와이프 안내에 iOS 예외 명시
- `skills/pro-agent-test/SKILL.md` iOS 좌표 탭 항목 문구 정합화
- 완료 기준: pro-launch, pro-agent-test 테스트 통과
