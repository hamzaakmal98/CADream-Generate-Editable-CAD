from collections import Counter
from io import BytesIO
from typing import Any

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
            entities.append(converted)

    usable = [entity for entity in entities if entity.get("layer", "0") not in IGNORE_LAYERS]
    preferred = [entity for entity in usable if entity.get("layer", "0") in PREFERRED_LAYERS]

    bounds = _compute_bounds(preferred)
    if bounds is None:
        bounds = _compute_bounds(usable)

    type_counts = Counter([entity["type"] for entity in entities])
    print("ENTITY COUNTS:", type_counts)

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
                entities.append(converted)

        if entities:
            blocks_out[name] = entities

    return blocks_out


def load_dxf_from_bytes(data: bytes) -> ezdxf.document.Drawing:
    stream = BytesIO(data)
    try:
        return ezdxf.read(stream)
    except Exception:
        stream.seek(0)
        document, _auditor = recover.read(stream)
        return document
