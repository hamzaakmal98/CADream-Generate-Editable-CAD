from __future__ import annotations

import math
from typing import Any

import numpy as np

from ml.rules import DOWNWEIGHT_LAYERS, EQUIP_LAYERS, NOISE_LAYERS, SITE_CONTEXT_LAYERS, normalize


_NOISE_SUBSTR = tuple(normalize(item) for item in NOISE_LAYERS)
_DOWNWEIGHT = {normalize(item) for item in DOWNWEIGHT_LAYERS}
_EQUIPMENT_KEYWORDS = tuple(normalize(item) for item in EQUIP_LAYERS)
_SITE_CONTEXT_KEYWORDS = tuple(normalize(item) for item in SITE_CONTEXT_LAYERS)


def is_noise_layer(layer_name: str) -> bool:
    layer = normalize(layer_name)
    return any(token in layer for token in _NOISE_SUBSTR)


def _contains_any(layer_name: str, keywords: tuple[str, ...]) -> bool:
    layer = normalize(layer_name)
    return any(keyword in layer for keyword in keywords)


def _is_equipment_layer(layer_name: str) -> bool:
    return _contains_any(layer_name, _EQUIPMENT_KEYWORDS)


def _is_site_context_layer(layer_name: str) -> bool:
    return _contains_any(layer_name, _SITE_CONTEXT_KEYWORDS)


def _should_draw_layer(layer_name: str, mode: str) -> bool:
    layer = normalize(layer_name)
    is_noise = is_noise_layer(layer)

    if mode == "noise":
        return is_noise

    if is_noise:
        return False

    if mode == "density" and layer in _DOWNWEIGHT:
        return False
    if mode == "equipment" and not _is_equipment_layer(layer):
        return False
    if mode == "site_context" and not _is_site_context_layer(layer):
        return False
    return True


def _render_bounds(render_doc: dict[str, Any], bounds_override: tuple[float, float, float, float] | None = None) -> tuple[float, float, float, float]:
    if bounds_override is not None:
        min_x, min_y, max_x, max_y = [float(v) for v in bounds_override]
        if max_x <= min_x or max_y <= min_y:
            raise ValueError("bounds_override is degenerate")
        return min_x, min_y, max_x, max_y

    bounds = render_doc.get("bounds") if isinstance(render_doc, dict) else None
    if not isinstance(bounds, dict):
        raise ValueError("render_doc missing bounds")

    mn = bounds.get("min")
    mx = bounds.get("max")
    if not isinstance(mn, list) or not isinstance(mx, list) or len(mn) < 2 or len(mx) < 2:
        raise ValueError("render_doc bounds invalid")

    min_x = float(mn[0])
    min_y = float(mn[1])
    max_x = float(mx[0])
    max_y = float(mx[1])

    if max_x <= min_x or max_y <= min_y:
        raise ValueError("render_doc bounds degenerate")
    return min_x, min_y, max_x, max_y


def _to_pixel(x: float, y: float, *, min_x: float, min_y: float, max_x: float, max_y: float, size: int) -> tuple[int, int]:
    px = (x - min_x) / (max_x - min_x)
    py = 1.0 - ((y - min_y) / (max_y - min_y))
    ix = int(round(max(0.0, min(1.0, px)) * (size - 1)))
    iy = int(round(max(0.0, min(1.0, py)) * (size - 1)))
    return ix, iy


def _draw_pixel(img: np.ndarray, x: int, y: int, value: int = 255) -> None:
    h, w = img.shape
    if 0 <= x < w and 0 <= y < h:
        img[y, x] = max(img[y, x], value)


def _draw_disk(img: np.ndarray, x: int, y: int, radius: int = 2, value: int = 255) -> None:
    for yy in range(y - radius, y + radius + 1):
        for xx in range(x - radius, x + radius + 1):
            if (xx - x) * (xx - x) + (yy - y) * (yy - y) <= radius * radius:
                _draw_pixel(img, xx, yy, value=value)


def _draw_line(img: np.ndarray, x0: int, y0: int, x1: int, y1: int, value: int = 255) -> None:
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    x, y = x0, y0
    while True:
        _draw_pixel(img, x, y, value=value)
        if x == x1 and y == y1:
            break
        e2 = err * 2
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy


def _arc_polyline(center: tuple[float, float], radius: float, start_deg: float, end_deg: float, segments: int = 24) -> list[tuple[float, float]]:
    cx, cy = center
    start = math.radians(start_deg)
    end = math.radians(end_deg)
    if end < start:
        end += math.tau

    out: list[tuple[float, float]] = []
    for index in range(segments + 1):
        t = start + (end - start) * index / max(1, segments)
        out.append((cx + radius * math.cos(t), cy + radius * math.sin(t)))
    return out


def rasterize_render_doc(
    render_doc: dict,
    out_size: int = 512,
    mode: str = "all",
    bounds_override: tuple[float, float, float, float] | None = None,
) -> np.ndarray:
    """
    Returns uint8 image HxW.
    mode:
      - "all": draw all non-noise geometry
      - "density": draw non-noise geometry excluding downweight layers
            - "equipment": draw equipment-like non-noise geometry only
            - "site_context": draw site-context-like non-noise geometry only
            - "noise": draw noise layers only
    """
    min_x, min_y, max_x, max_y = _render_bounds(render_doc, bounds_override=bounds_override)
    entities = render_doc.get("entities") if isinstance(render_doc, dict) else None
    if not isinstance(entities, list):
        raise ValueError("render_doc missing entities")

    img = np.zeros((out_size, out_size), dtype=np.uint8)

    for entity in entities:
        if not isinstance(entity, dict):
            continue
        layer = str(entity.get("layer") or "")
        if not _should_draw_layer(layer, mode):
            continue

        entity_type = str(entity.get("type") or "").upper()

        if entity_type == "LINE":
            p1 = entity.get("p1")
            p2 = entity.get("p2")
            if isinstance(p1, list) and len(p1) >= 2 and isinstance(p2, list) and len(p2) >= 2:
                x0, y0 = _to_pixel(float(p1[0]), float(p1[1]), min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y, size=out_size)
                x1, y1 = _to_pixel(float(p2[0]), float(p2[1]), min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y, size=out_size)
                _draw_line(img, x0, y0, x1, y1)
            continue

        if entity_type == "LWPOLYLINE":
            points = entity.get("points") if isinstance(entity.get("points"), list) else []
            world_points = [
                (float(point[0]), float(point[1]))
                for point in points
                if isinstance(point, list) and len(point) >= 2
            ]
            if len(world_points) < 2:
                continue
            prev = world_points[0]
            for curr in world_points[1:]:
                x0, y0 = _to_pixel(prev[0], prev[1], min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y, size=out_size)
                x1, y1 = _to_pixel(curr[0], curr[1], min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y, size=out_size)
                _draw_line(img, x0, y0, x1, y1)
                prev = curr
            if entity.get("closed"):
                x0, y0 = _to_pixel(prev[0], prev[1], min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y, size=out_size)
                x1, y1 = _to_pixel(world_points[0][0], world_points[0][1], min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y, size=out_size)
                _draw_line(img, x0, y0, x1, y1)
            continue

        if entity_type in ("CIRCLE", "ARC"):
            center = entity.get("center")
            radius = entity.get("r")
            if not (isinstance(center, list) and len(center) >= 2 and isinstance(radius, (int, float))):
                continue
            cx, cy = float(center[0]), float(center[1])
            r = abs(float(radius))
            if r <= 0:
                continue

            if entity_type == "CIRCLE":
                world_points = _arc_polyline((cx, cy), r, 0.0, 360.0, segments=36)
            else:
                world_points = _arc_polyline(
                    (cx, cy),
                    r,
                    float(entity.get("start_angle", 0.0)),
                    float(entity.get("end_angle", 360.0)),
                    segments=24,
                )
            prev = world_points[0]
            for curr in world_points[1:]:
                x0, y0 = _to_pixel(prev[0], prev[1], min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y, size=out_size)
                x1, y1 = _to_pixel(curr[0], curr[1], min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y, size=out_size)
                _draw_line(img, x0, y0, x1, y1)
                prev = curr
            continue

        if entity_type == "INSERT":
            pos = entity.get("pos")
            if isinstance(pos, list) and len(pos) >= 2:
                x, y = _to_pixel(float(pos[0]), float(pos[1]), min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y, size=out_size)
                _draw_disk(img, x, y, radius=2)
            continue

        if entity_type in ("TEXT", "MTEXT"):
            pos = entity.get("pos")
            if isinstance(pos, list) and len(pos) >= 2:
                x, y = _to_pixel(float(pos[0]), float(pos[1]), min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y, size=out_size)
                _draw_pixel(img, x, y, value=200)

    return img


def rasterize_render_doc_4ch(
    render_doc: dict,
    out_size: int = 512,
    bounds_override: tuple[float, float, float, float] | None = None,
) -> np.ndarray:
        """
        Returns uint8 tensor [4, H, W] in this channel order:
            0: all_non_noise
            1: equipment_layers_only
            2: site_context_layers_only
            3: noise_layers_only
        """
        channel_all = rasterize_render_doc(render_doc, out_size=out_size, mode="all", bounds_override=bounds_override)
        channel_equipment = rasterize_render_doc(render_doc, out_size=out_size, mode="equipment", bounds_override=bounds_override)
        channel_site_context = rasterize_render_doc(render_doc, out_size=out_size, mode="site_context", bounds_override=bounds_override)
        channel_noise = rasterize_render_doc(render_doc, out_size=out_size, mode="noise", bounds_override=bounds_override)
        return np.stack([channel_all, channel_equipment, channel_site_context, channel_noise], axis=0)
