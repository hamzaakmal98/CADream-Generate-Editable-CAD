from __future__ import annotations

import math
from typing import Any

from ml import EQUIPMENT_LAYOUT, SITE_PLAN
from ml.convert import model_bbox_to_img_norm
from ml.density import best_density_window
from ml.layer_stats import BBox, compute_layer_stats
from ml.rasterize import rasterize_render_doc
from ml.rules import normalize
from view_spec_heuristics import HeuristicViewSpecConfig


MIN_LAYER_ENTITIES_SITE = 10
MIN_LAYER_ENTITIES_EQUIP = 5

SITE_PAD_FRAC = 0.10
EQUIP_PAD_FRAC = 0.20

MIN_BOX_AREA_FRAC = 0.01

DOWNWEIGHT_LAYERS = {"shading", "obstruction", "0"}
NOISE_LAYERS_SUBSTR = ["drawing frame", "titleblock", "legend", "text", "annotation", "dimension", "dim", "pub text", "pub dim"]

BOUNDARY_KEYWORDS = ["unit area boundary", "property", "boundary", "parcel", "lot", "easement", "setback"]
SITE_CONTEXT_KEYWORDS = ["base map", "road", "access", "topo", "contour", "ridge"]
EQUIPMENT_KEYWORDS = ["inverter", "module", "transformer", "combiner", "service panel", "switching station", "mounting structure", "equipment", "equip", "electrical", "power", "conduit", "trench", "ductbank", "bess", "battery", "container", "eqpt", "设备", "基础"]
CABLE_KEYWORDS = ["ac cable", "dc cable", "cable path", "conduit", "trench"]
SITE_BOUNDARY_FALLBACK_KEYWORDS = ["property", "boundary", "parcel", "lot", "easement", "setback"]

_cfg = HeuristicViewSpecConfig()
_vx1, _vy1, _vx2, _vy2 = _cfg.viewport_rect
DEFAULT_VIEWPORT_ASPECT = max(0.1, float(_vx2 - _vx1) / max(1e-9, float(_vy2 - _vy1)))


def norm(s: str) -> str:
    return normalize(s)


def contains_any(layer_norm: str, keywords_list: list[str]) -> bool:
    return any(keyword in layer_norm for keyword in keywords_list)


def fit_bbox_to_aspect(b: BBox, aspect: float) -> BBox:
    target = max(1e-6, float(aspect))
    width = max(1e-9, b.width())
    height = max(1e-9, b.height())
    current = width / height

    cx = (b.minx + b.maxx) * 0.5
    cy = (b.miny + b.maxy) * 0.5

    if current < target:
        width = max(width, height * target)
    else:
        height = max(height, width / target)

    return BBox(cx - width * 0.5, cy - height * 0.5, cx + width * 0.5, cy + height * 0.5)


def _union_boxes(items: list[BBox]) -> BBox | None:
    if not items:
        return None
    box = items[0]
    for item in items[1:]:
        box = box.union(item)
    return box


def _collect_layers(stats: dict[str, dict], keywords: list[str], min_count: int) -> tuple[list[str], list[BBox]]:
    names: list[str] = []
    boxes: list[BBox] = []
    for layer_name, payload in stats.items():
        if not contains_any(layer_name, keywords):
            continue
        count = int(payload.get("count", 0))
        bbox = payload.get("bbox")
        if count < min_count or not isinstance(bbox, BBox) or not bbox.is_valid():
            continue
        names.append(layer_name)
        boxes.append(bbox)
    return names, boxes


def _find_exact_layer_bbox(stats: dict[str, dict], exact_name: str) -> tuple[str | None, BBox | None, int]:
    target = norm(exact_name)
    for layer_name, payload in stats.items():
        if layer_name != target:
            continue
        bbox = payload.get("bbox")
        if isinstance(bbox, BBox) and bbox.is_valid():
            return layer_name, bbox, int(payload.get("count", 0))
    return None, None, 0


def _is_noise_or_drawing_frame(layer_name: str) -> bool:
    layer = norm(layer_name)
    if "drawing frame" in layer:
        return True
    return contains_any(layer, NOISE_LAYERS_SUBSTR)


def _collect_non_noise_non_frame_boxes(stats: dict[str, dict]) -> tuple[list[str], list[BBox]]:
    names: list[str] = []
    boxes: list[BBox] = []
    for layer_name, payload in stats.items():
        if _is_noise_or_drawing_frame(layer_name):
            continue
        bbox = payload.get("bbox")
        if not isinstance(bbox, BBox) or not bbox.is_valid():
            continue
        names.append(layer_name)
        boxes.append(bbox)
    return names, boxes


def _intersects(a: BBox, b: BBox) -> bool:
    return not (a.maxx < b.minx or b.maxx < a.minx or a.maxy < b.miny or b.maxy < a.miny)


def _enforce_min_area(bbox: BBox, global_bbox: BBox, aspect: float) -> BBox:
    min_area = max(1e-9, global_bbox.area() * MIN_BOX_AREA_FRAC)
    if bbox.area() >= min_area:
        return bbox
    h = math.sqrt(min_area / max(1e-6, aspect))
    w = h * max(1e-6, aspect)
    cx = (bbox.minx + bbox.maxx) * 0.5
    cy = (bbox.miny + bbox.maxy) * 0.5
    return BBox(cx - w * 0.5, cy - h * 0.5, cx + w * 0.5, cy + h * 0.5)


def teacher_site_plan(stats: dict[str, dict], global_bbox: BBox, viewport_aspect: float) -> tuple[BBox, float, dict]:
    debug: dict[str, Any] = {"used_layers": [], "counts": {}, "strategy": "global"}

    unit_layer, unit_bbox, unit_count = _find_exact_layer_bbox(stats, "Unit Area Boundary")
    if unit_bbox is not None and unit_layer is not None:
        box = fit_bbox_to_aspect(unit_bbox.pad(SITE_PAD_FRAC), viewport_aspect)
        box = _enforce_min_area(box, global_bbox, viewport_aspect)
        debug["used_layers"] = [unit_layer]
        debug["counts"] = {unit_layer: int(unit_count)}
        debug["strategy"] = "unit_area_boundary"
        return box, 0.92, debug

    boundary_names, boundary_boxes = _collect_layers(stats, SITE_BOUNDARY_FALLBACK_KEYWORDS, min_count=1)
    if boundary_boxes:
        box = _union_boxes(boundary_boxes)
        assert box is not None
        box = fit_bbox_to_aspect(box.pad(SITE_PAD_FRAC), viewport_aspect)
        box = _enforce_min_area(box, global_bbox, viewport_aspect)
        debug["used_layers"] = boundary_names
        debug["counts"] = {name: int(stats[name]["count"]) for name in boundary_names}
        debug["strategy"] = "boundary_family"
        return box, 0.84, debug

    clean_names, clean_boxes = _collect_non_noise_non_frame_boxes(stats)
    clean_union = _union_boxes(clean_boxes)
    base = clean_union if clean_union is not None else global_bbox
    box = fit_bbox_to_aspect(base.pad(SITE_PAD_FRAC), viewport_aspect)
    box = _enforce_min_area(box, global_bbox, viewport_aspect)
    debug["used_layers"] = clean_names
    debug["counts"] = {name: int(stats[name]["count"]) for name in clean_names}
    debug["strategy"] = "global_non_noise_non_frame"
    return box, 0.7, debug


def teacher_equipment_layout(stats: dict[str, dict], global_bbox: BBox, viewport_aspect: float, density_img) -> tuple[BBox, float, dict]:
    debug: dict[str, Any] = {"used_layers": [], "counts": {}, "strategy": "density", "density_score": 0.0, "bbox_pre_pad": None, "bbox_post_pad": None}

    equip_names, equip_boxes = _collect_layers(stats, EQUIPMENT_KEYWORDS, min_count=MIN_LAYER_ENTITIES_EQUIP)
    equip_box = _union_boxes(equip_boxes)

    if equip_box is not None:
        expanded = equip_box.pad(0.10)
        cable_names, cable_boxes = _collect_layers(stats, CABLE_KEYWORDS, min_count=MIN_LAYER_ENTITIES_EQUIP)
        used = list(equip_names)
        all_boxes = list(equip_boxes)
        for name, box in zip(cable_names, cable_boxes):
            if _intersects(expanded, box):
                used.append(name)
                all_boxes.append(box)
        chosen = _union_boxes(all_boxes)
        assert chosen is not None
        debug["strategy"] = "equipment_layers"
        debug["used_layers"] = sorted(set(used))
        debug["counts"] = {name: int(stats[name]["count"]) for name in sorted(set(used))}

        confidence = 0.4 + 0.3
        if any("inverter" in name for name in used):
            confidence += 0.1
        if any("module" in name for name in used):
            confidence += 0.1

        debug["bbox_pre_pad"] = [chosen.minx, chosen.miny, chosen.maxx, chosen.maxy]
        chosen = fit_bbox_to_aspect(chosen.pad(EQUIP_PAD_FRAC), viewport_aspect)
        chosen = _enforce_min_area(chosen, global_bbox, viewport_aspect)
        debug["bbox_post_pad"] = [chosen.minx, chosen.miny, chosen.maxx, chosen.maxy]
        return chosen, min(0.95, confidence), debug

    density_norm, density_score = best_density_window(density_img, window_frac=0.25, stride_frac=0.05)
    x1, y1, x2, y2 = density_norm
    gx = global_bbox
    wx1 = gx.minx + x1 * gx.width()
    wx2 = gx.minx + x2 * gx.width()
    wy1 = gx.miny + (1.0 - y1) * gx.height()
    wy2 = gx.miny + (1.0 - y2) * gx.height()
    chosen = BBox(min(wx1, wx2), min(wy1, wy2), max(wx1, wx2), max(wy1, wy2))
    debug["density_score"] = float(density_score)

    confidence = 0.4
    if density_score > 0:
        confidence += 0.1

    debug["bbox_pre_pad"] = [chosen.minx, chosen.miny, chosen.maxx, chosen.maxy]
    chosen = fit_bbox_to_aspect(chosen.pad(EQUIP_PAD_FRAC), viewport_aspect)
    chosen = _enforce_min_area(chosen, global_bbox, viewport_aspect)
    debug["bbox_post_pad"] = [chosen.minx, chosen.miny, chosen.maxx, chosen.maxy]
    return chosen, min(0.9, confidence), debug


def generate_teacher_payload(
    render_doc: dict,
    viewport_aspect: float = DEFAULT_VIEWPORT_ASPECT,
    *,
    stats_override: dict[str, dict] | None = None,
    global_bbox_override: BBox | None = None,
):
    stats, global_bbox = compute_layer_stats(render_doc)
    if isinstance(stats_override, dict):
        stats = stats_override
    if isinstance(global_bbox_override, BBox) and global_bbox_override.is_valid():
        global_bbox = global_bbox_override
    density_img = rasterize_render_doc(render_doc, out_size=512, mode="density")

    site_box, site_conf, site_debug = teacher_site_plan(stats, global_bbox, viewport_aspect)
    equip_box, equip_conf, equip_debug = teacher_equipment_layout(stats, global_bbox, viewport_aspect, density_img)

    teacher_boxes_model = {
        SITE_PLAN: {"bbox": [site_box.minx, site_box.miny, site_box.maxx, site_box.maxy], "confidence": round(float(site_conf), 4)},
        EQUIPMENT_LAYOUT: {"bbox": [equip_box.minx, equip_box.miny, equip_box.maxx, equip_box.maxy], "confidence": round(float(equip_conf), 4)},
    }

    teacher_boxes_img = {
        SITE_PLAN: {"bbox": model_bbox_to_img_norm(site_box, global_bbox), "confidence": round(float(site_conf), 4)},
        EQUIPMENT_LAYOUT: {"bbox": model_bbox_to_img_norm(equip_box, global_bbox), "confidence": round(float(equip_conf), 4)},
    }

    teacher_conf = {
        SITE_PLAN: round(float(site_conf), 4),
        EQUIPMENT_LAYOUT: round(float(equip_conf), 4),
    }

    debug = {
        "viewport_aspect": float(viewport_aspect),
        "global_bbox": [global_bbox.minx, global_bbox.miny, global_bbox.maxx, global_bbox.maxy],
        "site_plan": site_debug,
        "equipment_layout": equip_debug,
        "layer_counts": {name: int(payload["count"]) for name, payload in sorted(stats.items(), key=lambda kv: (-int(kv[1]["count"]), kv[0]))},
    }

    return teacher_boxes_model, teacher_boxes_img, teacher_conf, debug
