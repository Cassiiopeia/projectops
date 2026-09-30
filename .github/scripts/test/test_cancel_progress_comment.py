"""취소된 테스트 빌드의 진행 댓글 정리 (#648).

실사고: 새 빌드가 이전 빌드를 취소(concurrency cancel-in-progress)하면 최종 상태를 쓰는
스텝(success/failure)이 하나도 돌지 않아 진행 댓글이 영원히 "진행 중"으로 남았다.
`if: cancelled()` 스텝이 실제로 있고, 수동 실행에서는 돌지 않으며, 기존 성공/실패 스텝은
그대로인지 정적으로 고정한다. 실제 취소 동작은 GitHub 에서만 확인할 수 있다.
"""
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
FLUTTER = ROOT / ".github" / "workflows" / "project-types" / "flutter"

# 파일 -> (진행 댓글을 만드는 job, 기존 최종/중간 갱신 스텝 이름들)
CASES = {
    "PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml": {
        "creator": "notify-start",
        "existing": [
            "진행 상황 댓글 생성",
            "진행 상황 업데이트 - 준비 실패",
            "진행 상황 업데이트 - 준비 완료",
            "진행 상황 업데이트 - IPA 빌드 완료",
            "빌드 실패 시 progress 댓글 업데이트",
            "진행 상황 최종 업데이트 - 성공",
            "진행 상황 최종 업데이트 - 실패",
        ],
    },
    "PROJECT-FLUTTER-ANDROID-TEST-APK.yaml": {
        "creator": "prepare-test-build",
        "existing": [
            "진행 상황 댓글 생성",
            "진행상황 - 준비 완료",
            "진행상황 - APK 빌드 완료",
            "진행 상황 최종 업데이트 - 성공",
            "진행 상황 최종 업데이트 - 실패",
        ],
    },
}


def _load(name):
    return yaml.safe_load((FLUTTER / name).read_text(encoding="utf-8"))


def _cancel_steps(doc):
    """(job 이름, job, step) 중 cancelled() 를 조건으로 쓰는 스텝. !cancelled() 는 제외."""
    out = []
    for jname, job in doc["jobs"].items():
        for step in job.get("steps", []):
            cond = str(step.get("if", ""))
            if re.search(r"(?<!!)\bcancelled\(\)", cond):
                out.append((jname, job, step))
    return out


@pytest.mark.parametrize("name", CASES)
def test_cancelled_step_exists(name):
    assert _cancel_steps(_load(name)), f"{name}: if: cancelled() 스텝이 없다"


@pytest.mark.parametrize("name", CASES)
def test_cancelled_steps_only_for_repository_dispatch_with_comment(name):
    for jname, _job, step in _cancel_steps(_load(name)):
        cond = str(step["if"])
        assert "github.event_name == 'repository_dispatch'" in cond, (jname, step["name"])
        assert re.search(r"comment_id\s*!=\s*''", cond), (jname, step["name"])


@pytest.mark.parametrize("name", CASES)
def test_cancelled_steps_cover_creator_and_build_jobs(name):
    """댓글을 만든 job 과 그 뒤에 도는 job 이 취소돼도 잡아야 한다."""
    doc = _load(name)
    creator = CASES[name]["creator"]
    covered = {j for j, _, _ in _cancel_steps(doc)}
    assert creator in covered
    downstream = [j for j, job in doc["jobs"].items()
                  if j != creator and any(s.get("id") == "progress_step1"
                                          for s in job.get("steps", []))]
    assert downstream and set(downstream) <= covered


@pytest.mark.parametrize("name", CASES)
def test_cancelled_steps_update_the_comment_without_clobbering_final(name):
    for jname, _job, step in _cancel_steps(_load(name)):
        assert step["uses"].startswith("actions/github-script@")
        script = step["with"]["script"]
        assert "updateComment" in script and "취소" in script
        # 이미 최종 상태(완료/실패)로 쓰인 댓글은 덮어쓰지 않는다
        assert "getComment" in script, (jname, step["name"])
        # 스크립트 소스에 외부 입력을 넣지 않고 env 로 읽는다
        assert "process.env." in script
        assert "client_payload" not in script and "secrets." not in script


@pytest.mark.parametrize("name", CASES)
def test_existing_progress_steps_untouched(name):
    doc = _load(name)
    names = [s.get("name") for j in doc["jobs"].values() for s in j.get("steps", [])]
    for n in CASES[name]["existing"]:
        assert n in names, f"기존 스텝 사라짐: {n}"
    # 기존 최종 스텝은 취소 조건을 갖지 않는다 (성공/실패 로직 그대로)
    for j in doc["jobs"].values():
        for s in j.get("steps", []):
            if s.get("name") in CASES[name]["existing"]:
                assert not re.search(r"(?<!!)\bcancelled\(\)", str(s.get("if", "")))
    finals = [s for j in doc["jobs"].values() for s in j.get("steps", [])
              if s.get("name") == "진행 상황 최종 업데이트 - 성공"]
    assert str(finals[0]["if"]).startswith("success()")


@pytest.mark.parametrize("name", CASES)
def test_cancel_in_progress_still_on(name):
    assert _load(name)["concurrency"]["cancel-in-progress"] is True
