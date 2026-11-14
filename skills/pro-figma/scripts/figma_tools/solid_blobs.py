"""Color fills on one side only: differing pixel blobs that are color fills, not text

Garbled text has dense edges on both sides. An image piece on one side only is smooth on both sides and differs only in color.
A silhouette shifted by 1px is nearly empty inside its box (fill ratio ~0.1), so it is filtered out.
Even on a screen whose score dropped to 1.66%, this found an asset piece left only in the app (a 13px beak) (elum).
"""
from __future__ import annotations

# Edge density cap: denser than this counts as text
MAX_EDGE_DENSITY = 0.10
# Minimum mean difference design color <-> render color
MIN_COLOR_GAP = 40
# Minimum ratio of the box filled by the blob
MIN_FILL_RATIO = 0.30


def _edge_density(image, threshold: int) -> float:
    """Ratio of pixels differing strongly from the horizontal neighbor (high for text, near 0 for fills)"""
    if image.shape[1] < 2:
        return 0.0
    import numpy as np
    neighbor_delta = np.abs(image[:, 1:].astype(np.int16) - image[:, :-1]).max(axis=2)
    return float((neighbor_delta > threshold).mean())


def connected_components(mask, min_area: int) -> list[dict]:
    """Differing pixels into connected blobs (4-neighbor) (row runs > union-find when overlapping the row above)

    diff's row boxes merge a row's text and image into one box, so they cannot tell fill from text.
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
            # Split contiguous runs
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
    """Differing pixel connected blobs > color-fill differences only (largest first)"""
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
