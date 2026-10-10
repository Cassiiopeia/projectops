# GitHub Actions Secret 관리

> 언제 읽나: "BACKEND_ENV_FILE secret 업데이트해줘", "secret 바꿔줘", "환경변수 secret 올려줘", "Actions secret 등록해줘" 같은 요청일 때.

명령은 `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py secrets <list|set> ...` 형태다 (SKILL.md "스크립트 찾기").

## 자동 탐색 절차

사용자가 secret 이름이나 값을 명시하지 않아도 스킬이 먼저 탐색한다.

**1단계 — secret 이름 결정**

- `$ARGUMENTS`에 이름이 명시된 경우 → 그대로 사용
- 미명시 시 → 현재 레포의 secrets 목록 조회 후 번호로 선택지 제시

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py secrets list {owner} {repo}
```

**2단계 — secret 값 결정**

- `$ARGUMENTS`에 값이 명시된 경우 → 그대로 사용
- 미명시 시 → 프로젝트 루트와 서브디렉터리에서 `.env` 파일 자동 탐색:

  ```bash
  find "{PROJECT_ROOT}" -maxdepth 3 -name ".env" -not -path "*/node_modules/*" -not -path "*/.git/*" 2>/dev/null
  ```

  - `.env` 파일 발견 시 → 내용을 보여주고 "이 내용으로 업데이트할까요?" 확인
  - `.env` 없음 → 직접 입력 요청

> **주의**: `.env` 내용에 민감 정보가 포함될 수 있으므로, 사용자에게 내용을 보여주고 반드시 확인 후 진행한다.

## Secret 업데이트 실행

값은 `SECRET_VALUE` 환경변수로 전달한다. 멀티라인 `.env`도 인자 이스케이프 없이 보존된다. `secrets set`이 PyNaCl로 GitHub public key 암호화 후 PUT한다. PyNaCl 미설치 시 자동 설치를 시도하고, 실패하면 `code:"pynacl_missing"` JSON을 반환한다.

```bash
SECRET_VALUE="{secret_value}" PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py secrets set {owner} {repo} {secret_name}
```

## 오류 대응

| 오류 | 원인 | 대응 |
|------|------|------|
| `403` on secrets API | PAT에 `repo` scope 없음 | PAT 재발급 시 `repo` 전체 체크 안내 |
| `404` on secrets list | private 레포 권한 없음 | 권한 확인 안내 |
| `pynacl_missing` / `nacl` import 오류 | PyNaCl 설치 실패 | `pip install PyNaCl --user` 수동 실행 안내 |
| `.env` 내용에 특수문자 | 인자 이스케이프 문제 | `SECRET_VALUE` 환경변수로 전달 |
