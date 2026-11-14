"""Background removal: detect background from border color > make transparent > remove edge semi-transparency and color bleed
2 modes: flood only background connected to the border (white bg, fake checkerboard), global every key-color pixel (green/pink chroma key)
"""
from __future__ import annotations

from collections import Counter, deque

# Color distance counted as background (RGB Euclidean, 0-441)
DEFAULT_TOLERANCE = 48
# Semi-transparent band: tolerance to tolerance*SOFT_BAND_RATIO gets alpha proportional to distance
SOFT_BAND_RATIO = 2.0
# 3 key-color candidates (green, pink, blue): pick the one farthest from the subject colors
KEY_COLOR_CANDIDATES = ("#00FF00", "#FF00FF", "#0000FF")
# Lower bound of the denominator when restoring edge color (alpha share, 0-1)
UNMIX_MIN_SHARE = 0.6
# Minimum tolerance for a key color (high-saturation background)
CHROMA_TOLERANCE = 110
# Key-color bleed removal range: how many pixels outside the transparent area
EDGE_RING_PIXELS = 2
# Border color bucket size (values quantized to this size to find dominant colors)
BORDER_COLOR_BUCKET = 16
# Dominant color candidates: only colors taking at least this share of border pixels
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
    """1-2 dominant border colors (fake checkerboard gives light gray and white)"""
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
    """Distance from background color > alpha (near 0, proportional in the soft band, far 255)"""
    nearest = min(_distance(color, key) for key in keys)
    if nearest <= tolerance:
        return 0
    soft_limit = tolerance * SOFT_BAND_RATIO
    return 255 if nearest >= soft_limit else round(255 * (nearest - tolerance) / (soft_limit - tolerance))


def _despill(rgba: bytearray, index: int, key: tuple[int, int, int]) -> None:
    # Key-color bleed removal: lower the key's strong channels (green 1, pink 2) to the max of the weak channels
    offset = index * 4
    strong = [channel for channel in range(3) if key[channel] >= 128]
    weak = [channel for channel in range(3) if key[channel] < 128]
    if not strong or not weak:
        return
    ceiling = max(rgba[offset + channel] for channel in weak)
    for channel in strong:
        rgba[offset + channel] = min(rgba[offset + channel], ceiling)


def _unmix(rgba: bytearray, index: int, key: tuple[int, int, int], alpha: int) -> None:
    # Semi-transparent pixel = subject x a + background x (1-a) > restore subject color (removes background tint on edges)
    # Very low alpha makes division amplify noise into off-color fringes > denominator floor UNMIX_MIN_SHARE
    offset, share = index * 4, max(alpha / 255, UNMIX_MIN_SHARE)
    for channel in range(3):
        restored = (rgba[offset + channel] - key[channel] * (1 - share)) / share
        rgba[offset + channel] = max(0, min(255, round(restored)))


def pick_key_color(colors: list[tuple[int, int, int]]) -> str:
    """Colors used in the subject > key color farthest from all of them (green, pink or blue)"""
    if not colors:
        return KEY_COLOR_CANDIDATES[0]
    def nearest_distance(candidate: str) -> float:
        key = parse_hex_color(candidate)
        return min(_distance(key, color) for color in colors)
    return max(KEY_COLOR_CANDIDATES, key=nearest_distance)


def dominant_colors(width: int, height: int, rgba: bytearray, limit: int = 8) -> list[tuple[int, int, int]]:
    """Dominant colors of opaque pixels (quantized, by frequency; used to pick a key color from references)"""
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
    # High-saturation key (green, pink, etc.): far from the subject, so widen tolerance and remove bleed
    return any(max(key) - min(key) > 128 for key in keys)


def _edge_ring(alpha_by_index: dict, width: int, height: int) -> set[int]:
    """Transparent/semi-transparent pixels + EDGE_RING_PIXELS rings of neighbors (outline where key color bleeds)"""
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
    """Adjust alpha of background pixels > {transparent count, semi-transparent count} (mutates rgba)"""
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
            # Semi-transparent pixel is the subject edge > stop here
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
