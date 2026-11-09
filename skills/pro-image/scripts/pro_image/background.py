"""배경 제거: 테두리 색으로 배경 판별 > 투명화 > 가장자리 반투명·색 번짐 제거
모드 2개: flood 테두리와 이어진 배경만 (흰 배경·가짜 체크무늬), global 키 컬러 전부 (초록·분홍 크로마키)
"""
from __future__ import annotations

from collections import Counter, deque

# 배경으로 볼 색 거리 (RGB 유클리드, 0~441)
DEFAULT_TOLERANCE = 48
# 반투명 처리 폭: tolerance ~ tolerance*SOFT_BAND_RATIO 구간은 거리 비례 알파
SOFT_BAND_RATIO = 2.0
# 키 컬러 후보 3개 (초록, 분홍, 파랑): 대상 색과 가장 먼 것을 고름
KEY_COLOR_CANDIDATES = ("#00FF00", "#FF00FF", "#0000FF")
# 가장자리 색 복원 분모 하한 (알파 비율, 0~1)
UNMIX_MIN_SHARE = 0.6
# 키 컬러(채도 높은 배경)일 때 최소 허용 거리
CHROMA_TOLERANCE = 110
# 키 컬러 번짐 제거 범위: 투명 영역 바깥 몇 픽셀까지
EDGE_RING_PIXELS = 2
# 테두리 색 묶음 단위 (값을 이 크기로 양자화해 대표색 계산)
BORDER_COLOR_BUCKET = 16
# 대표색 후보: 테두리 픽셀 중 이 비율 이상 차지한 색만
BORDER_COLOR_MIN_SHARE = 0.08


def parse_hex_color(text: str) -> tuple[int, int, int]:
    value = text.lstrip("#")
    if len(value) != 6:
        raise ValueError("key color must look like #00FF00")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _distance(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    return ((first[0] - second[0]) ** 2 + (first[1] - second[1]) ** 2 + (first[2] - second[2]) ** 2) ** 0.5


def _pixel(rgba: bytearray, index: int) -> tuple[int, int, int]:
    offset = index * 4
    return rgba[offset], rgba[offset + 1], rgba[offset + 2]


def _border_indexes(width: int, height: int) -> list[int]:
    top = list(range(width))
    bottom = [(height - 1) * width + column for column in range(width)]
    sides = [row * width for row in range(1, height - 1)] + [row * width + width - 1 for row in range(1, height - 1)]
    return top + bottom + sides


def detect_keys(width: int, height: int, rgba: bytearray) -> list[tuple[int, int, int]]:
    """테두리 대표색 1~2개 (가짜 체크무늬면 밝은 회색·흰색 2개)"""
    buckets = Counter()
    sums: dict[tuple, list[int]] = {}
    for index in _border_indexes(width, height):
        color = _pixel(rgba, index)
        bucket = tuple(channel // BORDER_COLOR_BUCKET for channel in color)
        buckets[bucket] += 1
        total = sums.setdefault(bucket, [0, 0, 0])
        for channel in range(3):
            total[channel] += color[channel]
    border_count = sum(buckets.values())
    keys = []
    for bucket, count in buckets.most_common(2):
        if count / border_count >= BORDER_COLOR_MIN_SHARE:
            keys.append(tuple(round(value / count) for value in sums[bucket]))
    return keys


def _alpha_for(color: tuple[int, int, int], keys: list[tuple[int, int, int]], tolerance: float) -> int:
    """배경색과의 거리 > 알파 (가까우면 0, 반투명 구간은 비례, 멀면 255)"""
    nearest = min(_distance(color, key) for key in keys)
    if nearest <= tolerance:
        return 0
    soft_limit = tolerance * SOFT_BAND_RATIO
    return 255 if nearest >= soft_limit else round(255 * (nearest - tolerance) / (soft_limit - tolerance))


def _despill(rgba: bytearray, index: int, key: tuple[int, int, int]) -> None:
    # 키 컬러 번짐 제거: 키에서 강한 채널(초록 1개, 분홍 2개)을 약한 채널 최대값으로 낮춤
    offset = index * 4
    strong = [channel for channel in range(3) if key[channel] >= 128]
    weak = [channel for channel in range(3) if key[channel] < 128]
    if not strong or not weak:
        return
    ceiling = max(rgba[offset + channel] for channel in weak)
    for channel in strong:
        rgba[offset + channel] = min(rgba[offset + channel], ceiling)


def _unmix(rgba: bytearray, index: int, key: tuple[int, int, int], alpha: int) -> None:
    # 반투명 픽셀 = 물체색 x a + 배경색 x (1-a) > 물체색 복원 (가장자리 배경색 비침 제거)
    # 알파가 아주 낮으면 나눗셈이 잡음을 키워 다른 색 테두리가 생김 > 분모 하한 UNMIX_MIN_SHARE
    offset, share = index * 4, max(alpha / 255, UNMIX_MIN_SHARE)
    for channel in range(3):
        restored = (rgba[offset + channel] - key[channel] * (1 - share)) / share
        rgba[offset + channel] = max(0, min(255, round(restored)))


def pick_key_color(colors: list[tuple[int, int, int]]) -> str:
    """대상에 쓰인 색들 > 그중 어느 색과도 가장 먼 키 컬러 (초록·분홍·파랑 중)"""
    if not colors:
        return KEY_COLOR_CANDIDATES[0]
    def nearest_distance(candidate: str) -> float:
        key = parse_hex_color(candidate)
        return min(_distance(key, color) for color in colors)
    return max(KEY_COLOR_CANDIDATES, key=nearest_distance)


def dominant_colors(width: int, height: int, rgba: bytearray, limit: int = 8) -> list[tuple[int, int, int]]:
    """불투명 픽셀의 대표색 (양자화 후 빈도순, 참조 그림에서 키 컬러 고를 때 사용)"""
    buckets = Counter()
    step = max(1, (width * height) // 40000)
    for index in range(0, width * height, step):
        if rgba[index * 4 + 3] < 200:
            continue
        buckets[tuple(channel // 32 * 32 + 16 for channel in _pixel(rgba, index))] += 1
    return [color for color, _ in buckets.most_common(limit)]


def _neighbors(index: int, width: int, height: int):
    row, column = divmod(index, width)
    if column > 0:
        yield index - 1
    if column < width - 1:
        yield index + 1
    if row > 0:
        yield index - width
    if row < height - 1:
        yield index + width


def is_chroma_key(keys: list[tuple[int, int, int]]) -> bool:
    # 채도 높은 키(초록·분홍 등): 물체와 멀어 허용 범위를 넓히고 번짐 제거
    return any(max(key) - min(key) > 128 for key in keys)


def _edge_ring(alpha_by_index: dict, width: int, height: int) -> set[int]:
    """투명·반투명 픽셀 + 그 바깥 EDGE_RING_PIXELS 겹 이웃 (키 컬러가 번지는 윤곽선)"""
    ring = {index for index, alpha in alpha_by_index.items() if alpha > 0}
    frontier = {index for index, alpha in alpha_by_index.items() if alpha == 0}
    seen = set(alpha_by_index)
    for _ in range(EDGE_RING_PIXELS):
        frontier = {neighbor for index in frontier for neighbor in _neighbors(index, width, height)
                    if neighbor not in seen}
        seen |= frontier
        ring |= frontier
    return ring


def remove(width: int, height: int, rgba: bytearray, keys: list[tuple[int, int, int]], tolerance: float,
           mode: str) -> dict:
    """배경 픽셀 알파 조정 > {투명 픽셀 수, 반투명 픽셀 수} (rgba 를 직접 수정)"""
    total = width * height
    if is_chroma_key(keys):
        tolerance = max(tolerance, CHROMA_TOLERANCE)
    alpha_by_index = {}
    if mode == "global":
        for index in range(total):
            alpha = _alpha_for(_pixel(rgba, index), keys, tolerance)
            if alpha < 255:
                alpha_by_index[index] = alpha
    else:
        queue = deque(index for index in _border_indexes(width, height))
        visited = set(queue)
        while queue:
            index = queue.popleft()
            alpha = _alpha_for(_pixel(rgba, index), keys, tolerance)
            if alpha == 255:
                continue
            alpha_by_index[index] = alpha
            # 반투명 픽셀은 물체 가장자리 > 더 들어가지 않음
            if alpha > 0:
                continue
            for neighbor in _neighbors(index, width, height):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
    for index, alpha in alpha_by_index.items():
        rgba[index * 4 + 3] = min(rgba[index * 4 + 3], alpha)
        if 0 < alpha < 255:
            _unmix(rgba, index, keys[0], alpha)
    if is_chroma_key(keys):
        for index in _edge_ring(alpha_by_index, width, height):
            _despill(rgba, index, keys[0])
    transparent = sum(1 for alpha in alpha_by_index.values() if alpha == 0)
    return {"transparent_pixels": transparent, "soft_edge_pixels": len(alpha_by_index) - transparent,
            "transparent_share": round(transparent / total, 3)}
