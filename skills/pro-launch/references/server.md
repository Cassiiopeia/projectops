# 서버에 붙는 법 — 요청 · DB · 로그

> 언제 읽나: `http`·`db`·`logs` 를 처음 쓰거나, `access` 에 붙는 법을 적을 때. 비밀 값 저장은 `credentials.md`.

**설정이 사는 곳과 붙는 길은 프로젝트마다 다르다.** Spring 의 `application.yml` 일 수도,
`.env`·`settings.py`·`ormconfig` 일 수도 있고, 로컬 DB 일 수도 SSH 로 들어가야 닿는 DB 일
수도 컨테이너 안에서 실행해야 할 수도 있다. **스크립트가 맞히지 않는다 — 코드를 읽고 네가 판단한다.**

알아냈으면 **기록해 둔다.** 다음 실행부터는 그것을 쓴다.

## 한눈에

```bash
{PYTHON} {SCRIPTS}/launch_cli.py http --url /api/health --expect-status 200
{PYTHON} {SCRIPTS}/launch_cli.py http --method POST --url /api/items --data '{"name":"x"}' \
  --header "Authorization: Bearer $TOKEN" --save create.json
{PYTHON} {SCRIPTS}/launch_cli.py access set --key base_url --json '{"url":"http://localhost:8080"}'
{PYTHON} {SCRIPTS}/launch_cli.py access show
{PYTHON} {SCRIPTS}/launch_cli.py access unset --key base_url
{PYTHON} {SCRIPTS}/launch_cli.py db --profile db --sql "select count(*) from item"
{PYTHON} {SCRIPTS}/launch_cli.py logs --tail 100 --grep ERROR
```

| code | 다음 행동 |
|---|---|
| `base_url_required` | 경로만 줬는데 `base_url` 이 없다. 코드를 읽어 `access set --key base_url` |
| `unexpected_status` | `--expect-status` 와 다르다. 응답 본문·서버 로그를 본다 |
| `profile_not_found` · `no_log_command` | `access show` 로 적힌 키를 보고, 없으면 붙는 법을 알아내 `access set` |
| `secret_in_value` | `access` 에 비밀을 적었다. `cred set` 으로 옮기고 `{"cred":"이름"}` 만 적는다 |
| `db_timeout` · `logs_timeout` | 접속 경로(직접 · ssh · command)가 맞는지 본다. `--timeout` 을 늘리는 것은 그다음이다 |

**적어 둔 방법의 성적.** `logs` · `db --profile` · `http`(경로만 줘서 `base_url` 을 쓴 경우)가 access 기록으로
실행되면 결과를 도구가 `access_status.json` 에 직접 남긴다 — 성공이면 `verified`(날짜), 실패면
`last_fail`(날짜 · code). 오류 원문은 남기지 않는다. 미설치·환경변수 누락처럼 환경 탓인 실패는 세지 않는다.
지난번에 실패했던 방법을 다시 쓰면 응답에 `verify: true` 와 `verify_note` 가 붙는다 — 결과를 확인하고
틀렸으면 코드를 다시 읽어 `access set` 으로 고친다(고치면 그 키의 성적은 지워진다). `access show` 의
`status` · `verify` 로도 본다.

## 주소

```bash
... access set --key base_url --json '{"url":"http://localhost:8080"}'
... http --url /api/health                       # 경로만 주면 base_url 에 붙인다
... http --url https://api.example.com/v1/me --header "Authorization: Bearer $TOKEN"
```

| 인자 | 무엇 |
|---|---|
| `--method` | 기본 GET |
| `--data` | 본문. JSON 이면 `Content-Type` 을 자동으로 붙인다. `@파일` 로 파일을 읽는다 |
| `--header` | `'이름: 값'` — 여러 번 |
| `--save` | 응답 본문 저장. 이름만 주면 `$RUN_DIR/http/` 아래 |
| `--expect-status` | 다르면 `ok:false` |

- 4xx · 5xx 도 **결과다.** 예외로 끝내지 않고 상태·헤더·본문을 돌려준다.
- **요청 헤더 값은 결과에 되돌려 주지 않는다** — 이름만 남긴다(Authorization 이 기록에 남는다).
- 시나리오를 이어서 밟고 판정하는 것은 `pro-agent-test` 의 `api` 다. 여기는 한 번씩이다.
- **운영 서버에 바꾸는 요청을 보내지 않는다.** `base_url` 이 어디를 가리키는지 매번 확인한다.

## DB

```bash
... access set --key db --json '{"how":"direct","engine":"postgres",
      "host":"...","port":5432,"db":"...","user":"...","password_env":"DB_PASSWORD"}'
DB_PASSWORD=... ... db --profile db --sql "select count(*) from ..."
```

> **`access` 에는 비밀 값을 적지 않는다**(적으면 거절한다). 값은 `cred set` 으로 저장하고 `access` 에는
> `"cred":"이름"` 만 적는다. 환경변수로 받고 싶으면 `password_env` 로 어디서 읽을지만 적는다.

| how | 언제 | 적을 것 |
|---|---|---|
| `direct` | 로컬 DB · 열린 포트 | `engine`·`host`·`port`·`db`·`user` |
| `ssh` | 서버 안에서만 닿는 DB | 위 + `ssh_host`·`ssh_user` |
| `command` | 컨테이너 안 실행 등 **무엇이든** | `command` (예: `docker exec -i pg psql -U u -d d -c`) |

`command` 는 어떤 DB 든 된다. 다루는 엔진(postgres · mysql)이 아니어도 여기로 하면 된다.
인자로 직접 준 값이 기록보다 이긴다 — 기록이 낡았을 때의 탈출구다.

## 로그

```bash
... access set --key logs --json '{"command":"ssh u@h \"docker logs --tail 200 app\""}'
... logs --tail 100 --grep ERROR
```

로그는 컨테이너·파일·관리자 화면·수집 도구 어디에나 있을 수 있다. 알아내서 적어 두고 실행한다.

## 알아둘 것

- 응답이 JSON 이 아니면(HTML 오류 페이지 등) `text` 에 앞부분만 담긴다. 그것만으로 원인이
  안 보이면 서버 로그를 본다.
- 비밀번호·토큰은 `access.json`·보고·커밋에 적지 않는다. 사용자에게 받으면 **`cred set` 으로 저장**해 다음에 다시 묻지 않는다
  (`~/.projectops/config/config.json` 의 `launch.credentials`, 파일 권한 600).
- 서버에는 `ssh --cred 이름 [--sudo] --command '…'`(저장된 서버)로, 또는 저장 없이 `ssh --host H --port P --user U --password-env 변수|--key-path 키 --command '…'` 로 들어간다. 비밀번호는 명령줄이 아니라 표준입력·환경변수로만 가고,
  서버가 되풀이해 찍어도 출력에서 `***` 로 가려진다. 비밀번호 접속에는 `sshpass` 가 필요하다.
- 서버 호출 전에 `cred list` 의 `use_when` · `scope` · `notes` 를 읽고 그 안에서만 쓴다.
