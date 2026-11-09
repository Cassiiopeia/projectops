"""크기 조절 (표준 라이브러리): RGBA > 가로·세로 분리 삼각 필터, 알파 곱한 상태로 계산 (가장자리 번짐 방지)
Pillow 가 없을 때의 대체 경로 (Windows 기본 Python 포함), 축소 시 필터 폭을 넓혀 계단 현상 방지
"""
from __future__ import annotations


def _weights(source_length: int, target_length: int) -> list[tuple[int, list[float]]]:
    """대상 픽셀별 (시작 원본 인덱스, 가중치 목록)"""
    scale = source_length / target_length
    support = max(1.0, scale)
    rows = []
    for target_index in range(target_length):
        center = (target_index + 0.5) * scale
        start = max(0, int(center - support))
        stop = min(source_length, int(center + support) + 1)
        weights = [max(0.0, 1.0 - abs((index + 0.5 - center) / support)) for index in range(start, stop)]
        total = sum(weights) or 1.0
        rows.append((start, [weight / total for weight in weights]))
    return rows


def _premultiply(rgba: bytearray) -> list[float]:
    values = [0.0] * len(rgba)
    for offset in range(0, len(rgba), 4):
        alpha = rgba[offset + 3] / 255
        values[offset] = rgba[offset] * alpha
        values[offset + 1] = rgba[offset + 1] * alpha
        values[offset + 2] = rgba[offset + 2] * alpha
        values[offset + 3] = rgba[offset + 3]
    return values


def _pass(values: list[float], width: int, height: int, new_length: int, is_horizontal: bool) -> list[float]:
    plan = _weights(width if is_horizontal else height, new_length)
    out_width, out_height = (new_length, height) if is_horizontal else (width, new_length)
    result = [0.0] * (out_width * out_height * 4)
    for row in range(out_height):
        for column in range(out_width):
            start, weights = plan[column] if is_horizontal else plan[row]
            sums = [0.0, 0.0, 0.0, 0.0]
            for step, weight in enumerate(weights):
                source = (row * width + start + step) * 4 if is_horizontal else ((start + step) * width + column) * 4
                sums[0] += values[source] * weight
                sums[1] += values[source + 1] * weight
                sums[2] += values[source + 2] * weight
                sums[3] += values[source + 3] * weight
            target = (row * out_width + column) * 4
            result[target:target + 4] = sums
    return result


def resize(width: int, height: int, rgba: bytearray, new_width: int, new_height: int) -> bytearray:
    values = _premultiply(rgba)
    values = _pass(values, width, height, new_width, True)
    values = _pass(values, new_width, height, new_height, False)
    output = bytearray(len(values))
    for offset in range(0, len(values), 4):
        alpha = values[offset + 3]
        factor = 255 / alpha if alpha > 0 else 0
        for channel in range(3):
            output[offset + channel] = max(0, min(255, round(values[offset + channel] * factor)))
        output[offset + 3] = max(0, min(255, round(alpha)))
    return output


def crop(width: int, rgba: bytearray, left: int, top: int, crop_width: int, crop_height: int) -> bytearray:
    stride = width * 4
    return bytearray(b"".join(bytes(rgba[(top + row) * stride + left * 4:(top + row) * stride + (left + crop_width) * 4])
                              for row in range(crop_height)))


def pad(width: int, height: int, rgba: bytearray, canvas_width: int, canvas_height: int) -> bytearray:
    """가운데 배치 + 투명 여백"""
    canvas = bytearray(canvas_width * canvas_height * 4)
    left, top = (canvas_width - width) // 2, (canvas_height - height) // 2
    for row in range(height):
        start = ((top + row) * canvas_width + left) * 4
        canvas[start:start + width * 4] = rgba[row * width * 4:(row + 1) * width * 4]
    return canvas
