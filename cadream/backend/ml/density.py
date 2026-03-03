from __future__ import annotations

import numpy as np


def best_density_window(img: np.ndarray, window_frac: float = 0.25, stride_frac: float = 0.05):
    """
    Returns normalized coords (x1,y1,x2,y2) and density score.
    Uses sum of pixels as score.
    """
    if img.ndim != 2:
        raise ValueError("Density image must be a 2D array")

    h, w = img.shape
    if h < 2 or w < 2:
        raise ValueError("Density image is too small")

    win_w = max(2, int(round(w * window_frac)))
    win_h = max(2, int(round(h * window_frac)))
    stride_x = max(1, int(round(w * stride_frac)))
    stride_y = max(1, int(round(h * stride_frac)))

    integral = img.astype(np.float64).cumsum(axis=0).cumsum(axis=1)

    def box_sum(x1: int, y1: int, x2: int, y2: int) -> float:
        total = float(integral[y2 - 1, x2 - 1])
        if x1 > 0:
            total -= float(integral[y2 - 1, x1 - 1])
        if y1 > 0:
            total -= float(integral[y1 - 1, x2 - 1])
        if x1 > 0 and y1 > 0:
            total += float(integral[y1 - 1, x1 - 1])
        return total

    best = (0, 0, win_w, win_h)
    best_score = -1.0

    for y1 in range(0, max(1, h - win_h + 1), stride_y):
        y2 = min(h, y1 + win_h)
        y1 = y2 - win_h
        for x1 in range(0, max(1, w - win_w + 1), stride_x):
            x2 = min(w, x1 + win_w)
            x1 = x2 - win_w
            score = box_sum(x1, y1, x2, y2)
            if score > best_score:
                best = (x1, y1, x2, y2)
                best_score = score

    x1, y1, x2, y2 = best
    nx1 = x1 / max(1, w - 1)
    ny1 = y1 / max(1, h - 1)
    nx2 = x2 / max(1, w - 1)
    ny2 = y2 / max(1, h - 1)
    return [float(nx1), float(ny1), float(nx2), float(ny2)], float(best_score)
