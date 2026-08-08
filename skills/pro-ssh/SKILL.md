---
name: pro-ssh
description: "원격 서버에 SSH로 접속해 명령을 실행하고 결과를 확인하는 skill. AWS EC2, 시놀로지 NAS, 일반 Linux 서버 등 모든 SSH 접근 가능한 서버에 사용한다. 사용자가 '서버 확인해줘', '로그 봐줘', 'EC2 접속해', '시놀로지 접속해', 'prod 검수해줘', '서버 상태 확인', '배포 됐는지 확인해줘', '서버에서 ~해줘' 등을 언급하면 이 skill을 사용한다."
version: 1.0.0
---

# SSH — 원격 서버 SSH 접근

AWS EC2, 시놀로지 NAS, 일반 Linux 서버 등 SSH 접근 가능한 모든 서버에 접속해 명령을 실행하고 결과를 보고한다.

---

## 언제 사용하는가

- 서버 상태 확인, 로그 조회, 파일 확인 등 SSH로 할 수 있는 모든 작업
- CI/CD 배포 후 서버 검수
- "서버 들어가서 ~해줘" 류의 요청

**이때는 쓰지 않는다**: 시놀로지 DSM 역방향 프록시·도메인 설정 변경 → `pro-synology-expose` 사용.

---

## 사용 전 준비

**Python 실행 환경**: `../references/common-rules.md` §"PYTHON 변수 설정 (크로스 플랫폼 필수)" 패턴을 사용한다. `python3 -c` 직접 호출 금지 — Windows에서 Store stub이 잡혀 `Exit code 49`로 실패한다. 본 skill의 Phase 1·Phase 2 코드블럭에서 검출된 `$PYTHON` 변수를 재사용한다.

Config 파일: `{HOME}/.projectops/config/config.json` — `ssh` 섹션 사용. **이 고정 경로를 Read tool로 바로 읽는다 — `ls`·glob으로 탐색하거나 플러그인 캐시를 뒤지지 마라.**
스키마 상세: `../references/config-rules.md` §7 `ssh` 섹션 참조.

파일이 없으면 아래 "Config 초기 설정" 절차로 대화형 수집 후 생성한다.

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

---

## Config 초기 설정

파일이 없으면 아래 순서로 하나씩 수집한다 (한 메시지 = 한 항목):

1. 호스트명 또는 IP (`host`)
2. SSH 포트 (`port`, 모르면 22 제안)
3. 사용자명 (`user`)
4. 인증 방식 선택:
   - 1) 비밀번호 (`password`)
   - 2) PEM 키 (`key`)
5. 선택에 따라 비밀번호 또는 키 경로 수집

수집 완료 후 `Write` 도구로 저장.

---

## 작업 흐름

### Phase 0 — Config 로드

1. `Read` 도구로 `{HOME}/.projectops/config/config.json` 읽기 → `ssh` 섹션 추출
2. instances가 1개면 자동 선택. 여러 개면 번호 매겨 선택하게 한다.
3. 파일 없으면 "Config 초기 설정" 진행.

### Phase 1 — SSH 명령 실행

`scripts/ssh_connect.py` (paramiko 기반)를 사용한다. sshpass 불필요 — macOS/Linux/Windows 크로스플랫폼 지원.

**Python 실행 경로 확인 (최초 1회):**

```bash
# python3 → python 순으로 fallback
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
if [ -z "$PYTHON" ]; then echo "[ERROR] Python이 설치되지 않았습니다."; exit 1; fi

# paramiko 설치 여부 확인 (없으면 설치)
$PYTHON -c "import paramiko" 2>/dev/null || $PYTHON -m pip install paramiko
```

**Windows PowerShell (5.x 포함):**

```powershell
# python3 → python 순서로 fallback (PowerShell 5.x: ?.Source 미지원이므로 if 분기 사용)
$py3 = Get-Command python3 -ErrorAction SilentlyContinue
if ($py3) { $PYTHON = $py3.Source }
else {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) { $PYTHON = $py.Source }
    else { Write-Error "[ERROR] Python이 설치되지 않았습니다."; exit 1 }
}

# paramiko 설치 확인
& $PYTHON -c "import paramiko" 2>$null
if ($LASTEXITCODE -ne 0) { & $PYTHON -m pip install paramiko }
```

**스크립트 경로 확인:**

```bash
# 플러그인 설치 경로에서 스크립트 찾기 ($PYTHON은 위 "Python 실행 경로 확인" 단계에서 검출됨)
PLUGIN_ROOT=$(cat ~/.claude/plugins/installed.json 2>/dev/null \
  | "$PYTHON" -c "import sys,json; d=json.load(sys.stdin); print(d.get('projectops',{}).get('path',''))" 2>/dev/null)
SCRIPT_PATH="${PLUGIN_ROOT}/skills/pro-ssh/scripts/ssh_connect.py"

# 없으면 로컬 경로 시도
[ ! -f "$SCRIPT_PATH" ] && SCRIPT_PATH="$(git rev-parse --show-toplevel)/skills/pro-ssh/scripts/ssh_connect.py"
```

**비밀번호 인증 (auth=password):**

```bash
$PYTHON "$SCRIPT_PATH" \
  --host "{host}" \
  --port {port} \
  --user "{user}" \
  --auth password \
  --password "{password}" \
  --command "{command}"
```

**PEM 키 인증 (auth=key, AWS EC2 등):**

```bash
$PYTHON "$SCRIPT_PATH" \
  --host "{host}" \
  --port {port} \
  --user "{user}" \
  --auth key \
  --key-path "{key_path}" \
  --command "{command}"
```

사용자가 실행할 명령을 명시하지 않았으면 목적에 맞는 명령을 agent가 판단해 실행한다.

### Phase 2 — 결과 보고

실행 결과를 사용자에게 요약해 보고한다. 에러가 있으면 원인과 해결 방법도 함께 제시한다.

---

## 시놀로지 NAS 특이사항

시놀로지 NAS는 일반 Linux 서버와 환경이 다르다.

| 항목 | 일반 서버 | 시놀로지 NAS |
|------|-----------|--------------|
| Docker 경로 | `docker` | `/var/packages/ContainerManager/target/usr/bin/docker` |
| 컨테이너 내 curl | 대부분 있음 | 없는 경우 많음 → `wget`으로 대체 |
| sudo | 일반적으로 가능 | SSH 비대화형에서 제한됨 |
| SSH 기본 포트 | 22 | 커스텀 포트 사용 가능 (예: 2022) |

**시놀로지에서 HTTP 확인 (curl 대신 wget):**
```bash
wget -q -O - --server-response http://localhost:{port}/{path} 2>&1 | head -5
```

---

## 자주 만나는 함정

| 증상 | 원인 | 해결 |
|------|------|------|
| `[ERROR] paramiko 모듈이 없습니다.` | paramiko 미설치 | `pip install paramiko` 또는 `pip3 install paramiko` |
| `[ERROR] Python이 설치되지 않았습니다.` | Python 미설치 | python.org에서 설치 (Windows: PATH 추가 필수) |
| `[ERROR] 인증 실패` | 비밀번호 또는 키 오류 | config의 `password` / `key_path` 값 확인 |
| `[ERROR] 소켓 오류` | 포트 오류 또는 방화벽 | config `port` 확인, 서버 방화벽 규칙 확인 |
| `[ERROR] PEM 키 파일을 찾을 수 없습니다` | key_path 경로 오류 | `~` 포함 절대 경로로 입력 (예: `~/.ssh/my-key.pem`) |
| `command not found` | PATH 미등록 바이너리 | 절대 경로로 실행 (`which`로 먼저 경로 확인) |
| `sudo: a terminal is required` | 비대화형 SSH에서 sudo 불가 | `echo '{password}' \| sudo -S {command}` 패턴 사용 |
| `WARNING: UNPROTECTED PRIVATE KEY FILE` | PEM 키 권한 문제 | `chmod 400 {key_path}` 실행 후 재시도 |
| Windows에서 `?` 기호 오류 (`?.Source`) | PowerShell 5.x Null 조건 연산자 미지원 | `if ($x) { $x.Source }` 패턴으로 대체 |
