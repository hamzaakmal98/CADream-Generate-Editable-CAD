from __future__ import annotations

import math
from typing import Any

import numpy as np

from ml.density import best_density_window, rasterize_for_density
from ml.layer_stats import BBox, LayerStats, compute_layer_stats
from ml.page_types import PageType
from ml.rules import (
    DOWNWEIGHT_LAYERS,
    EQUIP_LAYERS,
    NOISE_LAYERS,
    SITE_BOUNDARY_LAYERS,
    SITE_CONTEXT_LAYERS,
    normalize,
)


MIN_LAYER_ENTITIES_SITE = 10
MIN_LAYER_ENTITIES_EQUIP = 5
SITE_PAD_FRAC = 0.10
EQUIP_PAD_FRAC = 0.20
MIN_BOX_AREA_FRAC = 0.01

NOISE_SET = {normalize(name) for name in NOISE_LAYERS}
SITE_BOUNDARY_SET = [normalize(name) for name in SITE_BOUNDARY_LAYERS]
SITE_CONTEXT_SET = [normalize(name) for name in SITE_CONTEXT_LAYERS]
EQUIP_SET = [normalize(name) for name in EQUIP_LAYERS]
DOWNWEIGHT_SET = {normalize(name) for name in DOWNWEIGHT_LAYERS}
CABLE_TOKENS = ("cable", "wire", "conduit", "trench", "ductbank", "ac", "dc")


def fit_bbox_to_aspect(b: BBox, aspect: float) -> BBox:
    """
    Expand bbox around its center to match viewport aspect ratio.
    Never shrink.
    """
    target_aspect = max(1e-6, float(aspect))
    width = max(1e-9, b.width())
    height = max(1e-9, b.height())
    current_aspect = width / height

    cx = (b.minx + b.maxx) * 0.5
    cy = (b.miny + b.maxy) * 0.5

    new_width = width
    new_height = height

    if current_aspect < target_aspect:
        new_width = max(width, height * target_aspect)
    else:
        new_height = max(height, width / target_aspect)

    half_w = new_width * 0.5
    half_h = new_height * 0.5
    return BBox(cx - half_w, cy - half_h, cx + half_w, cy + half_h)


def _union_layers(layer_stats: dict[str, LayerStats], layer_names: list[str], min_count: int) -> tuple[BBox | None, list[str]]:
    used: list[str] = []
    union_bbox: BBox | None = None

    for layer_name in layer_names:
        stats = layer_stats.get(layer_name)
        if stats is None or stats.bbox is None or stats.count < min_count:
            continue
        used.append(layer_name)
        union_bbox = stats.bbox if union_bbox is None else union_bbox.union(stats.bbox)

    return union_bbox, used


def _is_cable_like(layer_name: str) -> bool:
    return any(token in layer_name for token in CABLE_TOKENS)


def _intersects_or_near(base: BBox, other: BBox, pad_frac: float = 0.15) -> bool:
    expanded = base.pad(pad_frac)
    if other.maxx < expanded.minx or other.minx > expanded.maxx:
        return False
    if other.maxy < expanded.miny or other.miny > expanded.maxy:
        return False
    return True


def _bbox_from_density_window(global_bbox: BBox, win: tuple[float, float, float, float, float]) -> tuple[BBox, float]:
    x1, y1, x2, y2, score = win

    wx1 = global_bbox.minx + x1 * global_bbox.width()
    wx2 = global_bbox.minx + x2 * global_bbox.width()

    wy_top = global_bbox.maxy - y1 * global_bbox.height()
    wy_bottom = global_bbox.maxy - y2 * global_bbox.height()

    bbox = BBox(min(wx1, wx2), min(wy_bottom, wy_top), max(wx1, wx2), max(wy_bottom, wy_top))
    return bbox, score


def _enforce_min_area(bbox: BBox, global_bbox: BBox, viewport_aspect: float) -> BBox:
    min_area = max(1e-9, global_bbox.area() * MIN_BOX_AREA_FRAC)
    if bbox.area() >= min_area:
        return bbox

    target_aspect = max(1e-6, float(viewport_aspect))
    target_h = math.sqrt(min_area / target_aspect)
    target_w = target_h * target_aspect

    cx = (bbox.minx + bbox.maxx) * 0.5
    cy = (bbox.miny + bbox.maxy) * 0.5
    expanded = BBox(cx - target_w * 0.5, cy - target_h * 0.5, cx + target_w * 0.5, cy + target_h * 0.5)
    return expanded


def make_site_plan_bbox(
    layer_stats: dict[str, LayerStats],
    global_bbox: BBox,
    viewport_aspect: float,
) -> tuple[BBox, float, dict]:
    """
    Priority:
      1) boundary layer bbox (even if count==1)
      2) site context layers with count>=MIN_LAYER_ENTITIES_SITE (excluding noise)
      3) global_bbox excluding noise if possible
    Returns bbox, confidence, debug_info
    """
    debug: dict[str, Any] = {
        "strategy": "global-fallback",
        "used_layers": [],
        "layer_counts": {},
    }

    if "unit area boundary" in layer_stats:
        stats = layer_stats["unit area boundary"]
        if stats.bbox is not None:
            chosen = fit_bbox_to_aspect(stats.bbox.pad(SITE_PAD_FRAC), viewport_aspect)
            min_area = max(1e-9, global_bbox.area() * MIN_BOX_AREA_FRAC)
            if chosen.area() < min_area:
                context_layers = [name for name in SITE_CONTEXT_SET if name not in NOISE_SET]
                context_bbox, context_used = _union_layers(layer_stats, context_layers, min_count=MIN_LAYER_ENTITIES_SITE)
                if context_bbox is not None:
                    chosen = context_bbox.union(chosen)
                    debug["used_layers"] = ["unit area boundary", *context_used]
                    debug["layer_counts"] = {
                        "unit area boundary": stats.count,
                        **{name: layer_stats[name].count for name in context_used},
                    }
                    debug["strategy"] = "unit-area-boundary-with-context"
                else:
                    chosen = chosen.union(global_bbox)
                    debug["used_layers"] = ["unit area boundary"]
                    debug["layer_counts"] = {"unit area boundary": stats.count}
                    debug["strategy"] = "unit-area-boundary-with-global"

            chosen = _enforce_min_area(chosen, global_bbox, viewport_aspect)
            if not debug["used_layers"]:
                debug["strategy"] = "unit-area-boundary"
                debug["used_layers"] = ["unit area boundary"]
                debug["layer_counts"] = {"unit area boundary": stats.count}
            return chosen, 0.95, debug

    boundary_bbox, boundary_used = _union_layers(layer_stats, SITE_BOUNDARY_SET, min_count=1)
    if boundary_bbox is not None:
        chosen = fit_bbox_to_aspect(boundary_bbox.pad(SITE_PAD_FRAC), viewport_aspect)
        chosen = _enforce_min_area(chosen, global_bbox, viewport_aspect)
        debug["strategy"] = "boundary-union"
        debug["used_layers"] = boundary_used
        debug["layer_counts"] = {name: layer_stats[name].count for name in boundary_used}
        return chosen, 0.92, debug

    context_layers = [name for name in SITE_CONTEXT_SET if name not in NOISE_SET]
    context_bbox, context_used = _union_layers(layer_stats, context_layers, min_count=MIN_LAYER_ENTITIES_SITE)
    if context_bbox is not None:
        chosen = fit_bbox_to_aspect(context_bbox.pad(SITE_PAD_FRAC), viewport_aspect)
        chosen = _enforce_min_area(chosen, global_bbox, viewport_aspect)
        debug["strategy"] = "site-context"
        debug["used_layers"] = context_used
        debug["layer_counts"] = {name: layer_stats[name].count for name in context_used}
        return chosen, 0.78, debug

    debug["strategy"] = "global-fallback"
    return fit_bbox_to_aspect(global_bbox, viewport_aspect), 0.55, debug


def make_equipment_layout_bbox(
    layer_stats: dict[str, LayerStats],
    global_bbox: BBox,
    viewport_aspect: float,
    density_img: np.ndarray | None = None,
) -> tuple[BBox, float, dict]:
    """
    Priority:
      1) union of equipment layers with count>=MIN_LAYER_ENTITIES_EQUIP
      2) if too small/empty: density window on raster that ignores DOWNWEIGHT_LAYERS
    Include cable layers only if they are near or intersect equipment bbox.
    Returns bbox, confidence, debug_info
    """
    debug: dict[str, Any] = {
        "strategy": "density-fallback",
        "used_layers": [],
        "layer_counts": {},
        "density_score": None,
    }

    core_layer_names = [name for name in EQUIP_SET if not _is_cable_like(name)]
    cable_layer_names = [name for name in EQUIP_SET if _is_cable_like(name)]

    equip_bbox, used_core = _union_layers(layer_stats, core_layer_names, min_count=MIN_LAYER_ENTITIES_EQUIP)

    if equip_bbox is not None:
        for cable_layer in cable_layer_names:
            stats = layer_stats.get(cable_layer)
            if stats is None or stats.bbox is None or stats.count < MIN_LAYER_ENTITIES_EQUIP:
                continue
            if _intersects_or_near(equip_bbox, stats.bbox):
                equip_bbox = equip_bbox.union(stats.bbox)
                used_core.append(cable_layer)

    global_area = max(1e-9, global_bbox.area())
    min_area = global_area * MIN_BOX_AREA_FRAC

    if equip_bbox is not None and equip_bbox.area() >= min_area:
        chosen = fit_bbox_to_aspect(equip_bbox.pad(EQUIP_PAD_FRAC), viewport_aspect)
        chosen = _enforce_min_area(chosen, global_bbox, viewport_aspect)
        debug["strategy"] = "equipment-layers"
        debug["used_layers"] = sorted(set(used_core))
        debug["layer_counts"] = {name: layer_stats[name].count for name in sorted(set(used_core)) if name in layer_stats}
        return chosen, 0.84, debug

    if density_img is not None:
        win = best_density_window(density_img, window_frac=0.25, stride_frac=0.05)
        density_bbox, density_score = _bbox_from_density_window(global_bbox, win)
        chosen = fit_bbox_to_aspect(density_bbox.pad(EQUIP_PAD_FRAC), viewport_aspect)
        chosen = _enforce_min_area(chosen, global_bbox, viewport_aspect)
        debug["strategy"] = "density-window"
        debug["density_score"] = float(density_score)
        return chosen, 0.66, debug

    return fit_bbox_to_aspect(global_bbox, viewport_aspect), 0.45, debug


def _bbox_to_list(bbox: BBox) -> list[float]:
    return [round(bbox.minx, 6), round(bbox.miny, 6), round(bbox.maxx, 6), round(bbox.maxy, 6)]


def generate_teacher_labels(render_doc: dict, viewport_aspect: float = 1.0) -> tuple[dict[str, Any], dict[str, Any]]:
    layer_stats, global_bbox = compute_layer_stats(render_doc)
    density_img = rasterize_for_density(render_doc, out_size=512, ignore_layers=DOWNWEIGHT_SET)

    site_bbox, site_conf, site_debug = make_site_plan_bbox(layer_stats, global_bbox, viewport_aspect)
    equip_bbox, equip_conf, equip_debug = make_equipment_layout_bbox(layer_stats, global_bbox, viewport_aspect, density_img=density_img)

    teacher_boxes = {
        PageType.SITE_PLAN.value: {
            "bbox": _bbox_to_list(site_bbox),
            "confidence": round(float(site_conf), 4),
        },
        PageType.EQUIPMENT_LAYOUT.value: {
            "bbox": _bbox_to_list(equip_bbox),
            "confidence": round(float(equip_conf), 4),
        },
    }

    debug_payload = {
        "global_bbox": _bbox_to_list(global_bbox),
        "site_plan": site_debug,
        "equipment_layout": equip_debug,
        "layer_counts": {
            name: stats.count for name, stats in sorted(layer_stats.items(), key=lambda kv: (-kv[1].count, kv[0]))
        },
    }

    return teacher_boxes, debug_payload
