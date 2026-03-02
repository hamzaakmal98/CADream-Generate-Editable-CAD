from __future__ import annotations

from typing import Iterable


def compute_bounds(points: Iterable[tuple[float, float]]) -> tuple[float, float, float, float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for x, y in points:
        xs.append(float(x))
        ys.append(float(y))
    if not xs or not ys:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def expand_bounds(
    bounds: tuple[float, float, float, float],
    *,
    pad_ratio: float = 0.08,
    min_pad: float = 5.0,
) -> tuple[float, float, float, float]:
    min_x, min_y, max_x, max_y = bounds
    width = max(1e-6, max_x - min_x)
    height = max(1e-6, max_y - min_y)
    pad = max(min_pad, max(width, height) * max(0.0, pad_ratio))
    return min_x - pad, min_y - pad, max_x + pad, max_y + pad


def build_projector(
    source_bounds: tuple[float, float, float, float],
    *,
    dest_min_x: float,
    dest_min_y: float,
    dest_max_x: float,
    dest_max_y: float,
) -> tuple[float, float, float]:
    src_min_x, src_min_y, src_max_x, src_max_y = source_bounds
    src_w = max(1e-6, src_max_x - src_min_x)
    src_h = max(1e-6, src_max_y - src_min_y)

    dst_w = max(1e-6, dest_max_x - dest_min_x)
    dst_h = max(1e-6, dest_max_y - dest_min_y)

    scale = min(dst_w / src_w, dst_h / src_h)

    draw_w = src_w * scale
    draw_h = src_h * scale
    offset_x = dest_min_x + (dst_w - draw_w) * 0.5
    offset_y = dest_min_y + (dst_h - draw_h) * 0.5

    return scale, offset_x - src_min_x * scale, offset_y - src_min_y * scale


def project_point(point: tuple[float, float], projector: tuple[float, float, float]) -> tuple[float, float]:
    x, y = point
    scale, tx, ty = projector
    return x * scale + tx, y * scale + ty
