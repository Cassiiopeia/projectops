"""타입별 워크플로우 github-script 스텝 렌더링 (#769 댓글 회귀 검사).

워크플로우 YAML > github-script 스텝 목록 > ${{ }} 를 고정값으로 바꿔 node 로 실행 > 게시 호출·출력.
값 묶음 4가지(variant): 0 성공·참, 1 실패·거짓·빈 값, 2 취소·참, 3 = 0 + 읽기 API 404.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

HELPERS = Path(__file__).resolve().parent
SCRIPTS = HELPERS.parents[1]
ROOT = SCRIPTS.parents[1]
TYPES_DIR = ROOT / ".github" / "workflows" / "project-types"
RUNNER = HELPERS / "github_script_runner.cjs"
MESSAGES = SCRIPTS / "i18n" / "messages.py"
MODULE_NAME = "projectops-messages.cjs"
LOADER_STEP = "Load comment messages"
CATALOG_STEP = "Check out the message catalog"
TYPE_FAMILIES = ("flutter", "spring", "python", "react", "node")
VARIANTS = range(4)

EXPRESSION = re.compile(r"\$\{\{(.*?)\}\}", re.S)
LOADER_PREFIXES = re.compile(r"messages\.py js ((?:[a-z0-9_]+\.\s*(?:\\\s*)?)+)")


def type_workflows() -> list[Path]:
    return sorted(p for family in TYPE_FAMILIES for p in (TYPES_DIR / family).rglob("*.y*ml"))


def value_for(expression: str, variant: int) -> str:
    """${{ 식 }} > 고정값 (식 이름으로 종류 추정)"""
    variant %= 3
    e = expression.strip().lower()
    if "elapsed" in e or "duration" in e:
        # 앞 스텝이 만든 경과 시간 — 언어 중립 값 (한국어 값이면 영문 댓글 검사가 헛짚는다)
        return ["62s", "", "3s"][variant]
    if re.search(r"(_time\b|time\b|_start\b|start\b)", e):
        return "1699999000000"
    if re.search(r"(number|comment_id|run_id|\bport\b|_port)", e):
        return "12"
    if re.search(r"(outcome|conclusion|result|status)", e):
        return ["success", "failure", "cancelled"][variant]
    if re.search(r"(available|enabled|exists|is_|has_|should|skip|found|ok\b|ready|healthy|changed)", e):
        return ["true", "false", "true"][variant]
    if "url" in e:
        return ["https://example.com/x", "", "https://example.com/y"][variant]
    return ["v1", "", "v2"][variant]


def substitute(text, variant: int) -> str:
    return EXPRESSION.sub(lambda m: value_for(m.group(1), variant), str(text))


def loader_prefixes(step) -> list[str] | None:
    match = LOADER_PREFIXES.search(str(step.get("run", "")))
    return match.group(1).replace("\\", " ").split() if match else None


def script_steps(doc) -> list[dict]:
    """github-script 스텝 (잡 안 순서 번호, 합친 env, 그 앞의 문구 모듈 접두사)"""
    steps = []
    workflow_env = doc.get("env") or {}
    for job_id, job in (doc.get("jobs") or {}).items():
        job_env = job.get("env") or {}
        prefixes = None
        index = 0
        for step in job.get("steps") or []:
            if step.get("name") == LOADER_STEP:
                prefixes = loader_prefixes(step) or []
            if "github-script" in str(step.get("uses", "")):
                steps.append({
                    "label": f"{job_id}#{index}",
                    "name": step.get("name"),
                    "script": step["with"]["script"],
                    "env": {**workflow_env, **job_env, **(step.get("env") or {})},
                    "prefixes": prefixes,
                })
                index += 1
    return steps


def _module_dir(prefixes, lang, cache, tmp) -> str:
    key = (lang, tuple(prefixes or ()))
    if key not in cache:
        folder = Path(tmp) / f"m{len(cache)}"
        folder.mkdir()
        if prefixes:
            js = subprocess.run([sys.executable, str(MESSAGES), "js", *prefixes, "--lang", lang],
                                capture_output=True, text=True, check=True).stdout
            (folder / MODULE_NAME).write_text(js, encoding="utf-8")
        cache[key] = str(folder)
    return cache[key]


def visible(result) -> list:
    """사람이 보는 것: 게시 호출의 본문·제목 + 스텝 출력 (다음 댓글에 들어간다)"""
    calls = [[c["api"], c["args"].get("body"), c["args"].get("title")] for c in result["calls"]]
    return [calls, result["outputs"]]


def render(doc, lang: str) -> dict:
    """{label: [variant 별 visible]} — 한 번의 node 실행으로 전부"""
    steps = script_steps(doc)
    tasks, index = [], []
    with tempfile.TemporaryDirectory() as tmp:
        cache = {}
        for step in steps:
            runner_temp = _module_dir(step["prefixes"], lang, cache, tmp)
            for variant in VARIANTS:
                env = {k: substitute(v, variant) for k, v in step["env"].items()}
                env["RUNNER_TEMP"] = runner_temp
                tasks.append({"script": substitute(step["script"], variant), "env": env, "apiFail": variant == 3})
                index.append((step["label"], variant))
        out = subprocess.run(["node", str(RUNNER)], input=json.dumps(tasks), capture_output=True,
                             text=True, check=True).stdout
    rendered: dict = {}
    for (label, _variant), result in zip(index, json.loads(out)):
        rendered.setdefault(label, []).append({"visible": visible(result), "error": result["error"]})
    return rendered


def digest(visible_value) -> str:
    return hashlib.sha256(json.dumps(visible_value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
