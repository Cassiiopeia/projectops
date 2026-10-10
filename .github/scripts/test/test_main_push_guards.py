"""main push 때 도는 워크플로우들의 오판·재시도·폭주 회귀 방지 (#806 · #807 · #808).

- #806 VERSION-CONTROL 가드가 `version.yml` **파일 이름**만 보고 릴리스로 판정해,
  설정만 바꾼 push(semver_auto 켜기, projectops 업데이트)에서 버전·태그가 빠졌다.
- #807 README-VERSION-UPDATE 재시도의 `git pull --rebase` 가 앞 단계 chmod 로 생긴
  스테이징 안 된 변경 때문에 거부돼 재시도가 한 번도 못 돌았다.
- #808 PR-PREVIEW destroy 가 모든 PR·이슈 닫힘마다 SSH·댓글을 돌려 secret 없는 레포에서
  실패하고, 일괄 닫힘에서는 댓글 rate limit 에 걸렸다.

가드는 문자열 검사가 아니라 **임시 git 저장소에서 그 run 블록을 실제로 돌려** 본다.
"""
import os
import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
WF = ROOT / ".github" / "workflows"
COMMON = WF / "project-types" / "common"
PREVIEWS = [
    WF / "project-types" / "spring" / "server-deploy" / "PROJECT-SPRING-PR-PREVIEW.yaml",
    WF / "project-types" / "python" / "server-deploy" / "PROJECT-PYTHON-PR-PREVIEW.yaml",
]


def _steps(path, job):
    return yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"][job]["steps"]


def _step(path, job, name):
    for s in _steps(path, job):
        if s.get("name") == name:
            return s
    raise AssertionError(f"{path.name}: '{name}' 단계를 못 찾았다")


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _run_guard(tmp_path, before_yml, after_yml, extra_file=True):
    """두 커밋 사이 push 를 흉내 내고 가드가 내놓은 is_release_merge 를 돌려준다."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    if before_yml is not None:
        (repo / "version.yml").write_text(before_yml, encoding="utf-8")
    (repo / "a.txt").write_text("0", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    before = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                            capture_output=True, text=True).stdout.strip()
    (repo / "version.yml").write_text(after_yml, encoding="utf-8")
    if extra_file:
        (repo / "a.txt").write_text("1", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "push")

    script = _step(WF / "PROJECT-COMMON-VERSION-CONTROL.yaml", "version-bump",
                   "릴리스 머지 여부 확인 (안전망 가드)")["run"]
    script = script.replace("${{ github.event.before }}", before)
    out = tmp_path / "out.txt"
    subprocess.run(["bash", "-e", "-c", script], cwd=repo, check=True,
                   env={**os.environ, "GITHUB_OUTPUT": str(out)}, capture_output=True)
    m = re.search(r"is_release_merge=(\w+)", out.read_text(encoding="utf-8"))
    return m.group(1)


YML = 'version: "{v}"\nmetadata:\n  template:\n    options:\n      semver_auto: {s}\n'


def test_settings_only_change_still_bumps(tmp_path):
    """version 값은 그대로, 설정만 바뀐 push 는 릴리스가 아니다 (#806 실사고)."""
    got = _run_guard(tmp_path, YML.format(v="0.0.251", s="false"), YML.format(v="0.0.251", s="true"))
    assert got == "false"


def test_version_change_is_release_merge(tmp_path):
    """RELEASE-CHANGELOG 가 version 을 올린 머지는 그대로 건너뛴다."""
    got = _run_guard(tmp_path, YML.format(v="0.0.251", s="true"), YML.format(v="0.1.0", s="true"))
    assert got == "true"


def test_first_integration_is_not_bumped(tmp_path):
    """version.yml 이 처음 생긴 push(최초 통합)는 기존처럼 건너뛴다."""
    got = _run_guard(tmp_path, None, YML.format(v="0.0.1", s="true"))
    assert got == "true"


def test_push_without_version_yml_bumps(tmp_path):
    """version.yml 을 안 건드린 직접 push 는 안전망이 올린다."""
    same = YML.format(v="1.2.3", s="false")
    assert _run_guard(tmp_path, same, same) == "false"


def test_readme_retry_survives_unstaged_changes():
    """재시도의 pull 이 스테이징 안 된 변경(chmod +x)에 막히면 안 된다 (#807)."""
    for path in (WF / "PROJECT-COMMON-README-VERSION-UPDATE.yaml",
                 COMMON / "PROJECT-COMMON-README-VERSION-UPDATE.yaml"):
        run = _step(path, "update-readme", "변경사항 커밋 및 푸시")["run"]
        pulls = re.findall(r"git pull --rebase[^\n]*", run)
        assert pulls, f"{path}: 재시도 pull 을 못 찾았다"
        assert all("--autostash" in p for p in pulls), pulls


def test_preview_destroy_only_when_something_was_deployed():
    """삭제·삭제 댓글은 '삭제 대상 확인'이 true 일 때만 돈다 (#808)."""
    for path in PREVIEWS:
        steps = _steps(path, "destroy-preview")
        names = [s.get("name") for s in steps]
        assert names.index("삭제 대상 확인") < names.index("컨테이너 & 이미지 삭제"), path.name
        target = _step(path, "destroy-preview", "삭제 대상 확인")
        assert target.get("id") == "target"
        # secret 이 없으면 실패가 아니라 건너뛰어야 한다
        assert "secrets.SERVER_HOST" in str(target.get("env"))
        for name in ("컨테이너 & 이미지 삭제", "삭제 완료 코멘트"):
            cond = _step(path, "destroy-preview", name).get("if", "")
            assert "steps.target.outputs.should_destroy == 'true'" in cond, (path.name, name)


# ── #805: main 직행 레포에서 semver_auto 가 무시되던 문제 ─────────────────
def _run_bump(tmp_path, semver, with_dev_branch, subjects):
    """push 구간 커밋 제목으로 '승격 폭 결정' 단계를 실제로 돌린다."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", str(origin))
    repo = tmp_path / "work"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "remote", "add", "origin", str(origin))
    (repo / "version.yml").write_text(YML.format(v="0.0.251", s=semver), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "push", "-q", "origin", "main")
    if with_dev_branch:
        _git(repo, "push", "-q", "origin", "main:develop")
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()
    for i, s in enumerate(subjects):
        (repo / f"f{i}").write_text(s, encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", s)

    script = _step(WF / "PROJECT-COMMON-VERSION-CONTROL.yaml", "version-bump", "승격 폭 결정")["run"]
    script = script.replace("${{ github.event.repository.default_branch || 'main' }}", "main")
    script = script.replace(".github/scripts/version_manager.py",
                            str(ROOT / ".github" / "scripts" / "version_manager.py"))
    script = script.replace(".github/scripts/changelog_manager.py",
                            str(ROOT / ".github" / "scripts" / "changelog_manager.py"))
    out = tmp_path / "out.txt"
    subprocess.run(["bash", "-e", "-c", script], cwd=repo, check=True, capture_output=True,
                   env={**os.environ, "GITHUB_OUTPUT": str(out), "RANGE": f"{base}..HEAD",
                        "RUNNER_TEMP": str(tmp_path)})
    return re.search(r"bump=(\w+)", out.read_text(encoding="utf-8")).group(1)


FEAT = ["제목 : feat : 새 기능 https://x/1", "제목 : fix : 고침 https://x/2"]


def test_main_direct_repo_uses_semver_auto(tmp_path):
    """개발 브랜치가 없으면 이 워크플로우가 유일한 릴리스 경로 — feat 는 minor (#805)."""
    assert _run_bump(tmp_path, "true", False, FEAT) == "minor"


def test_main_direct_repo_major(tmp_path):
    assert _run_bump(tmp_path, "true", False, ["제목 : feat! : 깨짐 https://x/1"]) == "major"


def test_repo_with_develop_also_uses_semver_auto(tmp_path):
    """develop 이 있어도 main 직접 push 는 semver_auto 를 따른다 (#815)."""
    assert _run_bump(tmp_path, "true", True, FEAT) == "minor"
    second = tmp_path / "second"
    second.mkdir()
    assert _run_bump(second, "true", True, ["제목 : feat! : 깨짐 https://x/1"]) == "major"


def test_semver_auto_off_stays_patch(tmp_path):
    assert _run_bump(tmp_path, "false", False, FEAT) == "patch"


def test_missing_semver_key_defaults_to_on_in_both_workflows():
    """키가 없으면 켜진 것으로 본다 — 신규·기존 레포 동일 (소유자 결정). 끄려면 false 를 명시한다."""
    for name in ("PROJECT-COMMON-RELEASE-CHANGELOG.yaml", "PROJECT-COMMON-VERSION-CONTROL.yaml"):
        for base in (WF, COMMON):
            text = (base / name).read_text(encoding="utf-8")
            # 읽기는 version_manager get-option 한 곳에서 하고, 기본값 인자가 true 여야 한다 (#832)
            assert "version_manager.py get-option semver_auto true" in text, f"{base.name}/{name}"
            assert "get-option semver_auto false" not in text, f"{base.name}/{name}"


# ── #797: projectops 설치기 버그 YAML 양식 ───────────────────────────────
def test_installer_bug_form_requires_the_fields_that_make_it_reproducible():
    form = yaml.safe_load((ROOT / ".github" / "ISSUE_TEMPLATE" / "projectops-installer-bug.yml").read_text(encoding="utf-8"))
    required = {b["id"] for b in form["body"] if b.get("type") != "markdown" and b.get("validations", {}).get("required")}
    assert {"version", "os", "how", "command", "expected", "log"} <= required
    assert "assignees" not in form, "이 저장소 소유자를 담당자로 고정하면 안 된다 (#782)"
    ids = [b["id"] for b in form["body"] if "id" in b]
    assert len(ids) == len(set(ids))
    # 이 저장소 전용이라 새 프로젝트로 복사·남겨지면 안 된다
    init = (ROOT / ".github" / "scripts" / "template_initializer.py").read_text(encoding="utf-8")
    assert "projectops-installer-bug.yml" in init


# ── #796: npm latest 는 배포 브랜치(main)에 올린 것과 같다 ───────────────────
def test_npm_latest_follows_only_pushes_to_main():
    """main 에 올리면 즉시 latest. develop 은 npm 에 올리지 않는다 (승격 주기 없음)."""
    data = yaml.safe_load((WF / "PROJECT-TEMPLATE-NPM-PUBLISH.yaml").read_text(encoding="utf-8"))
    on = data.get("on", data.get(True))
    assert on["push"]["branches"] == ["main"], "npm 배포 트리거는 main 하나뿐이어야 한다"
    run = _step(WF / "PROJECT-TEMPLATE-NPM-PUBLISH.yaml", "publish-npm", "npm 배포")["run"]
    assert "--tag latest" in run, "dist-tag 를 latest 로 명시해야 정책이 코드에서 보인다"
    assert "--tag next" not in run


# ── 워크플로 최상위 키 중복 (#816 QA 중 발견) ───────────────────────────────
def test_workflows_have_no_duplicate_top_level_keys():
    """로컬 YAML 파서는 중복 키를 조용히 받아들이지만 GitHub 은 워크플로 파일 자체를 거부한다(잡 0개로 실패).

    #816 의 QA 워크플로를 만들다 `permissions:` 가 두 번 들어갔고, 로컬 yaml.safe_load 는 통과했지만 Actions 에서는 실패했다.
    """
    import collections
    bad = []
    for path in sorted(WF.rglob("*.y*ml")):
        keys = re.findall(r"^([A-Za-z_][\w-]*):", path.read_text(encoding="utf-8"), re.M)
        dup = [k for k, c in collections.Counter(keys).items() if c > 1]
        if dup:
            bad.append(f"{path.relative_to(WF)}: {dup}")
    assert not bad, "최상위 키가 중복된 워크플로 (GitHub 이 거부한다):\n" + "\n".join(bad)


# ── #832-6: 브랜치에서 이슈 번호를 뽑는 sed 는 첫 #번호를 쓴다 ─────────────────
def test_test_build_workflows_take_the_first_issue_number_from_a_branch(tmp_path):
    """제목에 `#` 이 또 있는 브랜치에서 탐욕 sed 가 마지막 번호를 잡던 문제. 워크플로의 sed 를 그대로 꺼내 실행한다."""
    import subprocess
    for name in ("PROJECT-FLUTTER-ANDROID-TEST-APK.yaml", "PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml"):
        text = (WF / "project-types" / "flutter" / name).read_text(encoding="utf-8")
        line = next(l for l in text.splitlines() if l.strip().startswith("ISSUE_NUMBER=$(echo \"$BRANCH_NAME\" | sed"))
        script = line.strip()
        for branch, want in (("20261010_#825_title_#3_extra", "825"), ("20261010_#825_title", "825"),
                             ("feature/20261010_#12_x", "12"), ("main", ""), ("20261010_#7", "7")):
            r = subprocess.run(["bash", "-c", f'BRANCH_NAME="{branch}"; {script}; printf "%s" "$ISSUE_NUMBER"'],
                               capture_output=True, text=True)
            assert r.stdout == want, f"{name}: {branch!r} → {r.stdout!r} (기대 {want!r})"
