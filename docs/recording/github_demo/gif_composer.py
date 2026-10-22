"""캡처 프레임 > GIF: 단계 설명 바, 경과 타이머, 강조 테두리 합성 후 ffmpeg 로 조립"""
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# 화면 크기 (기존 데모와 동일)
FRAME_WIDTH_PIXELS = 860
FRAME_HEIGHT_PIXELS = 600
CAPTION_HEIGHT_PIXELS = 34
ACCENT_COLOR = (99, 102, 241)
CAPTION_BACKGROUND = (30, 32, 48, 235)
TIMER_BACKGROUND = (22, 27, 34, 235)
TIMER_TEXT_COLOR = (126, 231, 135)

# 언어별 글꼴 후보 (macOS 기본 > Linux 대체)
FONT_CANDIDATES = {
    "en": ["/System/Library/Fonts/Helvetica.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "ko": ["/System/Library/Fonts/AppleSDGothicNeo.ttc", "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"],
}
MONO_FONT_CANDIDATES = ["/System/Library/Fonts/Menlo.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"]


def load_font(candidates: list[str], size: int, index: int = 0):
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size, index=index)
    return ImageFont.load_default()


@dataclass
class CapturedFrame:
    """캡처 한 장: 화면, 단계, 경과 초, 재생 시간, 강조 영역(x, y, w, h)"""
    screenshot_path: Path
    step_number: int
    elapsed_seconds: float
    display_seconds: float
    highlight_box: tuple | None = None
    is_timer_visible: bool = True


@dataclass
class GifComposer:
    language: str
    captions: dict
    work_dir: Path
    frames: list = field(default_factory=list)

    def add(self, frame: CapturedFrame):
        self.frames.append(frame)

    def _render(self, frame: CapturedFrame, output_path: Path):
        image = Image.open(frame.screenshot_path).convert("RGBA").resize((FRAME_WIDTH_PIXELS, FRAME_HEIGHT_PIXELS))
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        caption_font = load_font(FONT_CANDIDATES[self.language], 15, index=1 if self.language == "en" else 6)
        timer_font = load_font(MONO_FONT_CANDIDATES, 15, index=1)

        # 강조 테두리 (요소 위치)
        if frame.highlight_box:
            x, y, w, h = frame.highlight_box
            draw.rounded_rectangle((x - 3, y - 3, x + w + 3, y + h + 3), radius=8, outline=ACCENT_COLOR + (255,), width=3)

        # 하단 설명 바: 번호 원 + 문구
        top = FRAME_HEIGHT_PIXELS - CAPTION_HEIGHT_PIXELS
        draw.rectangle((0, top, FRAME_WIDTH_PIXELS, FRAME_HEIGHT_PIXELS), fill=CAPTION_BACKGROUND)
        draw.line((0, top, FRAME_WIDTH_PIXELS, top), fill=ACCENT_COLOR + (255,), width=2)
        center_y = top + CAPTION_HEIGHT_PIXELS // 2
        draw.ellipse((12, center_y - 11, 34, center_y + 11), fill=ACCENT_COLOR + (255,))
        draw.text((23, center_y), str(frame.step_number), font=caption_font, fill="white", anchor="mm")
        draw.text((44, center_y), self.captions[frame.step_number], font=caption_font, fill="white", anchor="lm")

        # 우상단 경과 타이머 (실제 경과 시간)
        if frame.is_timer_visible:
            minutes, seconds = divmod(int(frame.elapsed_seconds), 60)
            left = FRAME_WIDTH_PIXELS - 112
            draw.rounded_rectangle((left, 8, FRAME_WIDTH_PIXELS - 10, 38), radius=15, fill=TIMER_BACKGROUND)
            # 시계 아이콘 (글꼴에 ⏱ 없음 > 직접 그림)
            draw.ellipse((left + 12, 16, left + 26, 30), outline=TIMER_TEXT_COLOR, width=2)
            draw.line((left + 19, 23, left + 19, 19), fill=TIMER_TEXT_COLOR, width=2)
            draw.line((left + 19, 23, left + 22, 23), fill=TIMER_TEXT_COLOR, width=2)
            draw.text((left + 62, 23), f"{minutes:02d}:{seconds:02d}", font=timer_font, fill=TIMER_TEXT_COLOR, anchor="mm")

        Image.alpha_composite(image, overlay).convert("RGB").save(output_path)

    def write_gif(self, output_path: Path):
        """프레임 렌더 > ffmpeg concat(프레임별 재생 시간) > 팔레트 생성 > GIF"""
        render_dir = self.work_dir / "rendered"
        render_dir.mkdir(parents=True, exist_ok=True)
        concat_lines = []
        for index, frame in enumerate(self.frames):
            rendered_path = render_dir / f"{index:04d}.png"
            self._render(frame, rendered_path)
            concat_lines += [f"file '{rendered_path}'", f"duration {frame.display_seconds:.2f}"]
        # concat 은 마지막 duration 적용에 마지막 파일 한 번 더 필요
        concat_lines.append(f"file '{render_dir / f'{len(self.frames) - 1:04d}.png'}'")
        concat_path = self.work_dir / "frames.txt"
        concat_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
        palette_filter = "fps=10,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_path),
                        "-vf", palette_filter, str(output_path)], check=True)
