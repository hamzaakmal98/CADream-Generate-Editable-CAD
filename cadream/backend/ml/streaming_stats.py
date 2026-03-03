from __future__ import annotations

import math
from typing import Any

from ml.layer_stats import BBox
from ml.rasterize import is_noise_layer
from ml.rules import normalize


def _layer_name(entity: Any) -> str:
    try:
        layer = str(entity.dxf.layer)
    except Exception:
        layer = "0"
    return layer or "0"


def _bbox_from_points(points: list[tuple[float, float]]) -> BBox | None:
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    bbox = BBox(min(xs), min(ys), max(xs), max(ys))
    return bbox if bbox.is_valid() else None


def _polyline_points(entity: Any) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []

    try:
        for point in entity.get_points("xy"):
            points.append((float(point[0]), float(point[1])))
        if points:
            return points
    except Exception:
        pass

    try:
        for vertex in entity.vertices:
            location = getattr(vertex.dxf, "location", None)
            if location is not None:
                points.append((float(location.x), float(location.y)))
    except Exception:
        pass

    return points


def _bbox_for_entity(entity: Any) -> BBox | None:
    entity_type = str(entity.dxftype()).upper()

    if entity_type == "LINE":
        try:
            start = entity.dxf.start
            end = entity.dxf.end
            return _bbox_from_points([(float(start.x), float(start.y)), (float(end.x), float(end.y))])
        except Exception:
            return None

    if entity_type in {"LWPOLYLINE", "POLYLINE"}:
        return _bbox_from_points(_polyline_points(entity))

    if entity_type == "CIRCLE":
        try:
            center = entity.dxf.center
            radius = abs(float(entity.dxf.radius))
            if radius <= 0:
                return None
            bbox = BBox(float(center.x) - radius, float(center.y) - radius, float(center.x) + radius, float(center.y) + radius)
            return bbox if bbox.is_valid() else None
        except Exception:
            return None

    if entity_type == "ARC":
        try:
            center = entity.dxf.center
            radius = abs(float(entity.dxf.radius))
            start_angle = float(entity.dxf.start_angle)
            end_angle = float(entity.dxf.end_angle)
            if radius <= 0:
                return None

            def in_arc(angle: float) -> bool:
                start = start_angle % 360.0
                end = end_angle % 360.0
                target = angle % 360.0
                if end < start:
                    end += 360.0
                if target < start:
                    target += 360.0
                return start <= target <= end

            candidate_angles = [start_angle, end_angle, 0.0, 90.0, 180.0, 270.0]
            points: list[tuple[float, float]] = []
            for angle in candidate_angles:
                if angle in (start_angle, end_angle) or in_arc(angle):
                    radians = math.radians(angle)
                    points.append((float(center.x) + radius * math.cos(radians), float(center.y) + radius * math.sin(radians)))
            return _bbox_from_points(points)
        except Exception:
            return None

    if entity_type in {"INSERT", "TEXT", "MTEXT"}:
        try:
            if entity_type == "INSERT":
                insert = entity.dxf.insert
            else:
                insert = getattr(entity.dxf, "insert", None)
                if insert is None:
                    insert = getattr(entity.dxf, "align_point", None)
            if insert is None:
                return None
            x = float(insert.x)
            y = float(insert.y)
            eps = 1e-6
            return BBox(x - eps, y - eps, x + eps, y + eps)
        except Exception:
            return None

    return None


def compute_uncapped_dxf_stats(doc: Any) -> tuple[dict[str, dict[str, Any]], BBox, int]:
    modelspace = doc.modelspace()

    stats: dict[str, dict[str, Any]] = {}
    total_entities = 0

    non_noise_bbox: BBox | None = None
    all_bbox: BBox | None = None

    for entity in modelspace:
        total_entities += 1
        raw_layer = _layer_name(entity)
        layer = normalize(raw_layer)

        if layer not in stats:
            stats[layer] = {"name": raw_layer, "count": 0, "bbox": None}
        stats[layer]["count"] += 1

        bbox = _bbox_for_entity(entity)
        if bbox is None or not bbox.is_valid():
            continue

        existing_bbox = stats[layer]["bbox"]
        stats[layer]["bbox"] = bbox if existing_bbox is None else existing_bbox.union(bbox)

        all_bbox = bbox if all_bbox is None else all_bbox.union(bbox)
        if not is_noise_layer(raw_layer):
            non_noise_bbox = bbox if non_noise_bbox is None else non_noise_bbox.union(bbox)

    global_bbox = non_noise_bbox if non_noise_bbox is not None else all_bbox
    if global_bbox is None or not global_bbox.is_valid():
        raise ValueError("Unable to compute uncapped DXF global bbox")

    return stats, global_bbox, total_entities
