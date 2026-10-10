---
name: pro-ssh
description: "원격 서버에 SSH로 접속해 명령을 실행하고 결과를 확인하는 skill. AWS EC2, 시놀로지 NAS, 일반 Linux 서버 등 모든 SSH 접근 가능한 서버에 사용한다. 사용자가 '서버 확인해줘', '로그 봐줘', 'EC2 접속해', '시놀로지 접속해', 'prod 검수해줘', '서버 상태 확인', '배포 됐는지 확인해줘', '서버에서 ~해줘' 등을 언급하면 이 skill을 사용한다."
version: 2.0.0
---

# SSH — 원격 서버 SSH 접근 (라우터)

접속·자격증명·서버 기억은 **`pro-launch` 가 정본**이다 (#841). 이 스킬은 어디로 가야 하는지만 안내한다.

- 쓰는 때: 서버 상태·로그·파일 확인, 배포 후 서버 검수, "서버 들어가서 ~해줘".
- **쓰지 않는 때**: 시놀로지 DSM 역방향 프록시·도메인 설정 → `pro-synology-expose`.

## 하는 법

`{SCRIPTS}` 는 pro-launch 의 `scripts/` (찾는 법은 `../pro-launch/SKILL.md`). 호출은 `{PYTHON} {SCRIPTS}/launch_cli.py …`.

| 하려는 것 | 명령 |
|---|---|
| 저장된 서버 보기 | `cred list` (`use_when` 이 지금 일에 맞는 것만 쓴다) |
| 명령 실행 | `ssh --cred <서버> --command '…'` (비밀번호 sudo 는 `--sudo` + `SUDO <명령>`) |
| 새 서버 저장 | 사용자에게 저장해도 되는지 묻고 `cred set --name <서버> --json '{"kind":"ssh","host":…,"user":…,"use_when":…}'` |
| 옛 `ssh` 섹션 서버 가져오기 | `cred import-ssh --dry-run` 으로 목록 확인 → 빼고 실행(값까지 복사) → 접속 확인 후 `--prune` |
| 로그 · DB | `logs --cred …` · `db --cred …` (`../pro-launch/references/server.md`) |

- 응답의 `memory` 에 그 서버에서 알아낸 사실(OS · docker 경로 · 컨테이너 · 로그 위치)이 실린다. 새로 알아낸 것은
  `learn --area server --scope machine --key server.<서버>.<주제> --how '…' --result ok` 로 남긴다 (계정·비밀 금지).
- 비밀번호 접속에는 `sshpass` 가 필요하다. 없으면 키 접속(`key_path`)을 쓰거나 아래 호환 경로를 쓴다.
- 자격증명 규칙 전체: `../pro-launch/references/credentials.md`.

## 이 스킬에 남은 것

- `references/troubleshooting.md` — 시놀로지 docker 절대경로·`wget`·Windows PowerShell·자주 만나는 함정 (서버 종류별 지식).
- `scripts/ssh_connect.py` — 호환용(paramiko). `launch_cli` 를 못 쓰는 환경(sshpass 없는 Windows)에서만. 비밀번호는
  `--password` 대신 환경변수 `SSH_PASSWORD` 로 넘긴다.
