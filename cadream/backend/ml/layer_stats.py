from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from ml.rules import normalize
from ml.rasterize import is_noise_layer


@dataclass
class BBox:
    minx: float
    miny: float
    maxx: float
    maxy: float

    def width(self) -> float:
        return max(0.0, self.maxx - self.minx)

    def height(self) -> float:
        return max(0.0, self.maxy - self.miny)

    def area(self) -> float:
        return self.width() * self.height()

    def union(self, other: "BBox") -> "BBox":
        return BBox(
            min(self.minx, other.minx),
            min(self.miny, other.miny),
            max(self.maxx, other.maxx),
            max(self.maxy, other.maxy),
        )

    def pad(self, p: float) -> "BBox":
        dx = self.width() * max(0.0, float(p))
        dy = self.height() * max(0.0, float(p))
        return BBox(self.minx - dx, self.miny - dy, self.maxx + dx, self.maxy + dy)

    def is_valid(self) -> bool:
        return (
            math.isfinite(self.minx)
            and math.isfinite(self.miny)
            and math.isfinite(self.maxx)
            and math.isfinite(self.maxy)
            and self.maxx > self.minx
            and self.maxy > self.miny
        )


def _is_xy(value: Any) -> bool:
    return isinstance(value, list) and len(value) >= 2 and isinstance(value[0], (int, float)) and isinstance(value[1], (int, float))


def _bbox_from_points(points: list[tuple[float, float]]) -> BBox | None:
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    bbox = BBox(min(xs), min(ys), max(xs), max(ys))
    return bbox if bbox.is_valid() else None


def _angle_in_arc(target_deg: float, start_deg: float, end_deg: float) -> bool:
    start = start_deg % 360.0
    end = end_deg % 360.0
    target = target_deg % 360.0

    if end < start:
        end += 360.0
    if target < start:
        target += 360.0
    return start <= target <= end


def _entity_bbox(entity: dict[str, Any]) -> BBox | None:
    entity_type = str(entity.get("type") or "").upper()

    if entity_type == "LINE":
        p1 = entity.get("p1")
        p2 = entity.get("p2")
        if _is_xy(p1) and _is_xy(p2):
            return _bbox_from_points([(float(p1[0]), float(p1[1])), (float(p2[0]), float(p2[1]))])
        return None

    if entity_type == "LWPOLYLINE":
        raw_points = entity.get("points") if isinstance(entity.get("points"), list) else []
        points = [(float(point[0]), float(point[1])) for point in raw_points if _is_xy(point)]
        return _bbox_from_points(points)

    if entity_type == "CIRCLE":
        center = entity.get("center")
        radius = entity.get("r")
        if _is_xy(center) and isinstance(radius, (int, float)) and float(radius) > 0:
            cx, cy = float(center[0]), float(center[1])
            r = abs(float(radius))
            bbox = BBox(cx - r, cy - r, cx + r, cy + r)
            return bbox if bbox.is_valid() else None
        return None

    if entity_type == "ARC":
        center = entity.get("center")
        radius = entity.get("r")
        start_angle = entity.get("start_angle", 0.0)
        end_angle = entity.get("end_angle", 360.0)
        if _is_xy(center) and isinstance(radius, (int, float)) and float(radius) > 0:
            cx, cy = float(center[0]), float(center[1])
            r = abs(float(radius))
            sa = float(start_angle)
            ea = float(end_angle)

            candidate_angles = [sa, ea, 0.0, 90.0, 180.0, 270.0]
            points: list[tuple[float, float]] = []
            for angle in candidate_angles:
                if angle in (sa, ea) or _angle_in_arc(angle, sa, ea):
                    rad = math.radians(angle)
                    points.append((cx + r * math.cos(rad), cy + r * math.sin(rad)))
            return _bbox_from_points(points)
        return None

    if entity_type in {"INSERT", "TEXT", "MTEXT"}:
        pos = entity.get("pos")
        if _is_xy(pos):
            x, y = float(pos[0]), float(pos[1])
            eps = 1e-6
            return BBox(x - eps, y - eps, x + eps, y + eps)

    return None


def compute_layer_stats(render_doc: dict) -> tuple[dict[str, dict], BBox]:
    """
    Returns:
      stats[layer_norm] = {"name": original, "count": int, "bbox": BBox|None}
      global_bbox: bbox over all NON-NOISE geometry (fallback: all geometry)
    """
    entities = render_doc.get("entities") if isinstance(render_doc, dict) else None
    if not isinstance(entities, list):
        raise ValueError("render_doc must contain entities list")

    stats: dict[str, dict] = {}
    non_noise_bbox: BBox | None = None
    all_bbox: BBox | None = None

    for entity in entities:
        if not isinstance(entity, dict):
            continue

        raw_layer = str(entity.get("layer") or "0")
        layer = normalize(raw_layer)
        if layer not in stats:
            stats[layer] = {"name": raw_layer, "count": 0, "bbox": None}

        stats[layer]["count"] += 1
        bbox = _entity_bbox(entity)
        if bbox is None or not bbox.is_valid():
            continue

        stats[layer]["bbox"] = bbox if stats[layer]["bbox"] is None else stats[layer]["bbox"].union(bbox)
        all_bbox = bbox if all_bbox is None else all_bbox.union(bbox)

        if not is_noise_layer(raw_layer):
            non_noise_bbox = bbox if non_noise_bbox is None else non_noise_bbox.union(bbox)

    global_bbox = non_noise_bbox if non_noise_bbox is not None else all_bbox
    if global_bbox is None or not global_bbox.is_valid():
        raise ValueError("Unable to compute global bbox from render_doc entities")

    return stats, global_bbox
