"""README 데모 GIF: pro-ui-design 연결 프로토타입을 작업 트리 CLI 로 녹화
실행: python docs/recording/ui_design_demo/record_ui_design.py --lang en|ko
결과: docs/images/feature-ui-design.gif (en), feature-ui-design.ko.gif (ko)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CLI_PATH = REPO_ROOT / "skills/pro-ui-design/scripts/ui_design_cli.py"
TEMPLATE_PATH = Path(__file__).with_name("linked.html")
GIF_MAX_WIDTH = 900
# 언어별 문구: 시안 내용과 녹화 단계에서 함께 씀
TEXT_BY_LANGUAGE = {
    "en": {"title": "Order flow: customer and kitchen", "subtitle": "Press + and Send on the left. The kitchen screen updates.",
           "customer": "Customer", "kitchen": "Kitchen", "menuTitle": "Menu", "ordersTitle": "Orders",
           "menu": ["Latte", "Bagel", "Orange juice"], "price": "4.50", "send": "Send order",
           "sent": "Order sent", "empty": "No orders yet", "stepsTitle": "Try this",
           "steps": ["Add items", "Send the order"]},
    "ko": {"title": "주문 흐름: 손님과 주방", "subtitle": "왼쪽에서 +와 주문하기를 누르면 주방 화면이 바뀝니다.",
           "customer": "손님", "kitchen": "주방", "menuTitle": "메뉴", "ordersTitle": "주문",
           "menu": ["라떼", "베이글", "오렌지 주스"], "price": "4,500원", "send": "주문하기",
           "sent": "주문했어요", "empty": "아직 주문이 없어요", "stepsTitle": "따라 해 보기",
           "steps": ["메뉴 담기", "주문 보내기"]},
}
RECORD_STEPS = [
    {"action": "wait", "ms": 700},
    {"action": "click", "selector": "[data-screen='customer'] .add[data-index='0']", "ms": 500},
    {"action": "click", "selector": "[data-screen='customer'] .add[data-index='1']", "ms": 600},
    {"action": "click", "selector": "[data-screen='customer'] .send", "ms": 1600},
]


def run_cli(root: Path, *args: str) -> dict:
    output = subprocess.run([sys.executable, str(CLI_PATH), *args, "--root", str(root)], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    result = json.loads(output.stdout)
    if not result.get("ok"):
        raise SystemExit(f"{args[0]} failed: {result}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Record the pro-ui-design README GIF")
    parser.add_argument("--lang", choices=sorted(TEXT_BY_LANGUAGE), required=True)
    language = parser.parse_args().lang
    text = TEXT_BY_LANGUAGE[language]
    workspace = Path(tempfile.mkdtemp(prefix="ui-design-demo-"))
    subprocess.run(["git", "init", "-q", str(workspace)], check=True)
    try:
        session = run_cli(workspace, "start", "--title", "readme demo")
        html = TEMPLATE_PATH.read_text(encoding="utf-8")
        for key in ("title", "subtitle"):
            html = html.replace("{{" + key + "}}", text[key])
        html = html.replace("{{text}}", json.dumps(text, ensure_ascii=False))
        (Path(session["screens_dir"]) / "linked.html").write_text(html, encoding="utf-8")
        steps_file = workspace / "steps.json"
        steps_file.write_text(json.dumps(RECORD_STEPS), encoding="utf-8")
        captured = run_cli(workspace, "capture", "--gif", "--screen", "linked.html", "--steps", str(steps_file),
                           "--max-width", str(GIF_MAX_WIDTH))
        suffix = "" if language == "en" else f".{language}"
        target = REPO_ROOT / "docs/images" / f"feature-ui-design{suffix}.gif"
        shutil.copyfile(captured["files"][0]["path"], target)
        print(f"wrote {target} ({target.stat().st_size} bytes)")
    finally:
        run_cli(workspace, "stop", "--all")
        shutil.rmtree(workspace, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
