> 언제 읽나: Step 1(DNS 레코드 추가) 안내를 만들 때. DNS 제공자별 입력 위치·필드 표와 출력 예시.

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
