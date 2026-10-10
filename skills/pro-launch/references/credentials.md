# 자격증명 · 이 맥 sudo · 원격 ssh

> 언제 읽나: 서버·DB·레지스트리·로그인 화면을 만지기 전, 사용자가 새 접속 정보를 줬을 때, 이 맥에서 `sudo` 가 필요할 때.

한 번 저장하면 다음 실행에서 다시 묻지 않는다.
`pro-ssh` · `pro-github` 가 `~/.projectops/config/config.json` 에 서버·PAT 를 두고 쓰는 것과 같은 방식이다.
`launch.credentials` 에 **이름 붙여** 값까지 저장하고(파일은 600), 목록·조회에서는 값이 `<저장됨>` 으로 가려진다.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py cred list                     # 작업 시작 때 한 번 — 무엇을 쓸 수 있나
{PYTHON} {SCRIPTS}/launch_cli.py cred show --name synology     # 값은 가려서 보여 준다 (--reveal 은 꼭 필요할 때만)
{PYTHON} {SCRIPTS}/launch_cli.py cred set --name synology --json '{"kind":"ssh","host":"h","port":22,"user":"u",
  "use_when":"서버 배포 QA","scope":"test-only","notes":"운영 컨테이너가 있으니 pops-qa- 접두사만"}'
{PYTHON} {SCRIPTS}/launch_cli.py cred unset --name synology
{PYTHON} {SCRIPTS}/launch_cli.py ssh --cred synology --sudo --command 'SUDO docker ps'   # 비밀번호 sudo 도 된다
{PYTHON} {SCRIPTS}/launch_cli.py logs --cred synology --command 'sshpass -e ssh -p $CRED_PORT $CRED_USER@$CRED_HOST "docker logs --tail 100 app"'
{PYTHON} {SCRIPTS}/launch_cli.py db --cred pg --sql "select 1"   # host·user·password 를 채운다
{PYTHON} {SCRIPTS}/launch_cli.py http --cred api --url /me        # token 이면 Authorization: Bearer
```

`cred set` 은 기존 항목에 합친다. 통째로 바꾸려면 `--replace`.

| 항목 | 의미 |
|---|---|
| `kind` | `ssh` · `dockerhub` · `db` · `http` · `github-org` · `login` · `local` · `other` |
| `ssh_server` | (폐기, 호환용) 옛 `ssh` 섹션의 서버 이름. 새로 쓰지 않는다 — `cred import-ssh` 로 값을 cred 로 옮긴다. 서버 정보와 비밀번호는 **cred 한 곳에만** 둔다 |
| `use_when` | 이 자격증명을 **언제 써도 되는지**(근거). 사용자가 허용한 범위를 그대로 적는다 |
| 로그인 계정 | `kind: login` + `provider`(google · apple · naver · kakao · custom) · `surface` · `app` · `account` · `password` · `two_factor` — 소셜·앱 로그인과 개발자 콘솔 로그인. 화면에는 `web type --cred` · `app type --cred` 로 넣는다. 필드 상세는 `web.md` 의 "로그인 정보를 저장할 때" |
| 이 맥 sudo | `kind: local` + `sudo_password` — **이 맥**에서 관리자 권한(`sudo installer -pkg …` 등)이 필요할 때. `local sudo --cred 이름 -- <명령>` 으로 쓴다 (아래) |
| `scope` | `test-only` · `test-ok` · `readonly` … 허용 범위 |
| `notes` | 지켜야 할 이름 규칙·포트 범위·서버에 있는 운영 서비스 등 알아둘 것 |

## agent 판단 규칙

- 서버·DB·레지스트리를 만지기 전에 `cred list` 를 보고 **`use_when` 이 지금 하려는 일에 맞는 것만** 쓴다.
  맞는 것이 없으면 추측해서 다른 것을 쓰지 말고 사용자에게 묻는다.
- **"로그인이 필요해서 사용자가 직접 해야 한다"고 말하기 전에 `cred list` 를 먼저 본다.** 개발자 콘솔(Apple
  Developer 등)·소셜 로그인 계정이 `kind: login` 으로 저장돼 있을 수 있다. `use_when` 이 맞으면 "할 수 없다"가 아니라
  "저장된 계정으로 시도하겠다"고 제안한다. 인증서·프로필·Secret 처럼 **외부 상태를 바꾸는 실행은 무엇이 바뀌는지
  말하고 승인받은 뒤** 한다. 2FA 처럼 사람만 할 수 있는 지점만 따로 떼어 요청한다.
- `scope` · `notes` 를 읽고 그 안에서만 움직인다(예: 테스트 이름 접두사, 지우는 것은 내가 만든 것만).
- 사용자가 새 접속 정보를 주면 **저장해도 되는지 한 번 묻고**, 허락하면 `cred set` 으로 저장해 `use_when` · `scope` · `notes` 를
  사용자 말 그대로 채운다. 다음에 다시 묻지 않는 것이 목적이다. 거절하면 그 실행에만 쓰고 저장하지 않는다.
  (사용자가 "알아서 저장해 둬" 처럼 미리 허락한 범위 안에서는 묻지 않고 저장한다.)
- 저장된 정보가 **틀렸거나 바뀌어 보이면**(로그인 실패·접속 거부) 다시 시도하거나 덮어쓰기 전에 사용자에게 먼저 묻는다. 로그인은 자동 재시도하지 않는다.
- 접속·로그인이 **통과한 방식**(어느 브라우저 모드, 어느 순서)은 `learn` 으로 남긴다 — 값은 적지 않는다. 다음 `recall` 이 꺼내 준다 (`memory.md`).
- 결과·보고·이슈·커밋에 값을 옮기지 않는다. `cred show --reveal` 은 정말 필요할 때만.
- 명령 문자열에는 비밀을 적지 않고 `$CRED_HOST` · `$CRED_USER` · `$CRED_PASSWORD` · `$CRED_TOKEN` · `$SSHPASS` 환경변수를 쓴다.
  출력에 값이 섞이면 `***` 로 가려진다.
- `access.json` 에는 비밀을 적지 않는다(값을 적으면 `secret_in_value` 로 거절한다). `access` 에는 `{"cred":"이름"}` 만 적는다 (`server.md`).

## 원격 ssh

- 저장된 서버에는 `ssh --cred 이름 [--sudo] --command '…'` 로 들어간다. `--sudo` 를 주면 원격 명령 안에서 `SUDO <명령>` 을 쓸 수 있다.
- 비밀번호는 명령줄이 아니라 표준입력·환경변수로만 가고, 서버가 되풀이해 찍어도 출력에서 `***` 로 가려진다.
- 비밀번호 접속에는 `sshpass` 가 필요하다(없으면 `sshpass_missing`). 출력은 `--max-output` 자에서 자른다.
- **서버 기억 (#841)**: `ssh` 응답의 `memory` 에는 그 서버(`server.<자격증명 이름>.*`) 기억만 실린다. 처음 접속에 성공하면
  CLI 가 OS(`uname -s`)와 시놀로지 docker 절대경로를 확인해 이 컴퓨터 범위에 남긴다(Windows 는 건너뜀).
  컨테이너 이름·로그 위치처럼 직접 알아낸 것은 `learn --area server --scope machine --key server.<서버>.<주제>` 로 남긴다(계정·비밀 금지).
- **서버 정보는 cred 한 곳에 둔다.** 옛 `ssh` 섹션이 있으면 `cred import-ssh --dry-run` 으로 목록을 보고(비밀은 가려진다),
  `--dry-run` 을 빼고 실행하면 host·user·password 값까지 가져온다. 접속이 되는지 확인한 뒤 `--prune` 을 붙여 다시 부르면
  가져온 서버가 옛 섹션에서 지워진다(지우기 전에 `config.json.bak-ssh-prune` 으로 백업, 권한 600). 이름이 cred 형식(영문·숫자·`._-`)이
  아닌 서버는 못 가져오니 `cred set` 으로 영문 이름을 붙여 직접 저장한다. `--ref` 는 참조만 만든다(비밀번호가 두 곳에 남는다).

## 이 맥의 sudo 비밀번호 (#784)

로컬 맥에서 관리자 권한이 필요한 작업(예: `sudo installer -pkg … -target /`)을 만나면, **"비밀번호는 못 넣는다"며 멈추지 말고** 저장된 자격증명부터 찾는다.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py cred list                      # kind 가 local 인 것이 있나
{PYTHON} {SCRIPTS}/launch_cli.py local sudo --cred mac -- installer -pkg /path/x.pkg -target /
```

- **첫 등록은 사용자가 터미널에서 직접 한다.** 입력은 화면에 보이지 않고, 비밀번호가 채팅·세션 기록에 들어가지 않는다.
  `! {PYTHON} {SCRIPTS}/launch_cli.py cred set --name mac --prompt` (Claude Code 에서는 `!` 접두사). `!` 로 TTY 를 못 받으면
  별도 터미널 창에서 같은 명령을 친다. 파이프·채팅으로는 받지 않는다(`no_tty` 로 거절).
- 비밀번호는 `sudo -S` 표준입력으로만 넘긴다. 명령줄·응답·로그에는 남지 않고 출력의 같은 문자열은 `***` 로 가려진다.
- `kind: local` 만 쓴다. 서버 ssh 비밀번호로 이 맥에 sudo 를 시도하지 않는다(`cred_not_local`).
- **시스템을 바꾸는 명령이다.** 실행 전에 무슨 명령인지 한 줄로 말한다. 한 번 저장했다고 아무 명령이나 돌리지 않고, `use_when` 범위 안에서 쓴다.
- 저장은 로컬 파일(`config.json`, 권한 600) 평문이다. 로컬 전용이라는 사용자 방침을 따랐고, 맥 로그인 비밀번호라는 점이 서버 키보다 민감하다는 것은 사용자가 알고 있다.
- ⚠️ **Claude Code 의 권한 분류기가 "저장된 비밀번호로 sudo" 호출을 거부할 수 있다.** 이 스킬로 우회할 수 없고 권한 설정을 바꾸지도 않는다.
  거부되면 그 사실과 사용자가 직접 칠 명령 한 줄을 알려 준다.

## 실패 code → 다음 행동

| code | 다음 행동 |
|---|---|
| `cred_required` · `name_required` | `cred list` 로 이름을 고른다. 맞는 것이 없으면 사용자에게 묻는다 |
| `cred_field_missing` | 그 자격증명에 필드가 없다. `cred show` 로 있는 필드를 본다 |
| `cred_not_local` | `kind: local` 인 자격증명만 `local sudo` 에 쓴다 |
| `no_tty` | 사용자가 `!` 접두사나 별도 터미널에서 `cred set --prompt` 를 직접 친다 |
| `sudo_failed` · `ssh_failed` | 다시 시도하지 말고 사용자에게 값이 바뀌었는지 묻는다 |
| `sshpass_missing` | `brew install sshpass` 등 설치를 제안한다 |
