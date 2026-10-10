---
name: pro-ssh
description: "원격 서버에 SSH로 접속해 명령을 실행하고 결과를 확인하는 skill. AWS EC2, 시놀로지 NAS, 일반 Linux 서버 등 모든 SSH 접근 가능한 서버에 사용한다. 사용자가 '서버 확인해줘', '로그 봐줘', 'EC2 접속해', '시놀로지 접속해', 'prod 검수해줘', '서버 상태 확인', '배포 됐는지 확인해줘', '서버에서 ~해줘' 등을 언급하면 이 skill을 사용한다."
version: 1.0.0
---

# SSH — 원격 서버 SSH 접근

AWS EC2, 시놀로지 NAS, 일반 Linux 서버 등 SSH 접근 가능한 모든 서버에 접속해 명령을 실행하고 결과를 보고한다.

- 쓰는 때: 서버 상태 확인·로그 조회·파일 확인 등 SSH로 할 수 있는 모든 작업, CI/CD 배포 후 서버 검수, "서버 들어가서 ~해줘".
- **쓰지 않는 때**: 시놀로지 DSM 역방향 프록시·도메인 설정 변경 → `pro-synology-expose`.

## 무엇을 하려는가 → 어디

| 하려는 것 | 할 일 | 자세히 |
|---|---|---|
| 접속 정보 불러오기 / 처음 등록 | config `ssh` 섹션 Read / 대화형 수집 후 Write | 아래 Phase 0, `../references/config-rules.md` §7 |
| 원격 명령 실행 | `{PYTHON} {SCRIPT_PATH} --host … --auth password\|key … --command "…"` | 아래 Phase 1 |
| 시놀로지 · Windows PowerShell · `[ERROR]` 대응 | — | `references/troubleshooting.md` |

## Config

`{HOME}/.projectops/config/config.json` 의 `ssh` 섹션. **이 고정 경로를 Read tool로 바로 읽는다 — `ls`·glob으로 탐색하거나 플러그인 캐시를 뒤지지 마라.**

| 필드 | 필수 | 설명 |
|------|------|------|
| `name` | ✅ | 서버 식별 이름 |
| `host` | ✅ | 호스트명 또는 IP |
| `port` | ✅ | SSH 포트 (기본: 22) |
| `user` | ✅ | SSH 사용자명 |
| `auth` | ✅ | 인증 방식: `"password"` 또는 `"key"` |
| `password` | auth=password 시 ✅ | SSH 비밀번호 |
| `key_path` | auth=key 시 ✅ | PEM 키 파일 절대 경로 (예: `~/.ssh/my-key.pem`) |
| `default` | — | 여러 인스턴스 중 기본 선택 여부 |

**초기 설정** (파일·섹션이 없을 때) — 한 메시지에 한 항목씩 수집한 뒤 `Write` 로 저장(다른 섹션 보존):
1. 호스트명 또는 IP (`host`) → 2. SSH 포트 (`port`, 모르면 22 제안) → 3. 사용자명 (`user`) →
4. 인증 방식(1) 비밀번호 `password` / 2) PEM 키 `key`) → 5. 선택에 따라 비밀번호 또는 키 경로.

## Phase 0 — Config 로드

1. `Read` 로 config 를 읽어 `ssh` 섹션 추출
2. instances가 1개면 자동 선택. 여러 개면 번호 매겨 선택하게 한다.
3. 없으면 위 초기 설정 진행.

## Phase 1 — SSH 명령 실행

`scripts/ssh_connect.py`(paramiko 기반)를 쓴다. sshpass 불필요 — macOS/Linux/Windows 크로스플랫폼.
`python3 -c` 직접 호출 금지(Windows Store stub이 `Exit code 49`로 실패) — 아래에서 찾은 `$PYTHON` 을 쓴다
(`../references/common-rules.md` §"PYTHON 변수 설정"). Windows PowerShell은 `references/troubleshooting.md` 의 블록을 쓴다.

**Python · paramiko · 스크립트 찾기 (1회).** Bash 도구는 호출마다 상태가 초기화되므로, 찾은 **실제 경로를 이후 블록에 값으로 써넣는다.**

```bash
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
if [ -z "$PYTHON" ]; then echo "[ERROR] Python이 설치되지 않았습니다."; exit 1; fi
# paramiko 설치 여부 확인 (없으면 설치)
$PYTHON -c "import paramiko" 2>/dev/null || $PYTHON -m pip install paramiko
SKILL=pro-ssh; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPT_PATH="$ROOT/skills/$SKILL/scripts/ssh_connect.py"
[ -f "$SCRIPT_PATH" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
echo "PYTHON=$PYTHON SCRIPT_PATH=$SCRIPT_PATH"
```

**비밀번호 인증 (auth=password):**

```bash
PYTHONIOENCODING=utf-8 "{PYTHON}" "{SCRIPT_PATH}" --host "{host}" --port {port} --user "{user}" \
  --auth password --password "{password}" --command "{command}"
```

**PEM 키 인증 (auth=key, AWS EC2 등):**

```bash
PYTHONIOENCODING=utf-8 "{PYTHON}" "{SCRIPT_PATH}" --host "{host}" --port {port} --user "{user}" \
  --auth key --key-path "{key_path}" --command "{command}"
```

- 접속 타임아웃은 `--timeout {초}`(기본 15).
- 사용자가 실행할 명령을 명시하지 않았으면 목적에 맞는 명령을 agent가 판단해 실행한다.
- 시놀로지면 docker 절대경로·curl 대신 `wget` 등 차이가 있다 — `references/troubleshooting.md`.

## Phase 2 — 결과 보고

실행 결과를 요약해 보고한다. 에러가 있으면 원인과 해결 방법도 함께 제시한다.

| 출력 | 다음 행동 |
|---|---|
| `[ERROR] 인증 실패` | config `password` / `key_path` 확인 |
| `[ERROR] 소켓 오류` | `port`·방화벽 확인 |
| `[ERROR] paramiko 모듈이 없습니다.` | `$PYTHON -m pip install paramiko` |
| `sudo: a terminal is required` · `command not found` · 키 권한 경고 등 | `references/troubleshooting.md` 함정 표 |
