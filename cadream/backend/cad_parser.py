from io import BytesIO, StringIO
from typing import Any
import math
import os
import tempfile

import ezdxf
from ezdxf import recover

IGNORE_LAYERS = {
    "Defpoints",
    "DEFPOINTS",
    "Drawing Frame",
    "DRAWING FRAME",
    "BORDER",
    "TITLEBLOCK",
    "Title Block",
}

PREFERRED_LAYERS = {
    "Base Map",
    "Unit Area Boundary",
    "Road",
    "Obstruction",
    "Ridge Line",
    "Switching Station",
    "Mounting Structure",
    "Module",
    "Inverter",
    "Transformer",
    "Combiner Box",
    "Cable Path",
    "AC Cable",
    "DC Cable",
    "Service Panel",
    "Shading",
    "0",
}

MAX_ABS_COORD = 1_000_000_000.0


def _is_finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except Exception:
        return False


def _is_valid_xy(point: Any) -> bool:
    return (
        isinstance(point, list)
        and len(point) >= 2
        and _is_finite_number(point[0])
        and _is_finite_number(point[1])
        and abs(float(point[0])) <= MAX_ABS_COORD
        and abs(float(point[1])) <= MAX_ABS_COORD
    )


def _sanitize_entity(entity: dict[str, Any]) -> dict[str, Any] | None:
    entity_type = entity.get("type")
    if not isinstance(entity_type, str):
        return None

    if entity_type == "LINE":
        if not _is_valid_xy(entity.get("p1")) or not _is_valid_xy(entity.get("p2")):
            return None
        x1, y1 = float(entity["p1"][0]), float(entity["p1"][1])
        x2, y2 = float(entity["p2"][0]), float(entity["p2"][1])
        if x1 == x2 and y1 == y2:
            return None
        entity["p1"] = [x1, y1]
        entity["p2"] = [x2, y2]
        return entity

    if entity_type == "LWPOLYLINE":
        raw_points = entity.get("points")
        if not isinstance(raw_points, list):
            return None
        points: list[list[float]] = []
        for point in raw_points:
            if _is_valid_xy(point):
                points.append([float(point[0]), float(point[1])])
        if len(points) < 2:
            return None
        entity["points"] = points
        return entity

    if entity_type in ("CIRCLE", "ARC"):
        center = entity.get("center")
        radius = entity.get("r")
        if not _is_valid_xy(center) or not _is_finite_number(radius):
            return None
        radius_value = float(radius)
        if radius_value <= 0 or radius_value > MAX_ABS_COORD:
            return None
        entity["center"] = [float(center[0]), float(center[1])]
        entity["r"] = radius_value
        if entity_type == "ARC":
            start_angle = entity.get("start_angle")
            end_angle = entity.get("end_angle")
            if not _is_finite_number(start_angle) or not _is_finite_number(end_angle):
                return None
            entity["start_angle"] = float(start_angle)
            entity["end_angle"] = float(end_angle)
        return entity

    if entity_type in ("TEXT", "MTEXT", "INSERT"):
        pos = entity.get("pos")
        if not _is_valid_xy(pos):
            return None
        entity["pos"] = [float(pos[0]), float(pos[1])]
        return entity

    return None


def _safe_layer(entity: Any) -> str:
    try:
        return entity.dxf.layer
    except Exception:
        return "0"


def polyline_xy_points(polyline_entity: Any) -> list[list[float]]:
    points: list[list[float]] = []

    try:
        for vertex in polyline_entity.vertices:
            location = getattr(vertex.dxf, "location", None)
            if location is not None:
                points.append([location.x, location.y])
    except Exception:
        pass

    if points:
        return points

    try:
        points = [[p[0], p[1]] for p in polyline_entity.points()]
    except Exception:
        points = []

    return points


def _convert_entity(entity: Any, layer: str) -> dict[str, Any] | None:
    entity_type = entity.dxftype()

    if entity_type == "LINE":
        return {
            "type": "LINE",
            "layer": layer,
            "p1": [entity.dxf.start.x, entity.dxf.start.y],
            "p2": [entity.dxf.end.x, entity.dxf.end.y],
        }

    if entity_type == "LWPOLYLINE":
        points = [[p[0], p[1]] for p in entity.get_points("xy")]
        return {
            "type": "LWPOLYLINE",
            "layer": layer,
            "points": points,
            "closed": bool(entity.closed),
        }

    if entity_type == "POLYLINE":
        points = polyline_xy_points(entity)
        if not points:
            return None
        return {
            "type": "LWPOLYLINE",
            "layer": layer,
            "points": points,
            "closed": bool(getattr(entity, "is_closed", False)),
        }

    if entity_type == "CIRCLE":
        return {
            "type": "CIRCLE",
            "layer": layer,
            "center": [entity.dxf.center.x, entity.dxf.center.y],
            "r": float(entity.dxf.radius),
        }

    if entity_type == "ARC":
        return {
            "type": "ARC",
            "layer": layer,
            "center": [entity.dxf.center.x, entity.dxf.center.y],
            "r": float(entity.dxf.radius),
            "start_angle": float(entity.dxf.start_angle),
            "end_angle": float(entity.dxf.end_angle),
        }

    if entity_type in ("TEXT", "MTEXT"):
        text = getattr(entity.dxf, "text", None) or ""
        insert = getattr(entity.dxf, "insert", None)
        position = [insert.x, insert.y] if insert else [0.0, 0.0]
        return {
            "type": entity_type,
            "layer": layer,
            "text": text,
            "pos": position,
            "height": float(getattr(entity.dxf, "height", 10.0) or 10.0),
        }

    if entity_type == "INSERT":
        insert = entity.dxf.insert
        return {
            "type": "INSERT",
            "layer": layer,
            "name": entity.dxf.name,
            "pos": [insert.x, insert.y],
            "rotation": float(getattr(entity.dxf, "rotation", 0.0) or 0.0),
            "xscale": float(getattr(entity.dxf, "xscale", 1.0) or 1.0),
            "yscale": float(getattr(entity.dxf, "yscale", 1.0) or 1.0),
        }

    return None


def _compute_bounds(entities: list[dict[str, Any]]) -> dict[str, list[float]] | None:
    xs: list[float] = []
    ys: list[float] = []

    def add_point(x: float, y: float) -> None:
        xs.append(float(x))
        ys.append(float(y))

    for entity in entities:
        entity_type = entity["type"]

        if entity_type == "LINE":
            add_point(entity["p1"][0], entity["p1"][1])
            add_point(entity["p2"][0], entity["p2"][1])
        elif entity_type == "LWPOLYLINE":
            for point in entity["points"]:
                add_point(point[0], point[1])
        elif entity_type in ("CIRCLE", "ARC"):
            center_x, center_y = entity["center"]
            radius = entity["r"]
            add_point(center_x - radius, center_y - radius)
            add_point(center_x + radius, center_y + radius)
        elif entity_type in ("TEXT", "MTEXT", "INSERT"):
            add_point(entity["pos"][0], entity["pos"][1])

    if not xs or not ys:
        return None

    return {"min": [min(xs), min(ys)], "max": [max(xs), max(ys)]}


def _compute_quantile_bounds(entities: list[dict[str, Any]], low_q: float = 0.01, high_q: float = 0.99) -> dict[str, list[float]] | None:
    xs: list[float] = []
    ys: list[float] = []

    def add_point(x: float, y: float) -> None:
        xs.append(float(x))
        ys.append(float(y))

    for entity in entities:
        entity_type = entity.get("type")

        if entity_type == "LINE":
            add_point(entity["p1"][0], entity["p1"][1])
            add_point(entity["p2"][0], entity["p2"][1])
        elif entity_type == "LWPOLYLINE":
            points = entity.get("points") or []
            for point in points:
                add_point(point[0], point[1])
        elif entity_type in ("CIRCLE", "ARC"):
            center_x, center_y = entity["center"]
            radius = entity["r"]
            add_point(center_x - radius, center_y - radius)
            add_point(center_x + radius, center_y + radius)
        elif entity_type in ("TEXT", "MTEXT", "INSERT"):
            add_point(entity["pos"][0], entity["pos"][1])

    if len(xs) < 10 or len(ys) < 10:
        return None

    xs_sorted = sorted(xs)
    ys_sorted = sorted(ys)

    def q(sorted_values: list[float], quantile: float) -> float:
        index = (len(sorted_values) - 1) * min(1.0, max(0.0, quantile))
        lo = int(math.floor(index))
        hi = int(math.ceil(index))
        if lo == hi:
            return sorted_values[lo]
        t = index - lo
        return sorted_values[lo] * (1.0 - t) + sorted_values[hi] * t

    min_x = q(xs_sorted, low_q)
    max_x = q(xs_sorted, high_q)
    min_y = q(ys_sorted, low_q)
    max_y = q(ys_sorted, high_q)

    if max_x <= min_x or max_y <= min_y:
        return None
    return {"min": [min_x, min_y], "max": [max_x, max_y]}


def dxf_to_render_json(doc: ezdxf.document.Drawing, max_entities: int = 250000) -> dict[str, Any]:
    modelspace = doc.modelspace()

    layers = [
        {
            "name": layer.dxf.name,
            "color": layer.color,
            "linetype": layer.dxf.linetype,
        }
        for layer in doc.layers
    ]

    entities: list[dict[str, Any]] = []

    for entity in modelspace:
        if len(entities) >= max_entities:
            break

        layer = _safe_layer(entity)
        converted = _convert_entity(entity, layer)
        if converted is not None:
            sanitized = _sanitize_entity(converted)
            if sanitized is not None:
                entities.append(sanitized)

    usable = [entity for entity in entities if entity.get("layer", "0") not in IGNORE_LAYERS]
    preferred = [entity for entity in usable if entity.get("layer", "0") in PREFERRED_LAYERS]

    bounds = _compute_bounds(preferred)
    if bounds is None:
        bounds = _compute_bounds(usable)
    if bounds is None:
        bounds = _compute_quantile_bounds(preferred)
    if bounds is None:
        bounds = _compute_quantile_bounds(usable)

    return {"layers": layers, "entities": entities, "bounds": bounds}


def extract_blocks(doc: ezdxf.document.Drawing, max_entities_per_block: int = 20000) -> dict[str, Any]:
    blocks_out: dict[str, Any] = {}

    for block in doc.blocks:
        name = block.name
        if name in ("*Model_Space", "*Paper_Space") or name.startswith("*Paper_Space"):
            continue

        entities: list[dict[str, Any]] = []

        for entity in block:
            if len(entities) >= max_entities_per_block:
                break

            layer = _safe_layer(entity)
            converted = _convert_entity(entity, layer)
            if converted is not None:
                sanitized = _sanitize_entity(converted)
                if sanitized is not None:
                    entities.append(sanitized)

        if entities:
            blocks_out[name] = entities

    return blocks_out


def load_dxf_from_bytes(data: bytes) -> ezdxf.document.Drawing:
    stream = BytesIO(data)
    try:
        return ezdxf.read(stream)
    except Exception:
        temp_fd, temp_path = tempfile.mkstemp(suffix=".dxf")
        try:
            with os.fdopen(temp_fd, "wb") as temp_file:
                temp_file.write(data)

            try:
                return ezdxf.readfile(temp_path)
            except Exception:
                try:
                    document, _auditor = recover.readfile(temp_path)
                    return document
                except Exception:
                    pass
        finally:
            try:
                os.remove(temp_path)
            except FileNotFoundError:
                pass

        for encoding in ("utf-8", "latin-1"):
            try:
                text_stream = StringIO(data.decode(encoding, errors="strict"))
                return ezdxf.read(text_stream)
            except Exception:
                continue

        stream.seek(0)
        try:
            document, _auditor = recover.read(stream)
            return document
        except Exception:
            for encoding in ("utf-8", "latin-1"):
                try:
                    text_stream = StringIO(data.decode(encoding, errors="ignore"))
                    document, _auditor = recover.read(text_stream)
                    return document
                except Exception:
                    continue
            raise
