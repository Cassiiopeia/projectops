# 이 컴퓨터에서 먹힌 방식 · 토큰 · 저장 위치

> 언제 읽나: `recall`·`learn`·`forget` 을 처음 쓸 때, 상태 파일이 어디 있는지 알아야 할 때, 캡처가 토큰을 많이 먹을 때.

## 먹힌 방식을 기억한다 (쓸수록 정확해진다)

사람마다 컴퓨터마다 잘 되는 방식이 다르다(iOS 는 Maestro 가 깔린 곳에서만, Google 로그인은 `--headed` 여야 하는 곳 등).
같은 실패를 반복하지 않고 토큰을 아끼려고 **먹힌 방식을 홈에 적어 둔다.**

1. **앱·웹 작업을 시작할 때 `recall` 을 한 번 부른다.** 상위 5건, 항목당 200자 이내라 짧다.
   `verify:true` 는 실패가 앞서거나 오래된 것이니 **한 번 확인하고** 쓴다.
2. **끝나면 `learn` 으로 결과만 남긴다** — 처음 알게 된 방식이거나, 기억이 맞았는지/틀렸는지.
   맞았으면 `--result ok`, 틀렸으면 `--result fail`. 쌓일수록 순서가 정확해진다.
3. 잘못 배운 것은 `forget`.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py recall --area ios                 # --area ios|android|web|server · --scope both|repo|machine · --limit
{PYTHON} {SCRIPTS}/launch_cli.py learn --area ios --key ios.tap \
    --how "client/tool/e2e_shot.sh (Maestro) 로 위젯 텍스트를 누른다" --result ok
# 이 컴퓨터 전체에 해당하면 --scope machine (기본은 이 레포)
{PYTHON} {SCRIPTS}/launch_cli.py forget --key ios.tap --area ios
```

- **안전 규칙이 기억보다 위다.** 호스트 마우스로 좌표를 누르는 방법(`cliclick` 등)은 저장도, 꺼내기도 막힌다.
- 비밀번호·토큰·이메일 같은 비밀값은 저장을 거절한다.
- **앱 화면·좌표·함정은 여기가 아니다** — `pro-agent-test` 의 `note` 가 맡는다. 여기는 **도구·방식**만.
- 설명이 필요한 긴 사례(왜 막혔고 어떻게 풀었나)는 `pro-note` 로 남긴다. 여기에는 결론만.
- 계정은 `cred`(`credentials.md`), 방식은 `learn` 으로 나눈다.

## 토큰을 아낀다

- 화면 이미지를 읽는 것이 가장 비싸다. **텍스트로 확인되면(`assert` · 로그 · `app tree` · E2E 의 assertVisible) 스크린샷을 읽지 않는다.**
- 한 번 만든 E2E 플로우는 경로를 `learn` 으로 남겨 다시 짜지 않는다.
- 캡처는 기본 축소본(긴 변 1200px WebP)을 쓰고, 원본은 픽셀 대조처럼 꼭 필요할 때만.
- `shrink` 로 줄인다 — 파일 크기는 WebP 가, 세션 토큰은 해상도가 줄인다. 둘을 함께 해야 한다.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py shrink "$SHOT_DIR"/*.png           # 긴 변 1200 + WebP (--max-side · --quality · --keep-format)
```

## 저장 위치

| 자리 | 담는 것 |
|---|---|
| `~/.projectops/launch/<owner__repo>/` | devices.json · browser.json · access.json(**비밀 없음**) · knowledge.json · `.browser-profile/` · `shots/` |
| `~/.projectops/config/config.json` → `launch.credentials` | **자격증명**(값 포함, 파일 600). `pro-ssh`·`pro-github` 와 같은 파일 |
| `~/.projectops/launch/_machine/` | knowledge.json — 이 컴퓨터 전체에 해당하는 방식 |
| `~/.projectops/launch/.venv` | Playwright · Pillow (옛 `agent-test/.venv` 가 있으면 그것을 쓴다) |

예전에는 `~/.projectops/agent-test/` 에 섞여 있었다. 처음 부를 때 launch 몫을 옮기고
결과에 `migrated` 로 알린다. 두 번째부터는 아무 일도 없다. 브라우저가 떠 있으면 브라우저
관련은 닫은 뒤로 미룬다.
