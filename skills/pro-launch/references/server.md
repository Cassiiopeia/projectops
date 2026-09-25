# 서버에 붙는 법 — 요청 · DB · 로그

**설정이 사는 곳과 붙는 길은 프로젝트마다 다르다.** Spring 의 `application.yml` 일 수도,
`.env`·`settings.py`·`ormconfig` 일 수도 있고, 로컬 DB 일 수도 SSH 로 들어가야 닿는 DB 일
수도 컨테이너 안에서 실행해야 할 수도 있다. **스크립트가 맞히지 않는다 — 코드를 읽고 네가 판단한다.**

알아냈으면 **기록해 둔다.** 다음 실행부터는 그것을 쓴다.

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

> **비밀번호는 값을 적지 않는다.** `password_env` 로 **어디서 읽을지**만 적는다. 값을 적으면 거절한다.

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
- 비밀번호·토큰을 파일에 적지 않는다. 사용자에게 받아 그 실행에만 쓴다.
