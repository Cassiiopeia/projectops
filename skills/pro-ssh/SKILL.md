---
name: pro-ssh
description: "Run commands on remote servers over SSH (AWS EC2, Synology NAS, any Linux host), by saved name or direct host/user/key. Use for 'check the server', 'look at logs', 'is the deploy live'."
version: 2.1.0
---

# SSH — 원격 서버 SSH 접근

## When to use

- '서버 확인해줘', '로그 봐줘', 'EC2 접속해', '시놀로지 접속해'
- 'prod 검수해줘', '서버 상태 확인', '배포 됐는지 확인해줘', '서버에서 ~해줘'
- 저장된 서버 이름으로도, 저장 없이 호스트·포트·계정·비밀번호/키를 직접 넘겨서도 접속한다.

접속 실행기는 **`pro-launch` 의 `launch_cli.py ssh`** 다 (#841). 저장된 서버(`--cred`)로도, **저장 없이 접속 정보를 직접 넘겨서도** 된다.

- 쓰는 때: 서버 상태·로그·파일 확인, 배포 후 서버 검수, "서버 들어가서 ~해줘".
- **쓰지 않는 때**: 시놀로지 DSM 역방향 프록시·도메인 설정 → `pro-synology-expose` (선택 플러그인 projectops-extras에 있음).

`{SCRIPTS}` 는 pro-launch 의 `scripts/` (찾는 법은 `../pro-launch/SKILL.md`). 호출은 `{PYTHON} {SCRIPTS}/launch_cli.py …`.

## 작업 흐름

### Phase 0 — 어느 서버인가

**사용자에게 묻기 전에 프로젝트에서 찾는다.** "이룸 서버 DB" 처럼 이름만 말해도 답은 대개 레포에 있다.

1. `access show` — 이 레포에 적어 둔 붙는 법(`ssh.<환경>` · `db` · `logs`)이 있으면 그것부터 쓴다.
2. 프로젝트 파일에서 대상 서버를 찾는다 (호스트 · 계정 · 포트 · DB 호스트/이름):

   | 어디 | 무엇 |
   |---|---|
   | `application-*.yml` · `application-*.properties` (`prod` · `dev` …) | `spring.datasource.url` 의 DB 호스트·이름, 외부 API 주소 |
   | `.env*` · `docker-compose*.yml` | `DB_HOST` · `DB_NAME` · 서비스 이름 · 포트 |
   | `.github/workflows/*DEPLOY*` · `*CICD*` | `ssh` 대상 호스트 · 계정 · 포트 · 배포 경로 · 컨테이너 이름 (값이 `secrets.*` 면 이름만 안다) |

   - **비밀 값(비밀번호 · 토큰 · 키)은 출력 · 보고에 옮기지 않는다.** 읽어도 "`application-prod.yml` 의 `spring.datasource.password`" 처럼 **위치만** 말한다.
   - 찾은 호스트를 `cred list` 의 `host` 와 맞춰 본다. 맞는 저장 서버가 있으면 그것을 쓴다.
3. `cred list` 로 저장된 서버(`kind: ssh`)를 본다. `use_when` 이 지금 일에 맞는 것만 쓴다. 하나뿐이면 자동 선택, 여럿이면 번호로 고르게 한다.
   - **`scope` 가 `ask-first` 면 접속 전에 사용자에게 확인한다** ("○○ 서버에 접속해 △△ 를 보겠습니다. 진행할까요?"). 승인 없이 쓰지 않는다.
4. 위에서 못 찾았거나 사용자가 접속 정보를 이미 말했으면(예: "host 1.2.3.4 포트 2222 계정 ubuntu 키 ~/k.pem") **저장 없이 직접 접속**한다. 빠진 정보는 **한 메시지에 하나씩** 묻는다:
   1) 호스트(IP/도메인) 2) 포트(모르면 22 제안) 3) 계정 4) 인증 방식(비밀번호 / PEM 키) 5) 비밀번호 또는 키 파일 경로.
5. **기록되지 않은 경로로 접속에 성공하면 남긴다** — 다음에 다시 찾지 않게.
   - 붙는 법(비밀 없음)은 이 레포에: `access set --key ssh.<환경> --json '{"host":…,"port":…,"user":…,"cred":"<저장 이름>","source":"<찾은 파일>"}'`,
     DB 는 `access set --key db --json '{"how":"ssh",…}'` (`../pro-launch/references/server.md`). 비밀 값을 넣으면 `secret_in_value` 로 거절된다.
   - 비밀번호 · 키 같은 자격증명은 저장해도 되는지 묻고 `cred set` (아래). 사용자가 일회성이라고 하면 저장하지 않는다.

### Phase 1 — 명령 실행

사용자가 명령을 안 정했으면 목적에 맞는 명령을 agent 가 판단해 실행한다.

| 상황 | 명령 |
|---|---|
| 저장된 서버 | `ssh --cred <서버> --command '…'` (비밀번호 sudo 는 `--sudo` + `SUDO <명령>`) |
| 저장 없이 · 비밀번호 | `ssh --host H --port P --user U --password-env 변수 --command '…'` (**비밀번호를 명령줄에 쓰지 않는다** — 권한 분류기가 막고 기록에 남는다) |
| 저장 없이 · PEM 키 | `ssh --host H --port P --user U --key-path ~/k.pem --command '…'` |
| 저장된 서버의 포트·계정만 바꿔 시도 | `ssh --cred <서버> --port 2022 --command '…'` (직접 준 값이 우선) |
| 새 서버 저장 | 저장해도 되는지 묻고, 비밀번호는 사용자가 직접 넣게 한다: `! {PYTHON} {SCRIPTS}/launch_cli.py cred set --name <서버> --prompt --json '{"kind":"ssh","host":…,"port":…,"user":…,"use_when":…,"scope":…}'` (비밀번호는 `--json` 에 싣지 않는다). 키 접속이면 `--prompt` 없이 `key_path` 를 `--json` 에 넣는다 |
| 옛 `ssh` 섹션 서버 가져오기 | `cred import-ssh --dry-run` 으로 목록 확인 → 빼고 실행(값까지 복사) → 접속 확인 후 `--prune` |
| 로그 · DB | `logs --cred …` · `db --cred …` (`../pro-launch/references/server.md`) |

- **결과 code 읽기**: `remote_exit_nonzero` 는 연결은 됐고 원격 명령이 0 이 아니게 끝난 것이다(grep 결과 없음 등 — 접속 정보를 의심하지 않는다). `auth_failed`·`connect_failed`·`host_key_*` 가 접속 실패다. Windows(cmd) 서버는 `&` 로 이은 명령의 종료코드가 마지막 것만 남으니 단계마다 따로 부르거나 PowerShell 로 감싼다.
- 출력에 비밀번호가 섞이면 `***` 로 가려진다. 비밀번호 접속에는 `sshpass` 가 필요하다(없으면 `sshpass_missing`) — 키 접속을 쓰거나 아래 호환 경로를 쓴다.
- 저장된 서버로 접속하면 응답의 `memory` 에 그 서버에서 알아낸 사실(OS · docker 경로 · 컨테이너 · 로그 위치)이 실린다. 새로 알아낸 것은
  `learn --area server --scope machine --key server.<서버>.<주제> --how '…' --result ok` 로 남긴다 (계정·비밀 금지). 저장 없는 접속은 기억하지 않는다.
- 자격증명 규칙 전체: `../pro-launch/references/credentials.md`.

### Phase 2 — 결과 보고

실행 결과를 요약해 보고한다. 에러가 있으면 원인과 해결 방법을 함께 제시한다 (`references/troubleshooting.md`).

## 이 스킬에 남은 것

- `references/troubleshooting.md` — 시놀로지 docker 절대경로·`wget`·Windows PowerShell·자주 만나는 함정 (서버 종류별 지식).
- `scripts/ssh_connect.py` — paramiko 기반 호환 경로. `launch_cli` 를 못 쓰는 환경(sshpass 없는 Windows)에서만. 비밀번호는 환경변수 `SSH_PASSWORD` 로도 받는다.

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-ssh`.
Keys for this skill: the common `language`, `tone`, `rules` only.
Preferences change presentation only; approval gates, secret protection and `--dry-run` stay in force.
