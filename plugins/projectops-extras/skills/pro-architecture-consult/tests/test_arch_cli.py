"""arch_cli 계약 테스트 8개: 오류 JSON · audit 사실 · 실측 오탐·놓침 회귀 · check(diff) · ledger · init 설치 · 템플릿 판정 동등성
임시 미니 모노레포(Flutter·Spring·Python·JS) 하나로 서브커맨드 전부를 본다
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1]
CLI = SKILL / "scripts" / "arch_cli.py"
TEMPLATES = SKILL / "templates" / "rule-tests"


def run_cli(*args, cwd=None):
    result = subprocess.run([sys.executable, str(CLI), *map(str, args)], capture_output=True, text=True,
                            encoding="utf-8", cwd=cwd, env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=60)
    assert result.stdout.strip(), result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1]), result.returncode


def write(root: Path, relative: str, text: str = "", data: bytes = None):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if data is not None:
        path.write_bytes(data)
    else:
        path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "repo"
    # Flutter 앱
    write(root, "app/pubspec.yaml", "name: sample_app\nflutter:\n  uses-material-design: true\n")
    write(root, "app/lib/features/quiz/presentation/pages/quiz_page.dart",
          "import 'package:sample_app/features/quiz/data/quiz_repository.dart';\n"
          "class QuizScreen {\n"
          "  bool loading = false;\n"
          "  final bool isReady = true;\n"
          "  // 기존에는 직접 호출했는데 바꿨다\n"
          "  void build() { final color = Color(0xFF112233); final spinner = CupertinoActivityIndicator(); }\n"
          "  void load() { try { run(); } catch (_) {} }\n"
          "}\n")
    write(root, "app/lib/features/quiz/data/quiz_repository.dart", "class QuizRepository {}\n")
    # Spring 멀티모듈 (순환 포함)
    write(root, "server/settings.gradle", "include ':core', ':web', ':api'\n")
    write(root, "server/build.gradle", "plugins { id 'org.springframework.boot' }\n")
    write(root, "server/core/build.gradle", "dependencies { implementation project(':web') }\n")
    write(root, "server/web/build.gradle", "dependencies { api project(':core') }\n")
    write(root, "server/api/build.gradle", "dependencies { implementation project(':core')\n testImplementation project(':web') }\n")
    # Python
    write(root, "ai/pyproject.toml", "[project]\nname='ai'\n")
    write(root, "ai/app/service.py",
          'TEMPLATE = """\n* **버그 수정** 문자열 안\n"""\n\n'
          "def create_branch(name: str) -> bool:\n    return True\n\n"
          "def load_svc_cfg(strict: bool):\n    try:\n        pass\n    except Exception:\n        pass\n")
    write(root, "ai/app/long_module.py", "\n".join(f"VALUE_{i} = {i}" for i in range(320)) + "\n")
    # JS
    write(root, "web/package.json", json.dumps({"dependencies": {"react": "18"}}))
    write(root, "web/src/components/SearchBar.tsx",
          "export function SearchInput() { const style = '#4F46E5'; return null; }\n")
    # 자산: 같은 내용 사본, 같은 이름·다른 내용
    write(root, "app/assets/logo.png", data=b"LOGO-NEW")
    write(root, "web/public/logo.png", data=b"LOGO-NEW")
    write(root, "server/web/src/main/resources/static/images/logo.png", data=b"LOGO-OLD")
    # 규칙 문서 · 이어받을 자료
    write(root, "CLAUDE.md", "- 코드 주석 필수 — WHY 중심\n- 설정은 `docs/missing-guide.md` 참고\n- `app/pubspec.yaml`\n")
    write(root, "docs/ARCHITECTURE-AUDIT.md", "# audit\n")
    return root


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull})


def _write_spinner_rule(root):
    write(root, "docs/architecture/rules/no-direct-spinner.rule",
          "description=로딩 인디케이터 직접 사용 금지\n"
          "paths=app/lib/features/\n"
          "extensions=.dart\n"
          "pattern=CupertinoActivityIndicator\\(\n")


PAGE = "app/lib/features/quiz/presentation/pages/quiz_page.dart"
NEW_SPINNER = "app/lib/features/quiz/presentation/widgets/loading_box.dart"


def _replace_spinner(root):
    page = root / PAGE
    page.write_text(page.read_text(encoding="utf-8").replace("CupertinoActivityIndicator()", "AppLoading()"), encoding="utf-8")


def test_errors_are_json(project, tmp_path):
    assert run_cli("no-such-subcommand")[0]["code"] == "bad_args"
    assert run_cli("scan", project / "nope")[0]["code"] == "path_not_found"
    assert run_cli("diff", tmp_path)[0]["code"] == "git_failed"


def test_audit_facts(project):
    # detect: 스택·Gradle 하위 모듈 묶기·규칙 문서·이전 감사
    detected = run_cli("detect", project)[0]
    stacks = {(s["stack"], s["module"]) for s in detected["stacks"]}
    assert {("flutter", "app"), ("spring", "server"), ("python", "ai"), ("javascript", "web")} <= stacks
    assert sorted(next(s for s in detected["stacks"] if s["module"] == "server")["modules"]) == ["server/api", "server/core", "server/web"]
    assert "CLAUDE.md" in detected["rule_documents"] and "docs/ARCHITECTURE-AUDIT.md" in detected["prior_audits"]

    # scan: 범주별 대표 사례 (여러 줄 문자열 안의 문구는 주석 아님)
    findings = run_cli("scan", project, "--record")[0]["findings"]
    names = {f["name"] for f in findings["boolean_names"]}
    assert "loading" in names and "strict" in names and "isReady" not in names
    assert any(f["name"] == "create_branch" for f in findings["boolean_functions"])
    assert any("기존에는" in f["text"] for f in findings["history_comments"])
    assert not any("버그 수정" in f["text"] for f in findings["history_comments"])
    assert {f["kind"] for f in findings["hardcoded_tokens"]} >= {"color_literal", "hex_color"}
    assert any(f["word"] == "svc" for f in findings["abbreviations"])
    assert {f["path"] for f in findings["swallowed_catch"]} >= {PAGE, "ai/app/service.py"}
    assert {f["path"] for f in findings["long_files"]} == {"ai/app/long_module.py"}
    mismatched = {f["path"]: f["first_type"] for f in findings["file_type_mismatch"]}
    assert mismatched == {PAGE: "QuizScreen", "web/src/components/SearchBar.tsx": "SearchInput"}
    assert (project / "docs/architecture/metrics.jsonl").read_text(encoding="utf-8").count("\n") == 1

    # assets: 같은 내용 사본 + 같은 이름·다른 내용
    assets = run_cli("assets", project)[0]
    assert sorted(assets["identical_copies"][0]["paths"]) == ["app/assets/logo.png", "web/public/logo.png"]
    assert assets["same_name_different_content"][0]["name"] == "logo.png"

    # deps: 화면 > 데이터 직접 import, Gradle 순환
    dependencies = run_cli("deps", project)[0]
    violation = dependencies["layer_violations"][0]
    assert (violation["from_layer"], violation["to_layer"]) == ("presentation", "infrastructure")
    # core <-> web 만 순환, 테스트 범위 의존(api > web)은 순환 판정 밖
    assert [sorted(set(c)) for c in dependencies["gradle_modules"]["cycles"]] == [["core", "web"]]
    assert [e["to"] for e in dependencies["gradle_modules"]["test_edges"]] == ["web"]

    # rule-docs: 없는 경로 참조, 줄글 주석 유도 문구
    document = next(d for d in run_cli("rule-docs", project)[0]["documents"] if d["path"] == "CLAUDE.md")
    assert [m["reference"] for m in document["missing_references"]] == ["docs/missing-guide.md"]
    assert document["prose_comment_inducing"]


def test_judgment_aids_from_dogfood(project):
    """레퍼런스 레포 4곳 실측에서 나온 오탐·놓침 회귀 (#867)"""
    # 출처: 도구 설치물·외부 라이브러리는 제외, 테스트는 따로 센다
    write(project, ".github/scripts/changelog_manager.py", "def run_tmp_job(flag: bool):\n    pass\n")
    write(project, "server/web/src/main/resources/static/js/semantic.js",
          "/*\n * # Semantic UI - 1.12.2\n */\nvar tmpValue = 1;\n")
    write(project, "app/test/quiz_test.dart", "void main() { final bool ready = true; }\n")
    # Java: 주입 필드 타입명 오탐, 타입 선언 지역 변수 놓침, Spring Data·override·catch
    write(project, "server/web/src/main/java/com/sample/web/MemberService.java",
          "package com.sample.web;\n\nimport com.sample.core.MemberRepository;\n"
          "public class MemberService {\n  private final JwtUtil jwtUtil;\n"
          "  void load() { Member curMember = find();\n"
          "    try { save(); } catch (Exception e) { log.error(\"rollback\"); rollback(); }\n  }\n"
          "  @Override\n  public boolean equals(Object other) { return true; }\n"
          "  // 기존 SSE 방식에서 전환\n  // 테스트 전용 스키마를 생성/삭제함\n  // 관리자가 모델명만 바꿨을 뿐인데\n}\n")
    write(project, "server/core/src/main/java/com/sample/core/MemberRepository.java",
          "package com.sample.core;\npublic interface MemberRepository { boolean existsByStudentId(String id); }\n")
    # Flutter: 공통 스피너가 있는데 화면이 직접 씀, 함수 타입은 함수 이름이 아님
    write(project, "app/lib/core/widgets/app_spinner.dart", "class AppSpinner { build() => CircularProgressIndicator(); }\n")
    write(project, "app/lib/features/quiz/presentation/widgets/quiz_card.dart",
          "class QuizCard { build() => CircularProgressIndicator(); final bool Function(int) onTap; }\n")

    scanned = run_cli("scan", project, "--limit", "200")[0]
    findings, counts = scanned["findings"], scanned["counts"]
    assert scanned["excluded"]["tooling"]["count"] == 1 and scanned["excluded"]["vendored"]["count"] == 1
    assert ".github/" not in json.dumps(findings) and "semantic" not in json.dumps(findings)
    assert scanned["test_counts"]["boolean_names"] == 1 and counts["boolean_names"] == 2  # loading, strict
    abbreviations = {f["name"] for f in findings["abbreviations"]}
    assert "curMember" in abbreviations and "JwtUtil" not in abbreviations
    boolean_functions = {f["name"] for f in findings["boolean_functions"]}
    assert not boolean_functions & {"equals", "existsByStudentId", "Function"}
    history = [f["text"] for f in findings["history_comments"]]
    assert any("전환" in t for t in history) and not any("삭제함" in t or "관리자가" in t for t in history)
    bypassed = next(b for b in findings["bypassed_components"] if b["call"] == "CircularProgressIndicator(")
    assert bypassed["wrappers"] == ["app/lib/core/widgets/app_spinner.dart"] and bypassed["files"] == 1
    catch = next(f for f in findings["unhandled_catch"] if f["path"].endswith("MemberService.java"))
    assert (catch["kind"], catch["is_catch_all"], catch["has_log"]) == ("no_rethrow", True, True)
    assert scanned["review_order"][0]["group"] == "동작 위험"

    # deps: 줄 번호(앞 빈 줄), 모듈 간 저장소 직접 사용
    dependencies = run_cli("deps", project)[0]
    cross = dependencies["cross_module_repository_imports"][0]
    assert (cross["from_module"], cross["to_module"], cross["line"]) == ("server/web", "server/core", 3)

    # assets: 형식만 다른 같은 이름은 낡은 사본이 아님
    write(project, "app/assets/star.svg", "<svg/>")
    write(project, "web/public/star.png", data=b"STAR")
    assets = run_cli("assets", project)[0]
    assert not any(s["name"].startswith("star") for s in assets["same_name_different_content"])
    assert assets["format_variants"]["count"] == 1

    # rule-docs: MIME 타입·꼬리 일치·gitignore 대상은 없는 경로가 아님
    write(project, ".gitignore", "application-prod.yml\n")
    write(project, "server/CLAUDE.md", "- `multipart/form-data`\n- `web/OrderService.java` 없음, `web/MemberService.java`·`com/sample/core/` 있음\n"
                                       "- `application-prod.yml` 은 커밋 안 함\n")
    document = next(d for d in run_cli("rule-docs", project)[0]["documents"] if d["path"] == "server/CLAUDE.md")
    assert [m["reference"] for m in document["missing_references"]] == ["web/OrderService.java"]
    assert [m["reference"] for m in document["ignored_references"]] == ["application-prod.yml"]

    # get-output-path 는 경로만 (승인 전 호출해도 레포가 바뀌지 않음)
    run_cli("get-output-path", project, "--title", "점검")
    assert not (project / "docs/architecture/audits").exists()


def test_generic_false_positive_guards(tmp_path):
    """2차 실측 오탐 회귀: JPA 어노테이션≠생성물, 문서 예시 URL, 앞선 catch 통과, 규칙 하나만 끄는 린트, 조합 모듈"""
    root = tmp_path / "repo"
    write(root, "a/src/main/java/x/Entity.java", "@Entity\npublic class Row { @GeneratedValue Long id; }\n")
    write(root, "a/src/main/java/x/Docs.java",
          'class Docs {\n  String s = """\n  {"url": "https://api.test.io/x"}\n  """;\n'
          '  @Schema(example = "https://a.test.io/y") String t;\n  String real = "https://real.test.io";\n}\n')
    write(root, "a/src/main/java/x/Svc.java",
          "class Svc { void f() { try { g(); } catch (BizException e) { throw e; } catch (Exception e) { throw new BizException(e); } } }\n")
    write(root, "web/src/slice.ts", "/* eslint-disable no-param-reassign */\nexport const a = 1;\n")
    write(root, "web/src/ui.tsx", "async function load() { try { await f(); } catch (e) { setError(String(e)); } }\n")
    write(root, "web/src/types/api/res.ts", "export type Res = { ok: boolean }\n")
    write(root, ".gitignore", "")
    _git(root, "init", "-q")
    write(root, "docs/shots/.gitignore", "*\n")
    write(root, "docs/shots/a.png", data=b"SAME")
    write(root, "app/assets/a.png", data=b"SAME")
    write(root, "app/assets/b.png", data=b"SAME")

    scanned = run_cli("scan", root, "--limit", "100")[0]
    findings = scanned["findings"]
    assert "excluded" in scanned and "generated" not in scanned["excluded"]
    assert [f["url"] for f in findings["hardcoded_urls"]] == ["https://real.test.io"]
    rewrap = next(f for f in findings["unhandled_catch"] if f["path"].endswith("Svc.java"))
    assert rewrap["kind"] == "rewrap_all" and rewrap["has_passthrough_before"]
    assert next(f for f in findings["unhandled_catch"] if f["path"].endswith("ui.tsx"))["sets_error_state"]
    assert findings["lint_disabled_files"] == []
    # 하위 폴더 .gitignore 는 그 폴더에만 적용 (사본 묶음에서 빠지고, 다른 영역 사본은 남음)
    copies = run_cli("assets", root)[0]["identical_copies"]
    assert all("docs/shots" not in path for group in copies for path in group["paths"])
    assert len(copies) == 1 and len(copies[0]["paths"]) == 2


def test_check_diff(project):
    target = write(project, "ai/app/pricing.py",
                   "# 할인율 10% 적용\ndef apply_discount(price):\n    return price * 0.9\n\n\n"
                   "# 세금 계산\ndef apply_tax(price):\n    return price * 1.1\n")
    _git(project, "init", "-q")
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "base")

    # 코드만 바뀜(주석 그대로) + 코드 그대로인데 주석만 고침 + 비슷한 이름의 새 함수(새 파일)
    target.write_text("# 할인율 10% 적용\ndef apply_discount(price):\n    return price * 0.8\n\n\n"
                      "# 부가세 포함 금액 계산 로직입니다\ndef apply_tax(price):\n    return price * 1.1\n", encoding="utf-8")
    write(project, "ai/app/discount_helper.py", "def apply_discount_rate(price):\n    return price\n")

    payload = run_cli("diff", project)[0]
    assert any(s["path"] == "ai/app/pricing.py" and s["comment_line"] == 1 for s in payload["stale_comment_suspects"])
    assert any(r["line"] == 6 for r in payload["rewritten_existing_comments"])
    assert any("prose_ending" in p["kinds"] for p in payload["added_comment_problems"])
    new_definition = next(d for d in payload["new_definitions"] if d["name"] == "apply_discount_rate")
    assert any(s["name"] == "apply_discount" for s in new_definition["similar_existing"])


def test_ledger_freeze_check_tighten(project):
    _write_spinner_rule(project)
    assert run_cli("ledger", project, "check")[0]["verdict"] == "fail"
    assert run_cli("ledger", project, "freeze", "--rule", "no-direct-spinner")[0]["frozen"] == 1
    assert run_cli("ledger", project, "check")[0]["verdict"] == "pass"
    # 동결 목록에는 줄을 더할 수 없다
    assert run_cli("ledger", project, "freeze", "--rule", "no-direct-spinner")[0]["code"] == "allow_exists"

    # 새 위반 > 실패
    write(project, NEW_SPINNER, "final x = CupertinoActivityIndicator();\n")
    assert [n["path"] for n in run_cli("ledger", project, "check")[0]["rules"][0]["new"]] == [NEW_SPINNER]
    (project / NEW_SPINNER).unlink()

    # 고쳐짐 > 목록에서 지우라고 실패 > tighten 후 통과
    _replace_spinner(project)
    assert run_cli("ledger", project, "check")[0]["rules"][0]["fixed"] == [PAGE]
    run_cli("ledger", project, "tighten")
    assert run_cli("ledger", project, "check")[0]["verdict"] == "pass"


def test_init_installs_without_overwriting(project):
    # conventions: missing > same > 프로젝트가 고치면 locally_modified, 다시 설치해도 안 덮음
    assert {d["status"] for d in run_cli("conventions", project, "check", "--stack", "flutter")[0]["documents"]} == {"missing"}
    run_cli("conventions", project, "install", "--stack", "flutter")
    assert {d["status"] for d in run_cli("conventions", project, "check", "--stack", "flutter")[0]["documents"]} == {"same"}
    installed = project / "docs/architecture/CONVENTIONS.md"
    installed.write_text(installed.read_text(encoding="utf-8") + "\n- 프로젝트 전용 규칙\n", encoding="utf-8")
    statuses = {d["installed"]: d["status"] for d in run_cli("conventions", project, "check")[0]["documents"]}
    assert statuses["docs/architecture/CONVENTIONS.md"] == "locally_modified"
    assert run_cli("conventions", project, "install")[0]["written"] == []

    # install-tests: 설치 1회, 두 번째는 거부
    assert run_cli("install-tests", project, "--stack", "python", "--module", "ai")[0]["installed"] == \
        "ai/tests/architecture/test_architecture_rules.py"
    assert run_cli("install-tests", project, "--stack", "python", "--module", "ai")[0]["code"] == "exists"

    # get-output-path
    assert run_cli("get-output-path", project, "--title", "전체 점검 1차")[0]["summary"].endswith("_전체_점검_1차.md")


def test_rule_test_templates_match_cli(project):
    """CLI ledger check <-> Python·Node 템플릿 판정 같음, 4개 템플릿의 제외 목록이 CLI와 같음"""
    sys.path.insert(0, str(SKILL / "scripts"))
    from arch.source_files import SKIPPED_DIRECTORY_NAMES
    for template in (p for p in TEMPLATES.glob("*/*") if p.is_file()):
        text = template.read_text(encoding="utf-8")
        assert all(f"'{n}'" in text or f'"{n}"' in text for n in SKIPPED_DIRECTORY_NAMES), template.name
        assert "docs/architecture/" in text, template.name

    _write_spinner_rule(project)
    run_cli("ledger", project, "freeze", "--rule", "no-direct-spinner")
    run_cli("install-tests", project, "--stack", "python", "--module", "ai")
    runners = {"python": [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                          str(project / "ai/tests/architecture/test_architecture_rules.py")]}
    if shutil.which("node"):
        run_cli("install-tests", project, "--stack", "javascript", "--module", "web")
        runners["javascript"] = ["node", "--test", str(project / "web/test/architecture/architecture.rules.test.mjs")]

    def verdicts():
        cli = run_cli("ledger", project, "check")[0]["verdict"]
        templates = {name: subprocess.run(command, capture_output=True, cwd=project, timeout=120).returncode == 0
                     for name, command in runners.items()}
        return cli, templates

    assert verdicts() == ("pass", {name: True for name in runners})
    _replace_spinner(project)  # 고쳐진 항목이 동결 목록에 남음 > 모두 실패
    assert verdicts() == ("fail", {name: False for name in runners})
