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
# 재인코딩: 프레임 공통 팔레트 1개 (프레임마다 팔레트가 달라 정지 영역까지 매 프레임 다시 쓰이는 것 방지)
SHARED_PALETTE_COLORS = 255
PALETTE_SAMPLE_FRAME_STEP = 3
# 언어별 문구: 시안 내용과 녹화 단계에서 함께 씀
TEXT_BY_LANGUAGE = {
    "en": {"title": "Order flow: customer and kitchen", "subtitle": "Press + and Send on the left. The kitchen screen updates.",
           "customer": "Customer app", "kitchen": "Kitchen display", "greeting": "Good morning, Mina",
           "menuTitle": "What's your order?", "categories": ["Coffee", "Bakery", "Juice"],
           "menu": ["Oat latte", "Sesame bagel", "Fresh orange"],
           "notes": ["Double shot", "Cream cheese", "Squeezed to order"],
           "prices": [450, 380, 520], "currency": "${n}", "currencyIsWhole": False, "itemsLabel": "{n} items",
           "send": "Place order", "sent": "Order sent", "sentNote": "#{n} is in the kitchen",
           "kitchenPlace": "Bloom Coffee · Bar 1", "ordersTitle": "Orders", "liveLabel": "Live",
           "tabNew": "New", "tabCooking": "Making", "tabDone": "Done", "newBadge": "NEW", "ticketMeta": "Pickup · just now",
           "start": "Start making", "empty": "No orders yet", "emptyNote": "New orders appear here instantly",
           "stepsTitle": "Try this", "steps": ["Add items", "Place the order"], "shared": "shared state"},
    "ko": {"title": "주문 흐름: 손님과 주방", "subtitle": "왼쪽에서 +와 주문하기를 누르면 주방 화면이 바뀝니다.",
           "customer": "손님 앱", "kitchen": "주방 화면", "greeting": "좋은 아침이에요, 민아 님",
           "menuTitle": "무엇을 드릴까요?", "categories": ["커피", "베이커리", "주스"],
           "menu": ["오트 라떼", "참깨 베이글", "생오렌지 주스"],
           "notes": ["더블 샷", "크림치즈", "주문 즉시 착즙"],
           "prices": [4500, 3800, 5200], "currency": "{n}원", "currencyIsWhole": True, "itemsLabel": "{n}개 담음",
           "send": "주문하기", "sent": "주문했어요", "sentNote": "#{n} 주방에 전달됨",
           "kitchenPlace": "블룸 커피 · 1번 바", "ordersTitle": "주문", "liveLabel": "실시간",
           "tabNew": "신규", "tabCooking": "제조 중", "tabDone": "완료", "newBadge": "NEW", "ticketMeta": "포장 · 방금",
           "start": "제조 시작", "empty": "아직 주문이 없어요", "emptyNote": "새 주문이 바로 여기에 떠요",
           "stepsTitle": "따라 해 보기", "steps": ["메뉴 담기", "주문 보내기"], "shared": "상태 공유"},
}
# 녹화 단계: 라떼 2잔 + 베이글 담기 > 주문 > 주방 티켓 도착 감상
RECORD_STEPS = [
    {"action": "wait", "ms": 900},
    {"action": "click", "selector": "[data-screen='customer'] .add[data-index='0']", "ms": 650},
    {"action": "click", "selector": "[data-screen='customer'] .add[data-index='1']", "ms": 650},
    {"action": "click", "selector": "[data-screen='customer'] .add[data-index='0']", "ms": 900},
    {"action": "click", "selector": "[data-screen='customer'] .send", "ms": 2400},
]


def run_cli(root: Path, *args: str) -> dict:
    output = subprocess.run([sys.executable, str(CLI_PATH), *args, "--root", str(root)], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    result = json.loads(output.stdout)
    if not result.get("ok"):
        raise SystemExit(f"{args[0]} failed: {result}")
    return result


def reencode_with_shared_palette(gif_path: Path) -> None:
    """프레임 표본 > 공통 팔레트 > 디더링 없이 전 프레임 재양자화 > 바뀐 영역만 저장 (용량 축소)"""
    from PIL import Image, ImageSequence

    with Image.open(gif_path) as source:
        frames = [frame.convert("RGB") for frame in ImageSequence.Iterator(source)]
        durations = [frame.info.get("duration", 100) for frame in ImageSequence.Iterator(source)]
    # 팔레트 표본: 일정 간격 프레임 + 마지막 프레임을 세로로 이어 붙임
    samples = frames[::PALETTE_SAMPLE_FRAME_STEP] + [frames[-1]]
    sheet = Image.new("RGB", (frames[0].width, frames[0].height * len(samples)))
    for index, frame in enumerate(samples):
        sheet.paste(frame, (0, frames[0].height * index))
    palette = sheet.quantize(colors=SHARED_PALETTE_COLORS, method=Image.Quantize.FASTOCTREE)
    quantized = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    quantized[0].save(gif_path, save_all=True, append_images=quantized[1:], duration=durations, loop=0, optimize=True, disposal=1)


def ensure_pillow() -> None:
    """Pillow 없으면 pro-launch 가상환경 파이썬으로 같은 인자 재실행"""
    try:
        import PIL  # noqa: F401
        return
    except ImportError:
        pass
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from common.state import venv_python

    interpreter = venv_python()
    if interpreter is None or Path(sys.executable).resolve() == Path(interpreter).resolve():
        raise SystemExit("Pillow missing: run `launch_cli.py web setup` (pro-launch) first")
    raise SystemExit(subprocess.run([str(interpreter), __file__, *sys.argv[1:]]).returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description="Record the pro-ui-design README GIF")
    parser.add_argument("--lang", choices=sorted(TEXT_BY_LANGUAGE), required=True)
    language = parser.parse_args().lang
    ensure_pillow()
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
        reencode_with_shared_palette(target)
        print(f"wrote {target} ({target.stat().st_size} bytes)")
    finally:
        run_cli(workspace, "stop", "--all")
        shutil.rmtree(workspace, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
