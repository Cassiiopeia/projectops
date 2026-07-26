# MCP-style 서브커맨드 설계 표준

각 skill의 `<scope>_cli.py`에 외부 시스템(GitHub API, SSH 등)을 다루는 새 서브커맨드를 추가할 때 **반드시 이 표준을 따른다.** CLAUDE.md "Python 행동 스크립트 표준"의 구체적 구현 레퍼런스다.

> **모범 사례**: `actions`, `deploy-status` 서브커맨드 (`skills/pro-changelog-deploy/scripts/changelog_cli.py`). 새 커맨드를 만들기 전에 이 둘을 먼저 읽고 같은 모양으로 만든다.

---

## 핵심 원칙 (왜 이렇게 하는가)

agent는 **인자만 정확히 넘기고, 반환 JSON을 보고 다음 행동을 판단**한다. 따라서 서브커맨드는:

1. **입력 계약이 명확**해야 한다 (agent가 무엇을 넘길지 헷갈리지 않게)
2. **출력이 언제나 JSON**이어야 한다 (agent가 단일 형식만 파싱)
3. **다음 행동 힌트(`next`)를 담아야** 한다 (agent가 체이닝 판단)

이렇게 하면 agent가 `/tmp`에 즉석 Python을 만들 이유가 사라진다. 즉석 Python은 곧 토큰 낭비 + Windows 호환성 깨짐 + heredoc 이스케이프 버그다.

---

## 1. 입력 계약 — 해석은 agent, 실행은 .py

- 서브커맨드는 **명확한 인자만** 받는다. URL 파싱·PR→run 추적 같은 **해석을 하지 않는다.**
- agent가 사용자 입력(URL/PR번호/브랜치/빈입력)을 해석해 정확한 서브커맨드·인자를 넘긴다.
- 그룹이 커지면 `actions show-run` / `secrets set`처럼 **그룹 + 하위 서브커맨드**로 묶는다 (최상위에 평면 나열 금지).
- 옵션은 `--limit N`, `--pr N`처럼 `rest` 배열에서 직접 파싱한다 (argparse 불필요 — 기존 패턴 유지).

```python
def cmd_groupname(args: list) -> int:
    """groupname <sub> <owner> <repo> [인자]

    출력은 언제나 JSON. 입력 해석(URL→ID)은 호출자(agent) 책임.
    """
    if len(args) < 3:
        return _emit({
            "ok": False,
            "error": "사용법: groupname <sub> <owner> <repo> [인자]",
            "subcommands": ["list-x OWNER REPO", "get-y OWNER REPO ID"],
        })
    sub, owner, repo = args[0], args[1], args[2]
    rest = args[3:]
    ...
```

---

## 2. 출력은 언제나 JSON — `_emit`으로

- 모든 경로에서 `_emit(payload)`로 stdout에 JSON 출력 (plain text 모드 없음, `--json` 옵션도 두지 않는다).
- 성공/실패 모두 JSON. **stderr로 에러 던지고 exit 1 하지 않는다** (agent가 파싱 못 함).

### 표준 반환 스키마

| 필드 | 필수 | 의미 |
|------|------|------|
| `ok` | ✅ | 성공 여부 (true/false) |
| `error` | 실패 시 | 사람·agent가 읽을 에러 메시지 |
| `code` | 선택 | 에러 분류 코드 (`missing_pat`, `github_api_404` 등) |
| (데이터 필드) | ✅ | 실제 결과 (`issues`, `repos`, `pr` 등 — 커맨드별) |
| `verdict` | 상태 판정 커맨드 | 상황을 한 단어로 (`merged`, `waiting`, `no_pr` 등) |
| `summary` | 권장 | 한 줄 자연어 요약 (agent·사람이 바로 이해) |
| `next` | ✅ | agent가 이어서 호출할 다음 서브커맨드 힌트 (없으면 `null`) |

### 데이터는 헬퍼(gh_client), 판정은 커맨드 레이어

- `gh_client.py` 함수는 **순수 API 조회**만 한다 (raw 데이터 dict 반환, 판정 없음).
- `<scope>_cli.py`의 `cmd_*`가 **verdict 판정 + JSON 조립 + next 힌트**를 담당한다.
- 이 분리 덕분에 헬퍼는 단독 테스트 가능하고, 판정 로직만 따로 검증할 수 있다.

```python
# gh_client.py — 조회만
def get_thing(owner, repo, id, pat) -> dict:
    data = _request("GET", f"{_API_BASE}/...", None, pat)
    return {"id": data["id"], "state": data["state"], ...}  # raw 추출

# <scope>_cli.py — 판정 + 조립
def cmd_thing(args):
    ...
    thing = _github.get_thing(owner, repo, id, pat)
    verdict = "ready" if thing["state"] == "open" else "closed"
    return _emit({"ok": True, "thing": thing, "verdict": verdict,
                  "summary": f"...", "next": f"thing-detail {owner} {repo} {id}"})
```

---

## 3. PAT는 `_get_pat` 재사용

```python
pat = _get_pat(owner, repo)
if not pat:
    return _emit({"ok": False, "error": "GITHUB_PAT 환경변수도 config.json도 없음", "code": "missing_pat"})
```

- `_get_pat`은 `GITHUB_PAT` 환경변수 → `config.json`(repo별 `pat` → `global_pat`) 순으로 자동 로드한다.
- 서브커맨드 안에서 config 파일을 직접 열지 않는다.

---

## 4. 에러는 GitHubAPIError를 잡아 JSON으로

```python
try:
    ...
except _github.GitHubAPIError as e:
    return _emit({"ok": False, "error": str(e), "code": f"github_api_{e.status_code}"})
```

- 치명적이지 않은 부분 실패(예: 워크플로우 run 조회 실패)는 **해당 필드를 `null`로 두고 계속 진행**한다 (전체를 실패시키지 않음). `deploy-status`의 `workflow=null` 처리 참고.

---

## 5. 표준 라이브러리 우선, 안 되면 외부 패키지 + 내부망 대응

- 가능하면 `urllib`/`json`만으로 해결 (mac·Windows·내부망에서 `pip install` 없이 동작).
- 표준 라이브러리로 안 되는 일(예: secret 암호화 PyNaCl)은 외부 패키지를 쓰되, **스크립트 안에서 `import` 실패 시 `pip install` 시도 + 실패하면 수동 설치 안내**를 둔다.
- redirect되는 엔드포인트(job logs 등)는 `_StripAuthRedirect` 핸들러 필수 (Azure 403 방지).

---

## 6. 등록 + 테스트

1. `_COMMANDS` dict에 `"groupname": cmd_groupname,` 추가.
2. `scripts/tests/test_cli_github.py`에 verdict/판정 로직 단위 테스트 추가 (gh_client를 mock, in-process 호출).
3. `gh_client.py` 신규 헬퍼는 `scripts/tests/test_gh_client.py`에 urllib mock 단위 테스트 추가.

테스트 패턴:

```python
def _call_cmd(mock_data, args_rest, capsys):
    import <scope>_cli
    with patch.object(<scope>_cli, "_get_pat", return_value="ghp_fake"), \
         patch.object(<scope>_cli, "get_thing", return_value=mock_data):
        <scope>_cli.cmd_thing(["owner", "repo", *args_rest])
    return _json.loads(capsys.readouterr().out.strip())

def test_thing_ready(capsys):
    result = _call_cmd({"id": 1, "state": "open"}, ["1"], capsys)
    assert result["verdict"] == "ready"
```

---

## 7. SKILL.md 작성 규칙

- SKILL.md는 **호출법만** 기술한다 (서브커맨드·인자·환경변수 + "이런 입력 → 이런 서브커맨드" 라우팅 규칙).
- 긴 Python heredoc을 SKILL.md에 인라인하지 않는다. `$PYTHON - <<'EOF'` 블록이 SKILL.md에 보이면 그건 이 표준 위반이다 — 서브커맨드로 빼야 한다.
- `verdict`별 agent 행동을 표로 명시해 agent가 반환값→행동을 정확히 라우팅하게 한다 (`deploy-status`의 verdict 표 참고).
- **CLI에 정의된 모든 서브커맨드는 해당 skill SKILL.md(또는 명시적으로 참조하는 다른 SKILL.md)에 호출 예시가 있어야 한다.** 호출 예시 없는 서브커맨드는 agent가 시그니처를 추측해 호출하다 실패한다 (이슈 #329). 호출예를 추가할 수 없다면 CLI 표면에서 제거하거나 내부 함수로 옮긴다.
- 호출 예시에는 다음 3가지를 반드시 포함한다: ①정확한 인자 순서를 포함한 `bash` 실행 라인, ②기대 JSON 출력 한 줄, ③agent가 결과를 어떻게 사용해야 하는지 한 줄 설명.
- `scripts/tests/test_cli_signatures_doc_sync.py`가 이 매칭을 강제한다. 신규 서브커맨드 추가 시 테스트가 통과하도록 SKILL.md를 함께 갱신해야 한다.

```bash
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
cd "$PROJECT_ROOT/scripts"
PYTHONIOENCODING=utf-8 "$PYTHON" <scope>_cli.py groupname sub OWNER REPO ARG
```

---

## 8. argparse 실패도 JSON으로 — `JSONArgumentParser` 필수

argparse 기본 동작은 인자 오류 시 stderr text + `SystemExit(2)`로 종료한다. agent는 stdout JSON만 파싱하므로 이 출력을 self-correct에 활용하지 못한다.

모든 `_cli.py`는 `scripts/common/cli_parser.py`의 `JSONArgumentParser` + `run_cli`를 사용한다:

```python
from common.cli_parser import JSONArgumentParser, run_cli

def build_parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(prog="scope_cli", description="...")
    sub = parser.add_subparsers(dest="command", required=True)
    # ... add_parser들 ...
    return parser

def main() -> int:
    return run_cli(build_parser())
```

`run_cli`는 argparse 에러를 다음 형태의 JSON으로 변환해 stdout에 출력한다:

```json
{
  "ok": false,
  "code": "bad_args",
  "error": "unrecognized arguments: extra1 extra2",
  "hint": "scope_cli <subcommand> — available: ...",
  "available_subcommands": ["...", "..."],
  "summary": null,
  "next": null
}
```

agent는 `code == "bad_args"`를 보면 `available_subcommands`로 정확한 서브커맨드를 선택해 재호출한다.

`--help`/`-h`는 argparse 기본 동작 그대로 유지해 사람이 직접 실행할 때 도움말이 보이게 한다.

---

## 체크리스트 (새 서브커맨드 추가 시)

- [ ] 입력 계약이 명확한가? (agent가 뭘 넘길지 헷갈리지 않게)
- [ ] 모든 경로가 `_emit`으로 JSON을 내는가? (stderr+exit 1 없음)
- [ ] `ok`/`next`/`summary` 필드를 담는가?
- [ ] 데이터 조회는 common.gh_client, 판정은 `<scope>_cli`로 분리했는가?
- [ ] `_get_pat` 재사용 + `GitHubAPIError` JSON 변환했는가?
- [ ] `_COMMANDS`에 등록 + 테스트 추가했는가?
- [ ] SKILL.md에 인라인 Python 대신 호출법만 적었는가?
