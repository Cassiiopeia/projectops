> 언제 읽나: Step 2(DSM 역방향 프록시) 안내를 만들 때. 항목 2개 필드 표, 웹소켓 헤더 9개·고급 설정, 출력 예시(일반/웹소켓).

## Step 2: 시놀로지 DSM 역방향 프록시 설정

**위치**: DSM > 제어판 > 로그인 포털 > 고급 탭 > 역방향 프록시 > "생성"

HTTPS(443)용과 HTTP→HTTPS 리다이렉트(80→443)용, 총 **2개 항목**을 생성한다.

### 항목 1: HTTPS 프록시 (443 → 로컬포트)

**일반 탭:**

| 필드 | 값 |
|------|-----|
| 역방향 프록시 이름 | `{서비스명} 443→{로컬포트}` |
| **소스** | |
| 프로토콜 | `HTTPS` |
| 호스트 이름 | `{서브도메인}.{도메인}` |
| 포트 | `443` |
| HSTS 활성화 | 체크 |
| 액세스 제어 프로파일 | `구성되지 않음` |
| **대상** | |
| 프로토콜 | `HTTP` |
| 호스트 이름 | `localhost` |
| 포트 | `{로컬포트}` |

### 항목 2: HTTP → HTTPS 리다이렉트 (80 → 443)

**일반 탭:**

| 필드 | 값 |
|------|-----|
| 역방향 프록시 이름 | `{서비스명} 80→443` |
| **소스** | |
| 프로토콜 | `HTTP` |
| 호스트 이름 | `{서브도메인}.{도메인}` |
| 포트 | `80` |
| HSTS 활성화 | 체크 안 함 |
| **대상** | |
| 프로토콜 | `HTTPS` |
| 호스트 이름 | `{서브도메인}.{도메인}` |
| 포트 | `443` |

---

### (조건부) 웹소켓 서비스인 경우 추가 설정

서비스가 웹소켓을 사용하는 경우에만 **항목 1(HTTPS 프록시)**에 아래 설정을 추가한다. 웹소켓을 사용하지 않는 일반 서비스는 이 섹션을 건너뛴다.

#### 사용자 지정 머리글 탭

"생성" 버튼을 눌러 아래 9개 헤더를 모두 추가한다:

| 머리글 이름 | 값 |
|-------------|-----|
| `Upgrade` | `$http_upgrade` |
| `Connection` | `$connection_upgrade` |
| `Sec-WebSocket-Key` | `$http_sec_websocket_key` |
| `Sec-WebSocket-Version` | `13` |
| `Sec-WebSocket-Extensions` | `$http_sec_websocket_extensions` |
| `X-Forwarded-Proto` | `https` |
| `X-Forwarded-For` | `$proxy_add_x_forwarded_for` |
| `Authorization` | `$http_authorization` |
| `Proxy-Authorization` | `$http_authorization` |

#### 고급 설정 탭 (선택)

타임아웃 기본값은 60초이다. 서비스에서 60초 이상 걸리는 작업이 있다면 사용자가 지정한 값으로 늘린다.

| 필드 | 값 |
|------|-----|
| 프록시 연결 시간 제한(초) | `{타임아웃}` (기본 60) |
| 프록시 보내기 시간 제한(초) | `{타임아웃}` (기본 60) |
| 프록시 읽기 시간 제한(초) | `{타임아웃}` (기본 60) |
| 프록시 HTTP 버전 | `HTTP 1.1` |
| 대상 서버에서 다시 발송된 오류 페이지를 사용하십시오 | 체크 |

---

### 출력 예시 (일반 서비스)

```
[Step 2] 역방향 프록시 설정 (2개 생성)

[항목 1] {서비스명} 443→{로컬포트}
  일반 탭:
    소스: HTTPS://{서브도메인}.{도메인}:443 (HSTS 활성화)
    대상: HTTP://localhost:{로컬포트}

[항목 2] {서비스명} 80→443
  일반 탭:
    소스: HTTP://{서브도메인}.{도메인}:80
    대상: HTTPS://{서브도메인}.{도메인}:443
```

### 출력 예시 (웹소켓 서비스)

```
[Step 2] 역방향 프록시 설정 (2개 생성)

[항목 1] {서비스명} 443→{로컬포트}
  일반 탭:
    소스: HTTPS://{서브도메인}.{도메인}:443 (HSTS 활성화)
    대상: HTTP://localhost:{로컬포트}
  사용자 지정 머리글 탭 (9개 추가):
    Upgrade: $http_upgrade
    Connection: $connection_upgrade
    Sec-WebSocket-Key: $http_sec_websocket_key
    Sec-WebSocket-Version: 13
    Sec-WebSocket-Extensions: $http_sec_websocket_extensions
    X-Forwarded-Proto: https
    X-Forwarded-For: $proxy_add_x_forwarded_for
    Authorization: $http_authorization
    Proxy-Authorization: $http_authorization
  고급 설정 탭:
    프록시 연결/보내기/읽기 시간 제한: {타임아웃}초
    프록시 HTTP 버전: HTTP 1.1
    오류 페이지 재발송: 체크

[항목 2] {서비스명} 80→443
  일반 탭:
    소스: HTTP://{서브도메인}.{도메인}:80
    대상: HTTPS://{서브도메인}.{도메인}:443
```
