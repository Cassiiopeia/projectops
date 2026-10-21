"""타입별 워크플로우 댓글·로그 언어 (#769 3층 3단계).

- 댓글: github-script 가 $RUNNER_TEMP/projectops-messages.cjs(messages.py js) 의 t() 로 카탈로그 문구를 쓴다
- 한국어 레포가 받는 댓글은 이관 전과 바이트 단위로 같다 (golden: 이관 전 렌더 결과의 해시)
- 실행 로그·스텝 이름·입력 설명은 영문. 한글이 남는 줄은 아래 KEPT_KOREAN 에 이유와 함께만 둔다
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "test" / "helpers"))
import workflow_comment_render as render  # noqa: E402

sys.path.insert(0, str(SCRIPTS))
from i18n import contracts  # noqa: E402

HANGUL = re.compile(r"[가-힣]")
EN = json.loads((SCRIPTS / "i18n" / "en.json").read_text(encoding="utf-8"))
KO = json.loads((SCRIPTS / "i18n" / "ko.json").read_text(encoding="utf-8"))
GOLDEN = json.loads((SCRIPTS / "test" / "golden" / "type_workflow_comments_ko.json").read_text(encoding="utf-8"))
WORKFLOWS = render.type_workflows()
COMMENT_WORKFLOWS = [p for p in WORKFLOWS if p.relative_to(render.TYPES_DIR).as_posix() in GOLDEN]
KEY_CALL = re.compile(r"""\bt\(\s*'([a-z0-9_.]+)'""")
RAW_KEY = re.compile(r"\b(?:%s)\.[a-z0-9_]+(?:\.[a-z0-9_]+)*\b" % "|".join(
    sorted({k.split(".")[0] for k in EN}, key=len, reverse=True)))

# 번역하지 않고 남기는 한국어: (파일 — None 이면 전체, 줄에 들어 있는 문자열, 이유)
KEPT_KOREAN = [
    (None, "###\\s*브랜치", "이슈 헬퍼 댓글의 브랜치 제목을 읽는 정규식 (contracts.BRANCH_HEADING)"),
    (None, "/### 브랜치\\s*", "이슈 헬퍼 댓글의 브랜치 제목을 읽는 정규식 (contracts.BRANCH_HEADING)"),
    (None, "'### 브랜치'", "계약 제목을 댓글에 값으로 넘긴다 (카탈로그에 넣지 않는다)"),
    (None, "'Preview 배포 완료'", "이관 전에 달린 한국어 배포 댓글을 찾는 표식"),
    (None, "'Preview 환경 삭제 완료'", "이관 전에 달린 한국어 삭제 댓글을 찾는 표식"),
    ("python/server-deploy/PROJECT-PYTHON-PR-PREVIEW.yaml", "프로젝트명", "사용자가 고쳐 쓰는 예시 경로 (실제 마운트 경로로 쓰인다)"),
    ("spring/publish/nexus/PROJECT-SPRING-NEXUS-CI.yml", "✅ 성공", "GITHUB_OUTPUT 상태값 — if: 조건과 스크립트가 비교한다"),
    ("spring/publish/nexus/PROJECT-SPRING-NEXUS-CI.yml", "❌ 실패", "GITHUB_OUTPUT 상태값 — if: 조건과 스크립트가 비교한다"),
    ("flutter/PROJECT-FLUTTER-ANDROID-PLAYSTORE-CICD.yaml", "업데이트\"", "Play Store ko-KR 릴리스 노트 기본값 (스토어 언어를 따른다)"),
]
PR_TRIGGERS = ("pull_request", "pull_request_target")


def _rel(path: Path) -> str:
    return path.relative_to(render.TYPES_DIR).as_posix()


def _doc(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# ── 문구 모듈 ─────────────────────────────────────────────────────────────

def test_문구_모듈은_언어별로_치환하고_경과_시간을_쓴다(tmp_path):
    for lang, expected in (("ko", ["1분 2초", "3초"]), ("en", ["1m 2s", "3s"])):
        js = subprocess.run([sys.executable, str(render.MESSAGES), "js", "comment.", "--lang", lang],
                            capture_output=True, text=True, check=True).stdout
        (tmp_path / f"{lang}.cjs").write_text(js, encoding="utf-8")
        probe = (f"const m = require({json.dumps(str(tmp_path / (lang + '.cjs')))});"
                 "console.log(JSON.stringify([m.elapsed(1, 2), m.elapsed(0, 3), m.lang, "
                 "m.t('no.such.key'), m.t('comment.elapsed.sec', {})]))")
        out = json.loads(subprocess.run(["node", "-e", probe], capture_output=True, text=True, check=True).stdout)
        assert out[:3] == [*expected, lang]
        # 없는 키는 키 그대로, 값이 없는 자리표시자는 그대로 (messages.py 와 같은 규칙)
        assert out[3] == "no.such.key"
        assert out[4] == EN["comment.elapsed.sec"] if lang == "en" else KO["comment.elapsed.sec"]


# ── 키와 불러오기 ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("wf", WORKFLOWS, ids=_rel)
def test_워크플로우가_쓰는_키는_en_ko_모두에_있다(wf):
    used = set(KEY_CALL.findall(wf.read_text(encoding="utf-8")))
    assert sorted(k for k in used if k not in EN or k not in KO) == []


@pytest.mark.parametrize("wf", WORKFLOWS, ids=_rel)
def test_문구_모듈을_쓰는_잡은_먼저_불러오고_접두사가_맞다(wf):
    for job_id, job in (_doc(wf).get("jobs") or {}).items():
        names = [s.get("name") for s in job.get("steps") or []]
        prefixes = None
        for index, step in enumerate(job.get("steps") or []):
            if step.get("name") == render.LOADER_STEP:
                assert index > 0 and names[index - 1] == render.CATALOG_STEP, (job_id, "catalog checkout first")
                prefixes = render.loader_prefixes(step)
            script = str((step.get("with") or {}).get("script", ""))
            if render.MODULE_NAME not in script:
                continue
            assert prefixes, f"{job_id}: '{step.get('name')}' uses the message module before '{render.LOADER_STEP}'"
            for key in KEY_CALL.findall(script):
                assert key.startswith(tuple(prefixes)), (job_id, step.get("name"), key, prefixes)


# ── 댓글 렌더링 ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("wf", COMMENT_WORKFLOWS, ids=_rel)
def test_한국어_댓글은_이관_전과_같다(wf):
    rendered = render.render(_doc(wf), "ko")
    golden = GOLDEN[_rel(wf)]
    assert sorted(rendered) == sorted(golden), "github-script steps were added, removed or reordered"
    bad = []
    for label, runs in rendered.items():
        for variant, run in enumerate(runs):
            if render.digest(run["visible"]) != golden[label][variant]:
                bad.append(f"{label} variant {variant}: {json.dumps(run['visible'], ensure_ascii=False)[:600]}")
    assert not bad, "\n".join(bad)


@pytest.mark.parametrize("wf", COMMENT_WORKFLOWS, ids=_rel)
def test_영문_댓글에는_한글과_풀리지_않은_키가_없다(wf):
    bad = []
    for label, runs in render.render(_doc(wf), "en").items():
        for variant, run in enumerate(runs):
            blob = json.dumps(run["visible"], ensure_ascii=False)
            # 계약 문자열(### 브랜치 등)은 어느 언어에서나 그대로 나간다
            for contract in contracts.ALL:
                blob = blob.replace(contract, "")
            hit = HANGUL.search(blob) or RAW_KEY.search(blob)
            if hit:
                bad.append(f"{label} variant {variant}: ...{blob[max(0, hit.start() - 100):hit.start() + 60]}")
    assert not bad, "\n".join(bad)


# ── 실행 로그는 영문 ──────────────────────────────────────────────────────

def _code_part(line: str) -> str:
    """YAML·셸·JS 주석을 뗀 코드 부분 (URL 의 // 는 남긴다)"""
    stripped = line.strip()
    if stripped.startswith(("#", "//")):
        return ""
    line = re.sub(r"(^|\s)//\s.*$", "", line)
    return re.sub(r"\s#\s.*$", "", line)


def _required_check_job_names(doc) -> set:
    """PR 로 도는 워크플로우의 잡 이름 — 브랜치 보호의 필수 상태 체크 이름일 수 있어 번역하지 않는다"""
    triggers = doc.get("on", doc.get(True)) or {}
    if not any(t in triggers for t in PR_TRIGGERS):
        return set()
    return {str(job.get("name")) for job in (doc.get("jobs") or {}).values() if job.get("name")}


@pytest.mark.parametrize("wf", WORKFLOWS, ids=_rel)
def test_주석_밖에는_한국어가_없다(wf):
    kept = [text for path, text, _reason in KEPT_KOREAN if path in (None, _rel(wf))]
    job_names = _required_check_job_names(_doc(wf))
    bad = []
    for no, line in enumerate(wf.read_text(encoding="utf-8").splitlines(), 1):
        code = _code_part(line)
        if not HANGUL.search(code) or any(text in line for text in kept):
            continue
        job_name = re.match(r"^ {4}name:\s*(.+?)\s*$", code)
        if job_name and job_name.group(1).strip("'\"") in job_names:
            continue
        bad.append(f"{no}: {line.strip()}")
    assert not bad, "\n".join(bad)


@pytest.mark.parametrize("wf", WORKFLOWS, ids=_rel)
def test_남긴_잡_이름에는_이유_주석이_있다(wf):
    lines = wf.read_text(encoding="utf-8").splitlines()
    for no, line in enumerate(lines):
        if re.match(r"^ {4}name:", line) and HANGUL.search(_code_part(line)):
            assert "필수 상태 체크" in lines[no - 1], f"{_rel(wf)}:{no + 1} {line.strip()}"


# ── 문구 카탈로그 받기 스텝 ───────────────────────────────────────────────

class _StrictLoader(yaml.SafeLoader):
    """같은 키가 두 번 나오면 실패 (기본 로더는 뒤의 값으로 조용히 덮는다)"""


def _no_duplicate_keys(loader, node, deep=False):
    keys = [loader.construct_object(k, deep=deep) for k, _ in node.value]
    duplicated = {k for k in keys if keys.count(k) > 1}
    if duplicated:
        raise yaml.constructor.ConstructorError(None, None, f"duplicate keys {duplicated}", node.start_mark)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys)


@pytest.mark.parametrize("wf", WORKFLOWS, ids=_rel)
def test_워크플로우에_중복_키가_없다(wf):
    yaml.load(wf.read_text(encoding="utf-8"), Loader=_StrictLoader)


@pytest.mark.parametrize("wf", COMMENT_WORKFLOWS, ids=_rel)
def test_카탈로그는_기본_브랜치에서_받고_실패해도_빌드를_막지_않는다(wf):
    found = 0
    for job in (_doc(wf).get("jobs") or {}).values():
        for step in job.get("steps") or []:
            if step.get("name") != render.CATALOG_STEP:
                continue
            found += 1
            options = step["with"]
            # PR 닫힘 이벤트의 merge ref 는 이미 없을 수 있고, PR 이 언어를 바꿔 끼우지 못하게 한다
            assert options["ref"] == "${{ github.event.repository.default_branch }}"
            assert options["path"] == ".projectops-messages"
            assert step.get("continue-on-error") is True
    assert found, "comment workflow without a catalog checkout"
    text = wf.read_text(encoding="utf-8")
    # 받은 폴더는 지운다 (뒤의 전체 checkout 과 겹치지 않게), 실패하면 키를 보여 주는 대체 모듈
    assert text.count("rm -rf .projectops-messages") == found
    assert text.count("Message catalog not found") == found
