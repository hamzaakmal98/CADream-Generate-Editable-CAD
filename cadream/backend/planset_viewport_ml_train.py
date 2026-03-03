from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

from cad_parser import dxf_to_render_json, load_dxf_from_bytes


@dataclass(frozen=True)
class SampleStats:
    name: str
    points: list[tuple[float, float]]
    layer_counts: dict[str, int]


def _extract_points_and_layers(render_payload: dict[str, Any]) -> tuple[list[tuple[float, float]], dict[str, int]]:
    entities = render_payload.get("entities") if isinstance(render_payload, dict) else None
    if not isinstance(entities, list):
        return [], {}

    insert_points: list[tuple[float, float]] = []
    fallback_points: list[tuple[float, float]] = []
    layers: dict[str, int] = {}

    for entity in entities:
        if not isinstance(entity, dict):
            continue

        layer = entity.get("layer")
        if isinstance(layer, str) and layer.strip():
            layers[layer] = layers.get(layer, 0) + 1

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
                fallback_points.append(((float(p1[0]) + float(p2[0])) * 0.5, (float(p1[1]) + float(p2[1])) * 0.5))
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
                    fallback_points.append((sx / count, sy / count))

    return (insert_points if insert_points else fallback_points), layers


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    clamped = min(1.0, max(0.0, q))
    idx = (len(sorted_values) - 1) * clamped
    lo = int(idx)
    hi = min(len(sorted_values) - 1, lo + 1)
    t = idx - lo
    return sorted_values[lo] * (1.0 - t) + sorted_values[hi] * t


def _coverage_and_area_ratio(points: list[tuple[float, float]], q_low: float) -> tuple[float, float]:
    if len(points) < 10:
        return 0.0, 1.0
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]

    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)
    full_area = max(1e-6, (max_x - min_x) * (max_y - min_y))

    q_high = 1.0 - q_low
    qmin_x = _quantile(xs, q_low)
    qmax_x = _quantile(xs, q_high)
    qmin_y = _quantile(ys, q_low)
    qmax_y = _quantile(ys, q_high)
    if qmax_x <= qmin_x or qmax_y <= qmin_y:
        return 0.0, 1.0

    inside = 0
    for x, y in points:
        if qmin_x <= x <= qmax_x and qmin_y <= y <= qmax_y:
            inside += 1

    cover = inside / max(1, len(points))
    q_area = (qmax_x - qmin_x) * (qmax_y - qmin_y)
    return cover, q_area / full_area


def _choose_quantile(samples: list[SampleStats]) -> float:
    candidates = [0.01, 0.02, 0.03, 0.04, 0.05]
    best_q = 0.02
    best_score = -1e9

    for q in candidates:
        cover_values: list[float] = []
        area_values: list[float] = []
        for sample in samples:
            cover, area_ratio = _coverage_and_area_ratio(sample.points, q)
            if cover <= 0:
                continue
            cover_values.append(cover)
            area_values.append(area_ratio)

        if not cover_values:
            continue

        med_cover = median(cover_values)
        med_area = median(area_values)

        penalty = 0.0
        if med_cover < 0.9:
            penalty += (0.9 - med_cover) * 10.0
        score = (1.0 - med_area) + med_cover - penalty

        if score > best_score:
            best_q = q
            best_score = score

    return best_q


def _densest_cell_concentration(points: list[tuple[float, float]], rows: int, cols: int) -> float:
    if len(points) < 4:
        return 0.0
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    if max_x <= min_x or max_y <= min_y:
        return 0.0

    cell_w = (max_x - min_x) / max(1, cols)
    cell_h = (max_y - min_y) / max(1, rows)
    if cell_w <= 0 or cell_h <= 0:
        return 0.0

    buckets: dict[tuple[int, int], int] = {}
    for x, y in points:
        col = min(cols - 1, max(0, int((x - min_x) / cell_w)))
        row = min(rows - 1, max(0, int((y - min_y) / cell_h)))
        key = (row, col)
        buckets[key] = buckets.get(key, 0) + 1

    return max(buckets.values()) / max(1, len(points)) if buckets else 0.0


def _choose_grid(samples: list[SampleStats]) -> tuple[int, int]:
    candidates = [(4, 4), (5, 5), (6, 6)]
    best = (4, 4)
    best_score = -1e9
    for rows, cols in candidates:
        concentrations = [_densest_cell_concentration(sample.points, rows, cols) for sample in samples if sample.points]
        if not concentrations:
            continue
        med = median(concentrations)
        score = med - (rows * cols * 0.002)
        if score > best_score:
            best_score = score
            best = (rows, cols)
    return best


def _pick_layer_include(samples: list[SampleStats], keywords: list[str], top_n: int = 6) -> list[str]:
    keys = [keyword.lower() for keyword in keywords]
    merged: dict[str, int] = {}
    for sample in samples:
        for layer, count in sample.layer_counts.items():
            lower = layer.lower()
            if any(keyword in lower for keyword in keys):
                merged[layer] = merged.get(layer, 0) + count

    ranked = sorted(merged.items(), key=lambda item: (-item[1], item[0]))
    return [name for name, _ in ranked[:top_n]]


def train_viewport_ml_v1(sample_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    files = sorted(sample_dir.glob("Input_Sample_*.dxf"))
    samples: list[SampleStats] = []

    for file_path in files:
        data = file_path.read_bytes()
        doc = load_dxf_from_bytes(data)
        payload = dxf_to_render_json(doc, max_entities=50000)
        points, layers = _extract_points_and_layers(payload)
        samples.append(SampleStats(name=file_path.name, points=points, layer_counts=layers))

    q = _choose_quantile(samples)
    rows, cols = _choose_grid(samples)

    ess5_layers = _pick_layer_include(samples, ["module", "inverter", "transformer", "cable", "service", "switch"], top_n=6)
    ess4_layers = _pick_layer_include(samples, ["cable", "service", "switch", "panel", "conduit"], top_n=6)

    config = {
        "schema_version": "viewport-ml-v1",
        "target_sheets": {
            "ESS-1.0": {
                "strategy": "quantile",
                "q_low": q,
                "q_high": round(1.0 - q, 2),
                "pad_ratio": 0.08,
                "min_pad": 8.0,
            },
            "ESS-5.0": {
                "strategy": "densest_cell",
                "grid_rows": rows,
                "grid_cols": cols,
                "pad_ratio": 0.12,
                "min_pad": 6.0,
                "layer_include": ess5_layers,
            },
            "ESS-4.0": {
                "strategy": "densest_cell",
                "grid_rows": rows,
                "grid_cols": cols,
                "pad_ratio": 0.10,
                "min_pad": 4.0,
                "layer_include": ess4_layers,
            },
        },
    }

    metrics = {
        "samples": [
            {
                "name": sample.name,
                "point_count": len(sample.points),
                "top_layers": [name for name, _ in sorted(sample.layer_counts.items(), key=lambda item: (-item[1], item[0]))[:8]],
            }
            for sample in samples
        ],
        "selected": {
            "quantile_q_low": q,
            "densest_grid": [rows, cols],
        },
    }

    return config, metrics
