---
name: pro-ssh
description: "원격 서버에 SSH로 접속해 명령을 실행하고 결과를 확인하는 skill. AWS EC2, 시놀로지 NAS, 일반 Linux 서버 등 모든 SSH 접근 가능한 서버에 사용한다. 저장된 서버 이름으로도, 저장 없이 호스트·포트·계정·비밀번호/키를 직접 넘겨서도 접속한다. 사용자가 '서버 확인해줘', '로그 봐줘', 'EC2 접속해', '시놀로지 접속해', 'prod 검수해줘', '서버 상태 확인', '배포 됐는지 확인해줘', '서버에서 ~해줘' 등을 언급하면 이 skill을 사용한다."
version: 2.1.0
---

# SSH — 원격 서버 SSH 접근

접속 실행기는 **`pro-launch` 의 `launch_cli.py ssh`** 다 (#841). 저장된 서버(`--cred`)로도, **저장 없이 접속 정보를 직접 넘겨서도** 된다.

- 쓰는 때: 서버 상태·로그·파일 확인, 배포 후 서버 검수, "서버 들어가서 ~해줘".
- **쓰지 않는 때**: 시놀로지 DSM 역방향 프록시·도메인 설정 → `pro-synology-expose`.

`{SCRIPTS}` 는 pro-launch 의 `scripts/` (찾는 법은 `../pro-launch/SKILL.md`). 호출은 `{PYTHON} {SCRIPTS}/launch_cli.py …`.

## 작업 흐름

### Phase 0 — 어느 서버인가

1. `cred list` 로 저장된 서버(`kind: ssh`)를 본다. `use_when` 이 지금 일에 맞는 것만 쓴다. 하나뿐이면 자동 선택, 여럿이면 번호로 고르게 한다.
2. 사용자가 접속 정보를 이미 말했거나(예: "host 1.2.3.4 포트 2222 계정 ubuntu 키 ~/k.pem"), 저장된 서버가 없으면 **저장 없이 직접 접속**한다. 빠진 정보는 **한 메시지에 하나씩** 묻는다:
   1) 호스트(IP/도메인) 2) 포트(모르면 22 제안) 3) 계정 4) 인증 방식(비밀번호 / PEM 키) 5) 비밀번호 또는 키 파일 경로.
3. 사용자가 일회성이라고 하면 저장하지 않는다. 접속이 성공하고 자주 쓸 것 같으면 저장해도 되는지 묻고 `cred set` (아래).

### Phase 1 — 명령 실행

사용자가 명령을 안 정했으면 목적에 맞는 명령을 agent 가 판단해 실행한다.

| 상황 | 명령 |
|---|---|
| 저장된 서버 | `ssh --cred <서버> --command '…'` (비밀번호 sudo 는 `--sudo` + `SUDO <명령>`) |
| 저장 없이 · 비밀번호 | `ssh --host H --port P --user U --password-env 변수 --command '…'` (`--password '…'` 로 직접 줘도 된다) |
| 저장 없이 · PEM 키 | `ssh --host H --port P --user U --key-path ~/k.pem --command '…'` |
| 저장된 서버의 포트·계정만 바꿔 시도 | `ssh --cred <서버> --port 2022 --command '…'` (직접 준 값이 우선) |
| 새 서버 저장 | 저장해도 되는지 묻고 `cred set --name <서버> --json '{"kind":"ssh","host":…,"port":…,"user":…,"password":…,"use_when":…,"scope":…}'` |
| 옛 `ssh` 섹션 서버 가져오기 | `cred import-ssh --dry-run` 으로 목록 확인 → 빼고 실행(값까지 복사) → 접속 확인 후 `--prune` |
| 로그 · DB | `logs --cred …` · `db --cred …` (`../pro-launch/references/server.md`) |

- 출력에 비밀번호가 섞이면 `***` 로 가려진다. 비밀번호 접속에는 `sshpass` 가 필요하다(없으면 `sshpass_missing`) — 키 접속을 쓰거나 아래 호환 경로를 쓴다.
- 저장된 서버로 접속하면 응답의 `memory` 에 그 서버에서 알아낸 사실(OS · docker 경로 · 컨테이너 · 로그 위치)이 실린다. 새로 알아낸 것은
  `learn --area server --scope machine --key server.<서버>.<주제> --how '…' --result ok` 로 남긴다 (계정·비밀 금지). 저장 없는 접속은 기억하지 않는다.
- 자격증명 규칙 전체: `../pro-launch/references/credentials.md`.

### Phase 2 — 결과 보고

실행 결과를 요약해 보고한다. 에러가 있으면 원인과 해결 방법을 함께 제시한다 (`references/troubleshooting.md`).

## 이 스킬에 남은 것

- `references/troubleshooting.md` — 시놀로지 docker 절대경로·`wget`·Windows PowerShell·자주 만나는 함정 (서버 종류별 지식).
- `scripts/ssh_connect.py` — paramiko 기반 호환 경로. `launch_cli` 를 못 쓰는 환경(sshpass 없는 Windows)에서만. 비밀번호는 환경변수 `SSH_PASSWORD` 로도 받는다.
