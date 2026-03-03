from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from page_view_spec import Bounds2D


_MODEL_PATH = Path(__file__).resolve().parent / "config" / "viewport_ml_v1.json"


@dataclass(frozen=True)
class ViewportPrediction:
    bounds: Bounds2D
    layer_include: tuple[str, ...] = ()


def _load_model() -> dict[str, Any]:
    data = json.loads(_MODEL_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    return data


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    clamped = min(1.0, max(0.0, q))
    idx = (len(sorted_values) - 1) * clamped
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return sorted_values[lo]
    t = idx - lo
    return sorted_values[lo] * (1.0 - t) + sorted_values[hi] * t


def _extract_points(render_payload: dict[str, Any]) -> list[tuple[float, float]]:
    entities = render_payload.get("entities") if isinstance(render_payload, dict) else None
    if not isinstance(entities, list):
        return []

    insert_points: list[tuple[float, float]] = []
    fallback: list[tuple[float, float]] = []

    for entity in entities:
        if not isinstance(entity, dict):
            continue
        entity_type = entity.get("type")

        if entity_type == "INSERT":
            pos = entity.get("pos")
            if isinstance(pos, list) and len(pos) >= 2:
                insert_points.append((float(pos[0]), float(pos[1])))
            continue

        if entity_type == "LINE":
            p1 = entity.get("p1")
            p2 = entity.get("p2")
            if isinstance(p1, list) and len(p1) >= 2 and isinstance(p2, list) and len(p2) >= 2:
                fallback.append(((float(p1[0]) + float(p2[0])) * 0.5, (float(p1[1]) + float(p2[1])) * 0.5))
            continue

        if entity_type == "LWPOLYLINE":
            points = entity.get("points")
            if isinstance(points, list) and points:
                sx = 0.0
                sy = 0.0
                count = 0
                for point in points:
                    if isinstance(point, list) and len(point) >= 2:
                        sx += float(point[0])
                        sy += float(point[1])
                        count += 1
                if count > 0:
                    fallback.append((sx / count, sy / count))

    if insert_points:
        return insert_points
    return fallback


def _expand_bounds(bounds: Bounds2D, pad_ratio: float, min_pad: float) -> Bounds2D:
    width = max(1e-6, bounds.max_x - bounds.min_x)
    height = max(1e-6, bounds.max_y - bounds.min_y)
    pad_x = max(min_pad, width * pad_ratio)
    pad_y = max(min_pad, height * pad_ratio)
    return Bounds2D(
        min_x=bounds.min_x - pad_x,
        min_y=bounds.min_y - pad_y,
        max_x=bounds.max_x + pad_x,
        max_y=bounds.max_y + pad_y,
    )


def _bounds_quantile(points: list[tuple[float, float]], q_low: float, q_high: float) -> Bounds2D | None:
    if len(points) < 4:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x = _quantile(xs, q_low)
    max_x = _quantile(xs, q_high)
    min_y = _quantile(ys, q_low)
    max_y = _quantile(ys, q_high)
    if max_x <= min_x or max_y <= min_y:
        return None
    return Bounds2D(min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y)


def _bounds_densest_cell(points: list[tuple[float, float]], rows: int, cols: int) -> Bounds2D | None:
    if len(points) < 4:
        return None

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)
    if max_x <= min_x or max_y <= min_y:
        return None

    cell_w = (max_x - min_x) / max(1, cols)
    cell_h = (max_y - min_y) / max(1, rows)
    if cell_w <= 0 or cell_h <= 0:
        return None

    buckets: dict[tuple[int, int], int] = {}
    for x, y in points:
        col = min(cols - 1, max(0, int((x - min_x) / cell_w)))
        row = min(rows - 1, max(0, int((y - min_y) / cell_h)))
        key = (row, col)
        buckets[key] = buckets.get(key, 0) + 1

    if not buckets:
        return None

    best_row, best_col = max(sorted(buckets.keys()), key=lambda key: buckets[key])
    bx0 = min_x + best_col * cell_w
    bx1 = min_x + (best_col + 1) * cell_w
    by0 = min_y + best_row * cell_h
    by1 = min_y + (best_row + 1) * cell_h
    if bx1 <= bx0 or by1 <= by0:
        return None

    return Bounds2D(min_x=bx0, min_y=by0, max_x=bx1, max_y=by1)


def predict_viewport_for_sheet(render_payload: dict[str, Any], sheet_code: str) -> ViewportPrediction | None:
    code = (sheet_code or "").strip()
    if not code:
        return None

    model = _load_model()
    target_sheets = model.get("target_sheets") if isinstance(model, dict) else None
    if not isinstance(target_sheets, dict):
        return None

    config = target_sheets.get(code)
    if not isinstance(config, dict):
        return None

    points = _extract_points(render_payload)
    if not points:
        return None

    strategy = str(config.get("strategy") or "").strip().lower()
    bounds: Bounds2D | None = None

    if strategy == "quantile":
        bounds = _bounds_quantile(
            points,
            q_low=float(config.get("q_low", 0.02)),
            q_high=float(config.get("q_high", 0.98)),
        )
    elif strategy == "densest_cell":
        bounds = _bounds_densest_cell(
            points,
            rows=max(1, int(config.get("grid_rows", 4))),
            cols=max(1, int(config.get("grid_cols", 4))),
        )

    if bounds is None:
        return None

    expanded = _expand_bounds(
        bounds,
        pad_ratio=float(config.get("pad_ratio", 0.1)),
        min_pad=float(config.get("min_pad", 4.0)),
    )

    include = config.get("layer_include")
    include_layers: tuple[str, ...] = tuple(str(item) for item in include) if isinstance(include, list) else ()
    return ViewportPrediction(bounds=expanded, layer_include=include_layers)
