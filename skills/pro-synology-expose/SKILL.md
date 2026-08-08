---
name: pro-synology-expose
description: "시놀로지 NAS에 새 웹 서비스를 외부 도메인으로 노출하는 가이드. DNS 레코드 추가, 시놀로지 DSM 역방향 프록시 설정, Let's Encrypt 인증서 발급 및 연결을 단계별로 안내한다. 사용자가 '서비스 외부 노출', '도메인 연결', '역방향 프록시 추가', '서브도메인 설정', 'HTTPS 설정', '인증서 발급', '시놀로지에 새 서비스 붙이기', '웹소켓 프록시' 등을 언급하면 이 skill을 사용한다."
---

# Synology Expose - 웹 서비스 외부 노출 가이드

시놀로지 NAS에서 Docker 등으로 실행 중인 웹 서비스를 커스텀 도메인으로 외부에 HTTPS로 노출하는 절차를 안내한다.

---

## 설정 파일 확인

`../references/config-rules.md` §2~5 절차를 따른다 (`skill_id = synology-expose`).

> ⚠️ **config는 탐색 금지.** config.json은 고정 경로 `{HOME}/.projectops/config/config.json` 한 곳뿐 — Read tool로 바로 읽는다. `ls`·glob으로 찾거나 플러그인 캐시를 뒤지지 마라.

- 파일이 존재하면 → `instances` 배열 파싱.
  - instances가 1개면 그대로 사용.
  - instances가 여러 개면 번호를 매겨 선택하게 한다:
    ```
    등록된 NAS 인스턴스가 여러 개입니다. 어떤 것을 사용하시겠습니까?
    1. 집 NAS (my-nas.synology.me)
    2. 사무실 NAS (office-nas.synology.me)
    ```
- 파일이 없으면 → 아래 항목을 하나씩 수집 후 저장:
  - NAS 이름 (예: 집 NAS)
  - 시놀로지 DDNS 주소 (예: my-nas.synology.me)
  - 사용하는 도메인 목록
  - Let's Encrypt 이메일
  - DNS 제공자 (cloudflare, route53, gabia 등)

  저장 형식:
  ```json
  {
    "instances": [
      {
        "name": "{NAS 이름}",
        "ddns": "{ddns 주소}",
        "domains": ["{도메인}"],
        "email": "{이메일}",
        "dns_provider": "{cloudflare|route53|gabia}",
        "default": true
      }
    ]
  }
  ```

---

## 서비스 정보 수집

설정 파일이 준비되면 서비스 노출에 필요한 정보를 수집한다. 사용자가 한번에 많은 정보를 줄 수 있으므로 **제공된 정보에서 최대한 자동 추론**하고, 부족한 것만 추가로 물어본다.

### 필요한 정보

| 항목 | 추론 방법 |
|------|-----------|
| **서비스명** | 사용자가 언급한 서비스명이나 docker-compose의 서비스명에서 추론 |
| **서브도메인** | 사용자가 직접 지정하거나, 서비스명에서 추론. 애매하면 물어본다 |
| **로컬포트** | 사용자가 제공한 정보에서 추출. 없으면 물어본다 |
| **웹소켓 사용 여부** | 서비스 특성에서 판단 (채팅, 스트리밍 등은 웹소켓 가능성 높음). 애매하면 물어본다 |
| **타임아웃** | 기본 60초. 사용자가 별도로 언급한 경우에만 변경 |

### 추론 원칙

- 사용자가 제공한 정보(설명, 설정 파일, 포트 번호 등)에서 최대한 추론한다
- 사용자가 한 문장으로 여러 정보를 줄 수 있다 (예: "grafana 3000번 포트 올려줘")
- 확실히 판단 가능한 건 물어보지 않는다. 애매한 것만 물어본다
- 서브도메인이 확실하지 않으면 추천하고 확인을 받는다

---

## Step 1: DNS 레코드 추가

설정 파일의 `dnsProvider`에 따라 안내 방식을 다르게 한다.

### Cloudflare

**위치**: Cloudflare Dashboard > DNS > Records > "Add record"

| 필드 | 값 |
|------|-----|
| Type | `{dnsRecordType}` |
| Name | `{서브도메인}` |
| Target(Content) | `{ddnsAddress}` |
| Proxy status | `{dnsProxyStatus}` |
| TTL | `Auto` |

> 서브도메인에 점(.)이 포함된 경우 (예: `test.api.{도메인}`) Proxied 사용 불가 — DNS only만 가능.

### Route53

**위치**: AWS Console > Route 53 > Hosted zones > {도메인} > "Create record"

| 필드 | 값 |
|------|-----|
| Record name | `{서브도메인}` |
| Record type | `{dnsRecordType}` |
| Value | `{ddnsAddress}` |
| TTL | `300` |
| Routing policy | `Simple routing` |

### 기타 DNS 제공자 (gabia, 직접관리 등)

DNS 관리 페이지에서 아래 레코드를 추가한다:

| 필드 | 값 |
|------|-----|
| 타입 | `{dnsRecordType}` |
| 호스트/이름 | `{서브도메인}` |
| 값/대상 | `{ddnsAddress}` |
| TTL | 기본값 |

### 출력 예시

```
[Step 1] DNS 레코드 추가 ({dnsProvider})
  Type: {dnsRecordType}
  Name: {서브도메인}
  Target: {ddnsAddress}
  (Cloudflare인 경우) Proxy status: {dnsProxyStatus}
```

---

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

---

## Step 3: 인증서 발급 및 서비스 연결

### 3-1. Let's Encrypt 인증서 발급

**위치**: DSM > 제어판 > 보안 > 인증서 탭 > "추가"

| 단계 | 선택/입력 |
|------|-----------|
| 작업 선택 | "새 인증서 추가" → 다음 |
| 인증서 생성 방식 | "Let's Encrypt에서 인증서 얻기" 선택 |
| 기본 인증서로 설정 | 체크 안 함 |
| 설명 | (비워두기 또는 서브도메인 입력) |
| 도메인 이름 | `{서브도메인}.{도메인}` |
| 이메일 | `{email}` |
| 주체 대체 이름(SAN) | (비워두기) |

> DNS 레코드가 전파되기까지 몇 분 걸릴 수 있다. 인증서 발급 실패 시 잠시 기다렸다가 재시도한다.

### 3-2. 인증서를 서비스에 연결

**위치**: DSM > 제어판 > 보안 > 인증서 탭 > "설정" 버튼

설정 팝업의 서비스 목록에서 `{서브도메인}.{도메인}` 항목을 찾아, 인증서 드롭다운을 방금 발급한 `{서브도메인}.{도메인}` 인증서로 변경 → "확인" 클릭.

### 출력 예시

```
[Step 3] 인증서 발급 및 연결

[3-1] 인증서 발급
  제어판 > 보안 > 인증서 > 추가
  방식: Let's Encrypt에서 인증서 얻기
  도메인: {서브도메인}.{도메인}
  이메일: {email}

[3-2] 인증서 서비스 연결
  제어판 > 보안 > 인증서 > 설정
  서비스: {서브도메인}.{도메인} → 인증서: {서브도메인}.{도메인}
```

---

## 최종 확인

모든 설정이 완료되면 브라우저에서 `https://{서브도메인}.{도메인}` 접속하여 정상 동작 확인을 안내한다.

접속 안 되는 경우 체크리스트:
1. DNS 레코드가 정상 등록되었는지 확인 (`nslookup {서브도메인}.{도메인}`)
2. 시놀로지 방화벽에서 80, 443 포트가 열려있는지 확인
3. Docker 컨테이너가 정상 실행 중인지 확인
4. 인증서가 서비스에 올바르게 연결되었는지 확인

---

## 안내 형식

사용자에게 안내할 때는 각 단계를 순서대로 보여주되, **설정 파일의 값과 사용자가 입력한 서비스 정보로 모든 플레이스홀더를 채운 상태**로 제공한다. 사용자가 복사해서 그대로 입력할 수 있도록 구체적인 값을 모두 표시한다.
