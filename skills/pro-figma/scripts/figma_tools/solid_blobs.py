"""한쪽에만 있는 색면: 다른 픽셀 덩어리 중 글자가 아니라 색면이 다른 것

글자 뭉개짐은 양쪽 다 가장자리가 촘촘하다. 한쪽에만 있는 그림 조각은 양쪽이 매끈하고 색만 다르다.
1px 밀린 실루엣은 상자 안이 거의 비어(채움률 ~0.1) 걸러진다.
수치가 1.66%까지 내려간 화면에서도 앱에만 남은 에셋 조각(부리 13px)을 이것으로 찾았다 (elum).
"""
from __future__ import annotations

# 가장자리 밀도 상한: 이보다 촘촘하면 글자로 봄
MAX_EDGE_DENSITY = 0.10
# 시안 색 <-> 렌더 색 평균 차 하한
MIN_COLOR_GAP = 40
# 덩어리가 상자를 채운 비율 하한
MIN_FILL_RATIO = 0.30


def _edge_density(image, threshold: int) -> float:
    """가로 이웃과 크게 다른 픽셀 비율 (글자면 높고 색면이면 0 근처)"""
    if image.shape[1] < 2:
        return 0.0
    import numpy as np
    neighbor_delta = np.abs(image[:, 1:].astype(np.int16) - image[:, :-1]).max(axis=2)
    return float((neighbor_delta > threshold).mean())


def connected_components(mask, min_area: int) -> list[dict]:
    """다른 픽셀을 연결 덩어리(4-이웃)로 (행 구간 > 위 행과 겹치면 union-find)

    diff 의 행 단위 상자는 한 행의 글자와 그림을 한 상자로 합쳐, 색면인지 글자인지 못 가린다.
    """
    import numpy as np
    parent: dict[int, int] = {}

    def find(label: int) -> int:
        while parent[label] != label:
            parent[label] = parent[parent[label]]
            label = parent[label]
        return label

    runs, previous_runs = [], []
    for y in range(mask.shape[0]):
        xs = np.nonzero(mask[y])[0]
        current_runs = []
        if len(xs):
            # 연속 구간 나누기
            breaks = np.nonzero(np.diff(xs) != 1)[0]
            starts = np.concatenate(([0], breaks + 1))
            ends = np.concatenate((breaks, [len(xs) - 1]))
            for start, end in zip(starts, ends):
                x0, x1 = int(xs[start]), int(xs[end])
                label = len(runs)
                parent[label] = label
                for previous_label, previous_x0, previous_x1 in previous_runs:
                    if previous_x0 <= x1 and x0 <= previous_x1:
                        root_a, root_b = find(previous_label), find(label)
                        if root_a != root_b:
                            parent[root_b] = root_a
                runs.append((label, y, x0, x1))
                current_runs.append((label, x0, x1))
        previous_runs = current_runs

    boxes: dict[int, list[int]] = {}
    for label, y, x0, x1 in runs:
        root = find(label)
        box = boxes.setdefault(root, [x0, y, x1, y, 0])
        box[0], box[2], box[3] = min(box[0], x0), max(box[2], x1), y
        box[4] += x1 - x0 + 1
    return [{"x": b[0], "y": b[1], "w": b[2] - b[0] + 1, "h": b[3] - b[1] + 1}
            for b in boxes.values() if b[4] >= min_area]


def find_solid_blobs(design, render, mask, min_area: int, threshold: int) -> list[dict]:
    """다른 픽셀 연결 덩어리 > 색면 차이만 (넓은 것부터)"""
    blobs = []
    for cluster in connected_components(mask, min_area):
        x0, y0 = cluster["x"], cluster["y"]
        x1, y1 = x0 + cluster["w"], y0 + cluster["h"]
        design_crop, render_crop = design[y0:y1, x0:x1], render[y0:y1, x0:x1]
        inside = mask[y0:y1, x0:x1]
        area = int(inside.sum())
        if area == 0:
            continue
        fill_ratio = area / float(cluster["w"] * cluster["h"])
        design_mean, render_mean = design_crop[inside].mean(axis=0), render_crop[inside].mean(axis=0)
        color_gap = float(abs(design_mean - render_mean).max())
        is_flat = (_edge_density(design_crop, threshold) < MAX_EDGE_DENSITY
                   and _edge_density(render_crop, threshold) < MAX_EDGE_DENSITY)
        if is_flat and color_gap > MIN_COLOR_GAP and fill_ratio >= MIN_FILL_RATIO:
            blobs.append({**cluster, "area": area, "fill_ratio": round(fill_ratio, 2),
                          "design_rgb": [int(v) for v in design_mean],
                          "render_rgb": [int(v) for v in render_mean], "color_gap": round(color_gap)})
    blobs.sort(key=lambda blob: -blob["area"])
    return blobs
