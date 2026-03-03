from __future__ import annotations

from typing import Any

import numpy as np

from ml import EQUIPMENT_LAYOUT
from ml.layer_stats import BBox


def box_metrics(img: np.ndarray, bb: list[float]) -> dict:
    """Returns density and geometry diagnostics for a normalized image bbox."""
    if img.ndim != 2:
        raise ValueError("Expected a 2D raster image")
    h, w = img.shape

    x1, y1, x2, y2 = [float(v) for v in bb]
    x1, x2 = sorted((max(0.0, min(1.0, x1)), max(0.0, min(1.0, x2))))
    y1, y2 = sorted((max(0.0, min(1.0, y1)), max(0.0, min(1.0, y2))))

    ix1 = max(0, min(w - 1, int(round(x1 * (w - 1)))))
    ix2 = max(0, min(w - 1, int(round(x2 * (w - 1)))))
    iy1 = max(0, min(h - 1, int(round(y1 * (h - 1)))))
    iy2 = max(0, min(h - 1, int(round(y2 * (h - 1)))))

    if ix2 < ix1:
        ix1, ix2 = ix2, ix1
    if iy2 < iy1:
        iy1, iy2 = iy2, iy1

    area_frac = max(0.0, (x2 - x1) * (y2 - y1))
    edge_touch = float(x1 <= 0.001 or y1 <= 0.001 or x2 >= 0.999 or y2 >= 0.999)

    patch = img[iy1 : iy2 + 1, ix1 : ix2 + 1]
    in_box = float(patch.mean()) if patch.size else 0.0
    global_avg = float(img.mean()) if img.size else 1e-6
    density_rel = in_box / max(1e-6, global_avg)

    return {
        "area_frac": area_frac,
        "density_in_box": in_box,
        "density_rel": density_rel,
        "edge_touch_frac": edge_touch,
    }


def _intersects(a: BBox, b: BBox) -> bool:
    return not (a.maxx < b.minx or b.maxx < a.minx or a.maxy < b.miny or b.maxy < a.miny)


def _equipment_anchor_presence(model_bbox: BBox, layer_stats: dict[str, dict]) -> float:
    score = 0.0
    for key in ("inverter", "module"):
        payload = layer_stats.get(key)
        if not isinstance(payload, dict):
            continue
        bbox = payload.get("bbox")
        count = int(payload.get("count", 0))
        if isinstance(bbox, BBox) and count > 0 and _intersects(model_bbox, bbox):
            score += 0.5
    return min(1.0, score)


def _passes_gates(page_type: str, metrics: dict, model_bbox: BBox, layer_stats: dict[str, dict]) -> bool:
    area_ok = 0.02 <= float(metrics.get("area_frac", 0.0)) <= 0.80
    density_ok = float(metrics.get("density_rel", 0.0)) >= 0.8
    if not (area_ok and density_ok):
        return False

    if page_type == EQUIPMENT_LAYOUT:
        return _equipment_anchor_presence(model_bbox, layer_stats) > 0.0
    return True


def choose_box(
    page_type: str,
    teacher_bb: list[float],
    teacher_conf: float,
    model_bb: list[float],
    model_conf: float,
    metrics_teacher: dict,
    metrics_model: dict,
    model_bbox_obj: BBox,
    layer_stats: dict[str, dict],
):
    """
    If model fails gates -> teacher.
    Else choose higher quality score.
    """
    def quality(metrics: dict, conf: float) -> float:
        density = float(metrics.get("density_rel", 0.0))
        area = float(metrics.get("area_frac", 0.0))
        area_penalty = abs(area - 0.25)
        return 0.6 * density + 0.3 * float(conf) - 0.1 * area_penalty

    model_ok = _passes_gates(page_type, metrics_model, model_bbox_obj, layer_stats)
    if not model_ok:
        return teacher_bb, "teacher_fallback", {
            "model_passed": False,
            "teacher_conf": teacher_conf,
            "model_conf": model_conf,
            "metrics_teacher": metrics_teacher,
            "metrics_model": metrics_model,
        }

    q_teacher = quality(metrics_teacher, teacher_conf)
    q_model = quality(metrics_model, model_conf)
    if q_model >= q_teacher:
        return model_bb, "model", {
            "model_passed": True,
            "q_teacher": q_teacher,
            "q_model": q_model,
            "metrics_teacher": metrics_teacher,
            "metrics_model": metrics_model,
        }

    return teacher_bb, "teacher_better", {
        "model_passed": True,
        "q_teacher": q_teacher,
        "q_model": q_model,
        "metrics_teacher": metrics_teacher,
        "metrics_model": metrics_model,
    }
