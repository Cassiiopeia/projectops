# 시놀로지 특이사항 · Windows PowerShell · 자주 만나는 함정

> 언제 읽나: 대상이 시놀로지 NAS일 때, Windows PowerShell에서 실행할 때, `launch_cli ssh` 나 호환용 `ssh_connect.py` 가 실패했을 때.
> 시놀로지 docker 경로는 첫 접속 때 `launch_cli ssh` 가 확인해 `server.<서버>.docker` 기억으로 남긴다.

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

## Windows PowerShell (5.x 포함) — Python 찾기

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

## 자주 만나는 함정

| 증상 | 원인 | 해결 |
|------|------|------|
| `[ERROR] paramiko 모듈이 없습니다.` | paramiko 미설치 | `pip install paramiko` 또는 `pip3 install paramiko` |
| `[ERROR] Python이 설치되지 않았습니다.` | Python 미설치 | python.org에서 설치 (Windows: PATH 추가 필수) |
| `sshpass_missing` (launch_cli) | 비밀번호 접속에 sshpass 없음 | `brew install hudochenkov/sshpass/sshpass`, 키 접속, 또는 `ssh_connect.py` |
| `[ERROR] 인증 실패` | 비밀번호 또는 키 오류 | config의 `password` / `key_path` 값 확인 |
| `[ERROR] 소켓 오류` | 포트 오류 또는 방화벽 | config `port` 확인, 서버 방화벽 규칙 확인 |
| `[ERROR] PEM 키 파일을 찾을 수 없습니다` | key_path 경로 오류 | `~` 포함 절대 경로로 입력 (예: `~/.ssh/my-key.pem`) |
| `command not found` | PATH 미등록 바이너리 | 절대 경로로 실행 (`which`로 먼저 경로 확인) |
| `sudo: a terminal is required` | 비대화형 SSH에서 sudo 불가 | `echo '{password}' \| sudo -S {command}` 패턴 사용 |
| `WARNING: UNPROTECTED PRIVATE KEY FILE` | PEM 키 권한 문제 | `chmod 400 {key_path}` 실행 후 재시도 |
| Windows에서 `?` 기호 오류 (`?.Source`) | PowerShell 5.x Null 조건 연산자 미지원 | `if ($x) { $x.Source }` 패턴으로 대체 |
