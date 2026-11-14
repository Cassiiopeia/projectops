"""Text row matching: design · render text row y-ranges > pairing > offset (logical px) · unpaired rows

On screens with a moving background (aurora·loading), the differing pixel % is swamped by the background and useless.
Which height text sits at can be read as numbers (found a title wrapping to a fourth line in elum).
"""
from __future__ import annotations

# Brightness sum (R+G+B) below this counts as text ink
INK_BRIGHTNESS_SUM = 300
# Row height (px) below this is noise
MIN_ROW_HEIGHT_PIXELS = 3
# Farther than this (logical px) is not paired as the same row
MAX_ROW_OFFSET_LOGICAL = 40


def ink_rows(image, top: int, bottom: int) -> list[tuple[int, int]]:
    """Horizontal runs with ink [(y0, y1)] (top·bottom bands excluded)"""
    dark = image.sum(axis=2) < INK_BRIGHTNESS_SUM
    if top:
        dark[:top] = False
    if bottom:
        dark[-bottom:] = False
    counts = dark.sum(axis=1)
    runs, start = [], None
    for y, value in enumerate(counts):
        if value > 0 and start is None:
            start = y
        elif value == 0 and start is not None:
            if y - start >= MIN_ROW_HEIGHT_PIXELS:
                runs.append((start, y))
            start = None
    if start is not None:
        runs.append((start, len(counts)))
    return runs


def match_rows(design_rows: list, render_rows: list, scale: float) -> list[tuple]:
    """Maximize pairs while keeping order, smaller offset sum on ties (one off row does not shift everything after it)"""
    design_count, render_count = len(design_rows), len(render_rows)
    infinity = float("inf")
    # cost[i][j] = (unpaired row count, offset sum) — lexicographic comparison
    cost = [[(infinity, infinity)] * (render_count + 1) for _ in range(design_count + 1)]
    back = [[None] * (render_count + 1) for _ in range(design_count + 1)]
    cost[0][0] = (0, 0)
    for i in range(design_count + 1):
        for j in range(render_count + 1):
            current = cost[i][j]
            if current[0] == infinity:
                continue
            steps = []
            if i < design_count:
                steps.append((i + 1, j, (current[0] + 1, current[1]), "design_only"))
            if j < render_count:
                steps.append((i, j + 1, (current[0] + 1, current[1]), "render_only"))
            if i < design_count and j < render_count:
                offset = abs(render_rows[j][0] - design_rows[i][0]) / scale
                if offset <= MAX_ROW_OFFSET_LOGICAL:
                    steps.append((i + 1, j + 1, (current[0], current[1] + offset), "pair"))
            for next_i, next_j, candidate, how in steps:
                if candidate < cost[next_i][next_j]:
                    cost[next_i][next_j], back[next_i][next_j] = candidate, (i, j, how)
    pairs, i, j = [], design_count, render_count
    while (i, j) != (0, 0):
        previous_i, previous_j, how = back[i][j]
        if how == "pair":
            pairs.append((design_rows[previous_i], render_rows[previous_j]))
        elif how == "design_only":
            pairs.append((design_rows[previous_i], None))
        else:
            pairs.append((None, render_rows[previous_j]))
        i, j = previous_i, previous_j
    pairs.reverse()
    return pairs


def compare_rows(design, render, top: int, bottom: int, scale: float) -> dict:
    """Text row comparison result: rows [{design, render, offset | only}] · offset rows · unpaired row count"""
    pairs = match_rows(ink_rows(design, top, bottom), ink_rows(render, top, bottom), scale)

    def logical(run):
        return [round(run[0] / scale), round(run[1] / scale)] if run else None

    rows, shifted, lonely = [], 0, 0
    for design_run, render_run in pairs:
        entry = {"design": logical(design_run), "render": logical(render_run)}
        if design_run and render_run:
            entry["offset"] = round((render_run[0] - design_run[0]) / scale)
            shifted += abs(entry["offset"]) > 1
        else:
            entry["only"] = "render" if render_run else "design"
            lonely += 1
        rows.append(entry)
    return {"rows": rows, "shifted_rows": shifted, "unpaired_rows": lonely,
            "note": ("Unpaired rows mean a line wrapped once more, an element is missing, or two close "
                     "lines were counted as one. Shifted rows are logical px, top edge")}
