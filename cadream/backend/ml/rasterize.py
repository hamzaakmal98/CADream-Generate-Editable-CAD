from __future__ import annotations

import math
from typing import Any

import numpy as np


def _layer_channel(layer: str) -> int | None:
    lower = layer.lower()

    equipment_keywords = ["module", "inverter", "transform", "battery", "bess", "pcs", "组件", "设备", "逆变"]
    cable_keywords = ["cable", "conduit", "trench", "wire", "电缆", "线", "沟"]
    boundary_keywords = ["boundary", "property", "area", "road", "obstruction", "map", "边界", "道路", "总图"]

    if any(token in lower for token in equipment_keywords):
        return 1
    if any(token in lower for token in cable_keywords):
        return 2
    if any(token in lower for token in boundary_keywords):
        return 3
    return None


def _as_bounds(render_doc: dict[str, Any]) -> tuple[float, float, float, float]:
    bounds = render_doc.get("bounds") if isinstance(render_doc, dict) else None
    if not isinstance(bounds, dict):
        raise ValueError("render_doc missing bounds")

    mn = bounds.get("min")
    mx = bounds.get("max")
    if not isinstance(mn, list) or not isinstance(mx, list) or len(mn) < 2 or len(mx) < 2:
        raise ValueError("render_doc bounds must have min/max XY")

    min_x = float(mn[0])
    min_y = float(mn[1])
    max_x = float(mx[0])
    max_y = float(mx[1])

    if max_x <= min_x or max_y <= min_y:
        raise ValueError("render_doc bounds are degenerate")

    return min_x, min_y, max_x, max_y


def _to_pixel(x: float, y: float, *, min_x: float, min_y: float, max_x: float, max_y: float, size: int) -> tuple[int, int]:
    px = (x - min_x) / (max_x - min_x)
    py = 1.0 - ((y - min_y) / (max_y - min_y))
    ix = int(round(max(0.0, min(1.0, px)) * (size - 1)))
    iy = int(round(max(0.0, min(1.0, py)) * (size - 1)))
    return ix, iy


def _draw_pixel(img: np.ndarray, x: int, y: int, channel: int, value: int = 255) -> None:
    h, w, _ = img.shape
    if 0 <= x < w and 0 <= y < h:
        img[y, x, 0] = max(img[y, x, 0], value)
        if 1 <= channel <= 3:
            img[y, x, channel] = max(img[y, x, channel], value)


def _draw_line(img: np.ndarray, x0: int, y0: int, x1: int, y1: int, channel: int, value: int = 255) -> None:
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    x, y = x0, y0
    while True:
        _draw_pixel(img, x, y, channel, value)
        if x == x1 and y == y1:
            break
        e2 = err * 2
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy


def _polyline_points(points: list[list[float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for point in points:
        if isinstance(point, list) and len(point) >= 2:
            out.append((float(point[0]), float(point[1])))
    return out


def _arc_polyline(center: tuple[float, float], radius: float, start_deg: float, end_deg: float, segments: int = 24) -> list[tuple[float, float]]:
    cx, cy = center
    start = math.radians(start_deg)
    end = math.radians(end_deg)
    if end < start:
        end += math.tau

    pts: list[tuple[float, float]] = []
    for idx in range(segments + 1):
        t = start + (end - start) * idx / max(1, segments)
        pts.append((cx + radius * math.cos(t), cy + radius * math.sin(t)))
    return pts


def rasterize_render_doc(render_doc: dict[str, Any], out_size: int = 512) -> np.ndarray:
    min_x, min_y, max_x, max_y = _as_bounds(render_doc)
    entities = render_doc.get("entities") if isinstance(render_doc, dict) else None
    if not isinstance(entities, list):
        raise ValueError("render_doc missing entities")

    img = np.zeros((out_size, out_size, 4), dtype=np.uint8)

    for entity in entities:
        if not isinstance(entity, dict):
            continue

        layer = str(entity.get("layer") or "")
        channel = _layer_channel(layer)
        entity_type = entity.get("type")

        if entity_type == "LINE":
            p1 = entity.get("p1")
            p2 = entity.get("p2")
            if isinstance(p1, list) and len(p1) >= 2 and isinstance(p2, list) and len(p2) >= 2:
                x0, y0 = _to_pixel(float(p1[0]), float(p1[1]), min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y, size=out_size)
                x1, y1 = _to_pixel(float(p2[0]), float(p2[1]), min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y, size=out_size)
                _draw_line(img, x0, y0, x1, y1, channel or 0)
            continue

        if entity_type == "LWPOLYLINE":
            pts = _polyline_points(entity.get("points") if isinstance(entity.get("points"), list) else [])
            if len(pts) < 2:
                continue
            prev = pts[0]
            for point in pts[1:]:
                x0, y0 = _to_pixel(prev[0], prev[1], min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y, size=out_size)
                x1, y1 = _to_pixel(point[0], point[1], min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y, size=out_size)
                _draw_line(img, x0, y0, x1, y1, channel or 0)
                prev = point
            if entity.get("closed"):
                x0, y0 = _to_pixel(prev[0], prev[1], min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y, size=out_size)
                x1, y1 = _to_pixel(pts[0][0], pts[0][1], min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y, size=out_size)
                _draw_line(img, x0, y0, x1, y1, channel or 0)
            continue

        if entity_type in ("CIRCLE", "ARC"):
            center = entity.get("center")
            radius = entity.get("r")
            if not (isinstance(center, list) and len(center) >= 2 and isinstance(radius, (int, float))):
                continue
            if entity_type == "CIRCLE":
                world_pts = _arc_polyline((float(center[0]), float(center[1])), abs(float(radius)), 0.0, 360.0, segments=32)
            else:
                world_pts = _arc_polyline(
                    (float(center[0]), float(center[1])),
                    abs(float(radius)),
                    float(entity.get("start_angle", 0.0)),
                    float(entity.get("end_angle", 360.0)),
                    segments=20,
                )
            prev = world_pts[0]
            for point in world_pts[1:]:
                x0, y0 = _to_pixel(prev[0], prev[1], min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y, size=out_size)
                x1, y1 = _to_pixel(point[0], point[1], min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y, size=out_size)
                _draw_line(img, x0, y0, x1, y1, channel or 0)
                prev = point
            continue

        if entity_type in ("TEXT", "MTEXT"):
            pos = entity.get("pos")
            if isinstance(pos, list) and len(pos) >= 2:
                x, y = _to_pixel(float(pos[0]), float(pos[1]), min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y, size=out_size)
                _draw_pixel(img, x, y, channel or 0, value=220)

    return img
