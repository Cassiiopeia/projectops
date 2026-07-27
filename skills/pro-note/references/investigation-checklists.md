# 유형별 조사 체크리스트

막혔을 때 무엇부터 확인할지에 대한 가이드. 과거 기록 검색에서 결과가 없을 때 사용한다.

명령어는 예시다. 실제 기록에는 **그 환경에서 실제로 실행한 명령을 그대로** 적는다 — 경로를 축약하거나 일반화하면 나중에 따라 할 수 없다.

---

## 공통 — 무엇부터 볼 것인가

무슨 유형이든 이 세 가지를 먼저 확인하면 범위가 크게 좁혀진다.

1. **언제부터인가** — 계속 안 됐나, 어제까지 됐나
2. **최근 무엇이 바뀌었나** — 배포, 설정 변경, 의존성 업데이트, 인증서 갱신
3. **어디까지 정상인가** — 전부 실패인가, 특정 조건에서만인가

```bash
# 최근 변경 확인
git log --oneline -20
git log --oneline -10 -- {의심 경로}

# 마지막으로 성공한 시점과 비교
git diff {마지막_성공_커밋}..HEAD -- {의심 경로}
```

---

## 빌드 실패

```bash
# 전체 로그를 남긴다 — 실패 지점만 보면 원인을 놓친다
{빌드 명령} 2>&1 | tee /tmp/build.log

# 런타임 버전 확인 (가장 흔한 원인)
java -version ; node --version ; python --version ; flutter --version

# 의존성 상태
./gradlew dependencies --configuration runtimeClasspath   # Gradle
npm ls --depth=0                                          # Node
pip list                                                  # Python
flutter pub deps                                          # Flutter
```

확인 항목:

- [ ] 런타임 버전이 프로젝트 요구사항과 맞는가
- [ ] 의존성 잠금 파일(`package-lock.json`, `pubspec.lock` 등)이 최신인가
- [ ] 캐시 문제인가 (지우고 다시 받으면 되는가)
- [ ] 로컬은 되는데 CI만 실패하는가 (환경 차이)
- [ ] 네트워크 제한으로 의존성을 못 받는가

---

## 배포 실패

```bash
# CI 실행 로그
gh run list --limit 5          # gh가 있을 때
# 또는 pro-github의 actions 서브커맨드 사용

# 인증서·자격증명 만료 (배포 실패의 흔한 원인)
openssl x509 -in {인증서} -noout -dates
openssl s_client -connect {호스트}:443 2>/dev/null | openssl x509 -noout -dates
```

확인 항목:

- [ ] 인증서·토큰·키가 만료되지 않았는가
- [ ] 저장소 secret·variable이 등록돼 있고 값이 유효한가
- [ ] 배포 대상(서버·스토어·레지스트리) 쪽 상태는 정상인가
- [ ] 빌드 산출물 경로가 워크플로우 설정과 일치하는가
- [ ] 권한이 충분한가 (배포 계정, 토큰 스코프)

---

## 서버·서비스 이상

```bash
# 프로세스와 포트
ps aux | grep -i {서비스명} | grep -v grep
ss -tlnp | grep {포트}

# 자원
df -h
free -h

# 로그 — 시간대를 특정해서 본다
tail -100 {로그경로}
journalctl -u {서비스} --since "1 hour ago"
```

확인 항목:

- [ ] 프로세스가 살아 있는가
- [ ] 포트를 듣고 있는가
- [ ] 디스크·메모리 여유가 있는가
- [ ] 로그에 에러가 있는가 (시작 시점 로그부터 본다)
- [ ] 재시작 후에도 재현되는가

---

## 코드 동작 이상

```bash
# 에러 메시지로 검색
grep -rn "{에러 키워드}" {소스 경로}

# 해당 파일의 최근 변경
git log -p --follow {파일} | head -100

# 언제 깨졌는지 이분 탐색
git bisect start
git bisect bad
git bisect good {정상이던 커밋}
```

확인 항목:

- [ ] 에러 메시지 전문(스택 트레이스 포함)을 확보했는가
- [ ] 재현 조건이 특정되는가
- [ ] 최근 변경과 관련이 있는가
- [ ] 특정 입력·상태에서만 발생하는가

---

## 설정 문제

```bash
# 실제 로드된 값을 확인한다 — 파일 내용과 다를 수 있다
env | grep {접두사}
cat {설정파일}

# 환경별 차이
diff {설정}.dev {설정}.prod
```

확인 항목:

- [ ] 파일에 적힌 값과 실제 적용된 값이 같은가
- [ ] 환경변수가 파일 설정을 덮어쓰고 있지 않은가
- [ ] 인코딩·줄바꿈 문제는 없는가
- [ ] 변경 전 백업했는가

---

## 네트워크·접근

```bash
# 연결 가능한가
curl -v {URL}
nc -zv {호스트} {포트}

# 이름 해석
nslookup {호스트}

# 프록시·미러 설정
npm config get registry
pip config list
```

확인 항목:

- [ ] 대상에 도달 가능한가
- [ ] 인증서 검증에 실패하는가
- [ ] 프록시·미러 설정이 맞는가
- [ ] 방화벽·보안그룹이 막고 있는가

---

## 로컬 환경

다른 사람은 되는데 나만 안 되는 경우.

```bash
# 무엇을 쓰고 있는지
which -a {명령}
echo $PATH

# 버전 관리 도구
sdk current ; nvm current ; pyenv version   # 설치된 것만
```

확인 항목:

- [ ] 여러 버전이 설치돼 충돌하는가
- [ ] PATH 우선순위가 의도와 다른가
- [ ] OS별 차이인가 (경로 구분자, 대소문자, 줄바꿈)
- [ ] 전역 설정이 프로젝트 설정을 덮어쓰는가
