# MCP-style 서브커맨드 설계 표준

각 skill의 `<scope>_cli.py`에 외부 시스템(GitHub API, SSH 등)을 다루는 새 서브커맨드를 추가할 때 **반드시 이 표준을 따른다.**
CLAUDE.md "Python 행동 스크립트 표준"의 구체적 구현 레퍼런스다.

> **모범 사례**: `actions`, `deploy-status` 서브커맨드 (`skills/pro-changelog-deploy/scripts/changelog_cli.py`). 새 커맨드를 만들기 전에 이 둘을 먼저 읽고 같은 모양으로 만든다.

## 핵심 원칙

agent는 **인자만 정확히 넘기고, 반환 JSON을 보고 다음 행동을 판단**한다. 그래서 서브커맨드는
① **입력 계약이 명확**하고 ② **출력이 언제나 JSON**이며 ③ **다음 행동 힌트(`next`)**를 담는다.
그러면 agent가 `/tmp`에 즉석 Python을 만들 이유가 사라진다 — 즉석 Python은 토큰 낭비 + Windows 호환성 깨짐 + heredoc 이스케이프 버그다.

---

## 1. 입력 계약 — 해석은 agent, 실행은 .py

- 서브커맨드는 **명확한 인자만** 받는다. URL 파싱·PR→run 추적 같은 **해석을 하지 않는다.** agent가 사용자 입력(URL/PR번호/브랜치/빈입력)을 해석해 정확한 서브커맨드·인자를 넘긴다.
- 그룹이 커지면 `actions show-run` / `secrets set`처럼 **그룹 + 하위 서브커맨드**로 묶는다 (최상위에 평면 나열 금지).
- 인자 정의는 argparse(`JSONArgumentParser`, §8)로 한다. **선택 위치 인자를 여러 개 줄줄이 두지 않는다** (#622) — argparse는 왼쪽부터 채우므로 서브커맨드마다 다른 값(`run_id`/`job_id`/`pr_number`/`branch`)을 각각의 칸으로 두면 첫 칸에만 들어간다. 위치 인자는 **하나**(`arg`)로 두고 서브커맨드가 해석한다 (`changelog_cli.py`의 `actions`).

---

## 2. 출력은 언제나 JSON — `emit`으로

- 모든 경로에서 `common.emit.emit(payload)`로 stdout에 JSON을 낸다 (plain text 모드 없음, `--json` 옵션도 두지 않는다). `emit`은 `ok`/`code`/`summary`/`next` 기본값을 채운다.
- 성공/실패 모두 JSON. **stderr로 에러 던지고 exit 1 하지 않는다** (agent가 파싱 못 함).

### 표준 반환 스키마

| 필드 | 필수 | 의미 |
|------|------|------|
| `ok` | ✅ | 성공 여부 (true/false) |
| `error` | 실패 시 | 사람·agent가 읽을 에러 메시지 |
| `code` | ✅ (emit이 채움) | 분류 코드 (`ok`, `missing_pat`, `github_api_404` 등) |
| (데이터 필드) | ✅ | 실제 결과 (`issues`, `repos`, `pr` 등 — 커맨드별) |
| `verdict` | 상태 판정 커맨드 | 상황을 한 단어로 (`merged`, `waiting`, `no_pr` 등) |
| `summary` | 권장 | 한 줄 자연어 요약 |
| `next` | ✅ | agent가 이어서 호출할 다음 서브커맨드 힌트 (없으면 `null`) |

### 데이터는 헬퍼(gh_client), 판정은 커맨드 레이어

`gh_client.py` 함수는 **순수 API 조회**만 한다 (raw dict 반환, 판정 없음). `<scope>_cli.py`의 `cmd_*`가
**verdict 판정 + JSON 조립 + next 힌트**를 맡는다. 그래서 헬퍼는 단독 테스트되고 판정 로직만 따로 검증된다.

```python
# gh_client.py — 조회만
def get_thing(owner, repo, id, pat) -> dict:
    data = _request("GET", f"{_API_BASE}/...", None, pat)
    return {"id": data["id"], "state": data["state"], ...}  # raw 추출

# <scope>_cli.py — 판정 + 조립
def cmd_thing(args):
    ...
    thing = get_thing(args.owner, args.repo, args.id, pat)
    verdict = "ready" if thing["state"] == "open" else "closed"
    return emit({"ok": True, "thing": thing, "verdict": verdict,
                 "summary": "...", "next": f"thing-detail {args.owner} {args.repo} {args.id}"})
```

---

## 3. PAT는 `get_github_pat` 재사용

```python
from common.config import get_github_pat

pat = get_github_pat(args.owner, args.repo)
if not pat:
    return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
```

`GITHUB_PAT` 환경변수 → `config.json`(repo별 `pat` → `global_pat`) 순으로 자동 로드한다. 서브커맨드 안에서 config 파일을 직접 열지 않는다.

---

## 4. 에러는 GitHubAPIError를 잡아 JSON으로

```python
try:
    ...
except GitHubAPIError as e:
    return emit({"ok": False, "error": str(e), "code": f"github_api_{e.status_code}"})
```

치명적이지 않은 부분 실패(예: 워크플로우 run 조회 실패)는 **해당 필드를 `null`로 두고 계속 진행**한다. `deploy-status`의 `workflow=null` 처리 참고.

---

## 5. 표준 라이브러리 우선, 안 되면 외부 패키지 + 내부망 대응

- 가능하면 `urllib`/`json`만으로 해결 (mac·Windows·내부망에서 `pip install` 없이 동작).
- 표준 라이브러리로 안 되는 일(예: secret 암호화 PyNaCl)은 외부 패키지를 쓰되, **`import` 실패 시 `pip install` 시도 + 실패하면 수동 설치 안내**를 둔다.
- redirect되는 엔드포인트(job logs 등)는 `gh_client.py`의 `_StripAuthRedirect` 핸들러를 거친다 (Azure 403 방지).

---

## 6. 등록 + 테스트

1. `build_parser()`에 `sub.add_parser(...)` + `set_defaults(func=cmd_xxx)`로 등록한다 (일부 구 CLI는 `_COMMANDS` dict — 그 파일의 기존 방식을 따른다).
2. `scripts/tests/`에 verdict/판정 로직 단위 테스트를 추가한다 (gh_client 함수를 mock, in-process 호출).
3. `gh_client.py` 신규 헬퍼는 urllib mock 단위 테스트를 추가한다.

```python
def _call_cmd(mock_data, argv, capsys):
    import <scope>_cli
    with patch.object(<scope>_cli, "get_github_pat", return_value="ghp_fake"), \
         patch.object(<scope>_cli, "get_thing", return_value=mock_data):
        <scope>_cli.run_cli(<scope>_cli.build_parser(), argv)
    return _json.loads(capsys.readouterr().out.strip())
```
---

## 7. SKILL.md 작성 규칙

- SKILL.md는 **호출법만** 기술한다 (서브커맨드·인자·환경변수 + "이런 입력 → 이런 서브커맨드" 라우팅 규칙). 호출은 `common-rules.md` §표준 호출 패턴으로 찾은 `{PYTHON} {SCRIPTS}/<scope>_cli.py` 형태다.
- 긴 Python heredoc을 SKILL.md에 인라인하지 않는다. `$PYTHON - <<'EOF'` 블록이 SKILL.md에 보이면 표준 위반이다 — 서브커맨드로 뺀다.
- `verdict`별 agent 행동을 표로 명시한다 (`deploy-status`의 verdict 표 참고).
- **CLI에 정의된 모든 서브커맨드는 해당 skill SKILL.md(또는 명시적으로 참조하는 문서)에 호출 예시가 있어야 한다.** 예시 없는 서브커맨드는 agent가 시그니처를 추측하다 실패한다 (#329). 예시를 둘 수 없으면 CLI 표면에서 제거하거나 내부 함수로 옮긴다.
- 호출 예시에는 ①정확한 인자 순서의 `bash` 실행 라인, ②기대 JSON 출력 한 줄, ③결과를 어떻게 쓰는지 한 줄을 넣는다.
- `scripts/tests/test_cli_signatures_doc_sync.py`가 이 매칭을 강제한다.

---

## 8. argparse 실패도 JSON으로 — `JSONArgumentParser` 필수

argparse 기본 동작은 인자 오류 시 stderr text + `SystemExit(2)`다. agent는 stdout JSON만 파싱하므로 이걸로 self-correct하지 못한다.
모든 `_cli.py`는 `scripts/common/cli_parser.py`의 `JSONArgumentParser` + `run_cli`를 쓴다.

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

`run_cli`는 argparse 에러를 아래 JSON으로 바꿔 stdout에 낸다.

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

agent는 `code == "bad_args"`를 보면 `available_subcommands`로 정확한 서브커맨드를 골라 재호출한다.
`--help`/`-h`는 argparse 기본 동작 그대로 둔다 (사람이 직접 실행할 때 도움말).

---

## 체크리스트 (새 서브커맨드 추가 시)

- [ ] 입력 계약이 명확한가? (위치 인자는 하나)
- [ ] 모든 경로가 `emit`으로 JSON을 내는가? (stderr+exit 1 없음)
- [ ] `ok`/`next`/`summary` 필드를 담는가?
- [ ] 데이터 조회는 common.gh_client, 판정은 `<scope>_cli`로 분리했는가?
- [ ] `get_github_pat` 재사용 + `GitHubAPIError` JSON 변환했는가?
- [ ] `build_parser()`에 등록 + 테스트 추가했는가?
- [ ] SKILL.md에 인라인 Python 대신 호출법만 적었는가?
