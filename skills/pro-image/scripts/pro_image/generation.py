"""생성 1회: 도구 확인 > 실행 폴더 준비 > 도구 실행 > 결과 수거 > 후처리(변환·배경·크기) > 판정"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from . import codex_runner, harness, image_facts, postprocess, provider_runner, providers, settings

# 투명 배경을 못 만드는 도구에 쓰는 기본 키 컬러
DEFAULT_KEY_COLOR = "#00FF00"
# 수거 대기: 도구가 끝난 뒤 새 그림이 생길 때까지 최대 대기 (초), 새 그림이 멈춘 뒤 안정화 대기 (초)
HARVEST_WAIT_SECONDS = 300
HARVEST_SETTLE_SECONDS = 25
HARVEST_POLL_SECONDS = 5

# 모든 프롬프트 뒤에 붙는 규칙 (영어: 이미지 모델 지시 정확도)
COMMON_RULES = """

## Output rules (always apply)
- Create the image with your built-in image generation tool. Never draw it with code (SVG, PIL, canvas, HTML).
- Aspect ratio {aspect} (final size {size}). Keep the main subject whole and inside the frame.
{background_rule}
- If image generation is not available, reply only "IMAGE GENERATION UNAVAILABLE" and create no file.
"""
SAVE_RULE = ("- Save the final file as `./out/{file_name}` (PNG). Code may only resize, crop or convert the generated "
             "image. Write nothing outside this folder. Reply in one line: saved path, size, transparency.")
GENERATE_ONLY_RULE = "- Generate exactly one final image. Do not save, copy or move files; the caller collects it."
ALPHA_NATIVE_RULE = ("- Background must be fully transparent (PNG with alpha). No background, floor shadow or frame. "
                     "If you cannot make real transparency, say so instead of faking it.")
ALPHA_KEYED_RULE = ("- Background: one flat solid {key} color filling everything around the subject. No gradient, "
                    "no shadow, no checkerboard, no texture. Do not use {key} anywhere on the subject.")
OPAQUE_RULE = "- Opaque image that fills the whole frame. No transparency, no checkerboard, no border."


def _aspect(size: tuple[int, int]) -> str:
    from math import gcd
    divisor = gcd(size[0], size[1])
    return f"{size[0] // divisor}:{size[1] // divisor}"


def build_prompt(prompt_text: str, definition: dict, file_name: str, size: tuple[int, int],
                 is_alpha_required: bool, key_color: str) -> str:
    if not is_alpha_required:
        background_rule = OPAQUE_RULE
    elif definition["supports_alpha"]:
        background_rule = ALPHA_NATIVE_RULE
    else:
        background_rule = ALPHA_KEYED_RULE.format(key=key_color)
    rules = COMMON_RULES.format(aspect=_aspect(size), size=f"{size[0]}x{size[1]}", background_rule=background_rule)
    rules += (SAVE_RULE.format(file_name=file_name) if definition["kind"] == "codex" else GENERATE_ONLY_RULE) + "\n"
    if not definition["attaches_references"]:
        rules += ("- Reference images are in ./ref/ and the style guide is ./STYLE.md. Open them with your file viewing "
                  "tool (do not run shell commands) and follow them as the prompt describes.\n")
    return prompt_text.rstrip() + "\n" + rules


def check_ready(definition: dict | None, name: str) -> dict | None:
    """실행 전 확인 > 문제 없으면 None"""
    if definition is None:
        return {"ok": False, "code": "unknown_provider", "known": providers.known_names(),
                "summary": f"No provider named '{name}'", "next": "providers"}
    if definition["kind"] == "agent":
        return {"ok": False, "code": "agent_draws", "provider": name,
                "summary": "This provider is you: draw it yourself (see references/providers.md, claude-vector)"}
    executable = providers.executable_of(definition)
    if not executable:
        return {"ok": False, "code": "provider_missing", "provider": name,
                "summary": f"'{definition['command']}' is not installed", "next": "try the next provider in priority"}
    if definition["kind"] == "codex":
        login = codex_runner.login_facts()
        if settings.is_subscription_required() and login["auth_mode"] != codex_runner.SUBSCRIPTION_AUTH_MODE:
            return {"ok": False, "code": "not_subscription", "provider": name, "login": login,
                    "summary": f"Codex is signed in as '{login['auth_mode']}', not a ChatGPT subscription",
                    "next": "ask the user to run `codex logout` then `codex login` with their ChatGPT account"}
    return None


def _prepare(run_dir: Path, references: list[Path], harness_dir: Path) -> list[Path]:
    (run_dir / "out").mkdir(parents=True, exist_ok=True)
    (run_dir / "ref").mkdir(exist_ok=True)
    style = harness_dir / harness.STYLE_FILE
    if style.is_file():
        shutil.copyfile(style, run_dir / harness.STYLE_FILE)
    copied = []
    for reference in references:
        target = run_dir / "ref" / reference.name
        shutil.copyfile(reference, target)
        copied.append(target)
    return copied


def _harvest(definition: dict, started_at: float) -> Path | None:
    """도구 저장 폴더에서 실행 이후 생긴 그림 > 마지막 것 (도구가 스스로 다시 그리면 최종본)"""
    deadline, newest, last_change = time.time() + HARVEST_WAIT_SECONDS, None, time.time()
    while time.time() < deadline:
        fresh = [path for path in providers.expand_globs(definition["harvest_globs"])
                 if path.stat().st_mtime >= started_at]
        latest = max(fresh, key=lambda path: path.stat().st_mtime) if fresh else None
        if latest != newest:
            newest, last_change = latest, time.time()
        if newest and time.time() - last_change >= HARVEST_SETTLE_SECONDS:
            return newest
        time.sleep(HARVEST_POLL_SECONDS)
    return newest


def generate(provider_name: str, name: str, prompt_text: str, references: list[Path], size: tuple[int, int],
             is_alpha_required: bool, key_color: str | None, harness_dir: Path, run_dir: Path) -> dict:
    definition = providers.invocation(provider_name)
    refusal = check_ready(definition, provider_name)
    if refusal:
        return refusal
    missing = [str(reference) for reference in references if not reference.is_file()]
    if missing:
        return {"ok": False, "code": "reference_missing", "missing": missing, "summary": "Reference image not found"}
    file_name, key = f"{name}.png", key_color or DEFAULT_KEY_COLOR
    copied = _prepare(run_dir, references, harness_dir)
    full_prompt = build_prompt(prompt_text, definition, file_name, size, is_alpha_required, key)
    (run_dir / "prompt.md").write_text(full_prompt, encoding="utf-8")
    command = provider_runner.build_command(providers.executable_of(definition), definition, run_dir,
                                            copied if definition["attaches_references"] else [], file_name,
                                            f"{size[0]}x{size[1]}", full_prompt)
    started_at = time.time() - 1
    result = provider_runner.run_once(command, definition, run_dir, full_prompt)
    raw = run_dir / "out" / file_name
    if not raw.is_file() and definition["harvest_globs"]:
        harvested = _harvest(definition, started_at)
        if harvested:
            raw = run_dir / "out" / f"raw_{harvested.name}"
            shutil.copyfile(harvested, raw)
            result["harvested_from"] = str(harvested)
    return _judge(definition, name, run_dir, raw, size, is_alpha_required,
                  None if definition["supports_alpha"] else key, result)


def _judge(definition: dict, name: str, run_dir: Path, raw: Path, size: tuple[int, int], is_alpha_required: bool,
           key_color: str | None, result: dict) -> dict:
    """결과 > code (ok · spec_mismatch · timeout · image_unavailable · no_image · postprocess_failed)"""
    base = {"provider": definition["name"], "name": name, "run_dir": str(run_dir),
            "prompt_file": str(run_dir / "prompt.md"), **result}
    if not raw.is_file():
        if result["is_timed_out"]:
            return {**base, "ok": False, "code": "timeout", "summary": "The provider did not finish in time",
                    "next": "run again, or try the next provider in priority"}
        if result["reported_unavailable"]:
            return {**base, "ok": False, "code": "image_unavailable", "summary": "The provider cannot generate images",
                    "next": "free plans hit rate limits (429): retry once after 1-2 minutes, then the next provider"}
        return {**base, "ok": False, "code": "no_image", "summary": "No image came back",
                "next": "read log_tail; fix the prompt or try the next provider"}
    final_path = run_dir / "out" / f"{name}.final.png"
    try:
        finished = postprocess.finish(raw, final_path, size, is_alpha_required, key_color)
    except (RuntimeError, OSError, ValueError) as error:
        return {**base, "ok": False, "code": "postprocess_failed", "raw_image": str(raw), "summary": str(error)}
    if not finished["ok"]:
        return {**base, **finished, "raw_image": str(raw)}
    facts = image_facts.read_facts(final_path)
    problems = image_facts.find_problems(facts, size, is_alpha_required)
    if result["used_image_model"] is False:
        problems.append("log does not show the image model output; it may have been drawn with code")
    return {**base, "ok": True, "code": "spec_mismatch" if problems else "ok", "image": facts,
            "raw_image": str(raw), "steps": finished["steps"], "problems": problems,
            "summary": f"{final_path.name} {facts.get('width')}x{facts.get('height')}"
                       + (f", {len(problems)} problem(s)" if problems else ", matches the request"),
            "next": "open image.path with Read, check it against your brief, then show only the image to the user"}
