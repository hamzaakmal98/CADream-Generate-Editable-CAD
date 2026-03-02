from __future__ import annotations

from io import StringIO
from typing import Any

import ezdxf
from cad_parser import load_dxf_from_bytes


def _layer_name_from_id(layer_id: str) -> str:
    if layer_id.startswith("layer:"):
        return layer_id.split(":", 1)[1] or "0"
    return layer_id or "0"


def _lineweight_to_dxf(value: Any) -> int | None:
    if value == "bylayer":
        return -1
    if value == "byblock":
        return -2
    if isinstance(value, (int, float)):
        return int(value)
    return None


def _color_to_dxf_attribs(color: Any) -> dict[str, Any]:
    if not isinstance(color, dict):
        return {}

    mode = color.get("mode")
    if mode == "bylayer":
        return {"color": 256}
    if mode == "byblock":
        return {"color": 0}
    if mode == "aci" and isinstance(color.get("aci"), int):
        return {"color": int(color["aci"])}
    if mode == "rgb" and isinstance(color.get("rgb"), list) and len(color["rgb"]) == 3:
        r, g, b = color["rgb"]
        if all(isinstance(v, int) and 0 <= v <= 255 for v in [r, g, b]):
            return {"true_color": (r << 16) + (g << 8) + b}

    return {}


def _linetype_to_dxf(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}

    mode = value.get("mode")
    if mode == "bylayer":
        return {"linetype": "BYLAYER"}
    if mode == "byblock":
        return {"linetype": "BYBLOCK"}
    if mode == "named" and isinstance(value.get("name"), str):
        return {"linetype": value["name"]}

    return {}


def _entity_dxfattribs(
    entity: dict[str, Any],
    layer_lookup: dict[str, str],
    allowed_layers_lower: set[str],
) -> dict[str, Any]:
    layer_id = entity.get("layerId")
    layer_name = layer_lookup.get(layer_id, _layer_name_from_id(layer_id if isinstance(layer_id, str) else "0"))
    if layer_name.lower() not in allowed_layers_lower:
        layer_name = "0"

    dxfattribs: dict[str, Any] = {"layer": layer_name}
    dxfattribs.update(_color_to_dxf_attribs(entity.get("color")))
    dxfattribs.update(_linetype_to_dxf(entity.get("linetype")))

    lw = _lineweight_to_dxf(entity.get("lineweight"))
    if lw is not None:
        dxfattribs["lineweight"] = lw

    return dxfattribs


def _to_xy_pair(value: Any) -> tuple[float, float]:
    if isinstance(value, list) and len(value) >= 2:
        return float(value[0]), float(value[1])
    return 0.0, 0.0


def _add_entity_to_layout(
    layout: Any,
    entity: dict[str, Any],
    layer_lookup: dict[str, str],
    allowed_layers_lower: set[str],
) -> None:
    entity_type = entity.get("type")
    dxfattribs = _entity_dxfattribs(entity, layer_lookup, allowed_layers_lower)

    if entity_type == "LINE":
        start = _to_xy_pair(entity.get("start"))
        end = _to_xy_pair(entity.get("end"))
        layout.add_line(start, end, dxfattribs=dxfattribs)
        return

    if entity_type == "LWPOLYLINE":
        vertices = entity.get("vertices") or []
        points: list[tuple[float, float, float]] = []
        for vertex in vertices:
            if not isinstance(vertex, dict):
                continue
            x = float(vertex.get("x", 0.0))
            y = float(vertex.get("y", 0.0))
            bulge = float(vertex.get("bulge", 0.0) or 0.0)
            points.append((x, y, bulge))

        if points:
            poly = layout.add_lwpolyline(points, format="xyb", dxfattribs=dxfattribs)
            if bool(entity.get("closed")):
                poly.closed = True
        return

    if entity_type == "CIRCLE":
        center = _to_xy_pair(entity.get("center"))
        radius = float(entity.get("radius", 0.0))
        layout.add_circle(center, radius, dxfattribs=dxfattribs)
        return

    if entity_type == "ARC":
        center = _to_xy_pair(entity.get("center"))
        radius = float(entity.get("radius", 0.0))
        start_angle = float(entity.get("startAngleDeg", 0.0))
        end_angle = float(entity.get("endAngleDeg", 0.0))
        layout.add_arc(center, radius, start_angle, end_angle, dxfattribs=dxfattribs)
        return

    if entity_type in ("TEXT", "MTEXT"):
        text_value = str(entity.get("text", ""))
        height = float(entity.get("height", 2.5))
        insertion = _to_xy_pair(entity.get("insertionPoint"))

        if entity_type == "TEXT":
            text_entity = layout.add_text(text_value, dxfattribs={**dxfattribs, "height": height})
            text_entity.set_placement(insertion)
        else:
            mtext = layout.add_mtext(text_value, dxfattribs={**dxfattribs, "char_height": height})
            mtext.set_location(insertion)
        return

    if entity_type == "INSERT":
        block_name = entity.get("blockName")
        if not isinstance(block_name, str) or not block_name:
            return

        insertion = _to_xy_pair(entity.get("insertionPoint"))
        insert = layout.add_blockref(block_name, insertion, dxfattribs=dxfattribs)
        insert.dxf.rotation = float(entity.get("rotationDeg", 0.0) or 0.0)
        insert.dxf.xscale = float(entity.get("xScale", 1.0) or 1.0)
        insert.dxf.yscale = float(entity.get("yScale", 1.0) or 1.0)

        z_scale = entity.get("zScale")
        if isinstance(z_scale, (int, float)):
            insert.dxf.zscale = float(z_scale)

        for attrib in entity.get("attributes") or []:
            if not isinstance(attrib, dict):
                continue
            tag = attrib.get("tag")
            text = attrib.get("text")
            if isinstance(tag, str) and isinstance(text, str):
                insert.add_attrib(tag, text)


def export_dxf_from_cad_ir(cad_ir: dict[str, Any]) -> bytes:
    if not isinstance(cad_ir, dict):
        raise ValueError("Invalid CAD IR payload: expected object")

    if cad_ir.get("schemaVersion") != "cad-ir-v1":
        raise ValueError("Unsupported CAD IR schema version")

    doc = ezdxf.new("R2010")
    modelspace = doc.modelspace()

    layers = cad_ir.get("layers")
    layer_lookup: dict[str, str] = {}
    allowed_layers_lower: set[str] = {"0"}

    if isinstance(layers, list):
        for layer in layers:
            if not isinstance(layer, dict):
                continue
            layer_id = layer.get("id")
            layer_name = layer.get("name")
            if not isinstance(layer_id, str) or not isinstance(layer_name, str) or not layer_name:
                continue

            layer_lookup[layer_id] = layer_name
            allowed_layers_lower.add(layer_name.lower())
            if layer_name not in doc.layers:
                doc.layers.add(layer_name)

    entities_by_id = cad_ir.get("entitiesById")
    if not isinstance(entities_by_id, dict):
        raise ValueError("Invalid CAD IR: entitiesById missing")

    blocks = cad_ir.get("blocksByName")
    if isinstance(blocks, dict):
        for block_name, block_def in blocks.items():
            if not isinstance(block_name, str) or not block_name:
                continue
            if block_name in doc.blocks:
                continue

            block_layout = doc.blocks.new(name=block_name)

            entity_ids = []
            if isinstance(block_def, dict):
                raw_ids = block_def.get("entityIds")
                if isinstance(raw_ids, list):
                    entity_ids = [eid for eid in raw_ids if isinstance(eid, str)]

            for entity_id in entity_ids:
                entity = entities_by_id.get(entity_id)
                if isinstance(entity, dict):
                    _add_entity_to_layout(block_layout, entity, layer_lookup, allowed_layers_lower)

    model_ids_raw = cad_ir.get("modelSpaceEntityIds")
    model_ids = [eid for eid in model_ids_raw if isinstance(eid, str)] if isinstance(model_ids_raw, list) else []

    for entity_id in model_ids:
        entity = entities_by_id.get(entity_id)
        if isinstance(entity, dict):
            _add_entity_to_layout(modelspace, entity, layer_lookup, allowed_layers_lower)

    site_plan = cad_ir.get("sitePlan")
    if isinstance(site_plan, dict):
        _append_site_plan_to_layout(doc, modelspace, site_plan)

    stream = StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")


def _ensure_layer(doc: ezdxf.document.Drawing, layer_name: str) -> str:
    if layer_name not in doc.layers:
        doc.layers.add(layer_name)
    return layer_name


def _safe_scale(value: Any) -> float:
    try:
        scale = float(value)
    except (TypeError, ValueError):
        return 1.0
    return scale if abs(scale) > 1e-6 else 1.0


def _ensure_generic_bess_block(doc: ezdxf.document.Drawing) -> str:
    block_name = "CADREAM_BESS_GENERIC"
    if block_name in doc.blocks:
        return block_name

    block = doc.blocks.new(name=block_name)
    body = [(-15.0, -10.0), (15.0, -10.0), (15.0, 10.0), (-15.0, 10.0)]
    poly = block.add_lwpolyline(body, dxfattribs={"layer": "0"})
    poly.closed = True
    block.add_line((-10.0, 0.0), (10.0, 0.0), dxfattribs={"layer": "0"})
    block.add_line((0.0, -6.0), (0.0, 6.0), dxfattribs={"layer": "0"})
    return block_name


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _add_bess_marker(layout: Any, x: float, y: float, layer_name: str) -> None:
    marker_radius = 20.0
    marker_arm = 14.0
    marker_attribs = {"layer": layer_name, "color": 3}
    layout.add_circle((x, y), marker_radius, dxfattribs=marker_attribs)
    layout.add_line((x - marker_arm, y), (x + marker_arm, y), dxfattribs=marker_attribs)
    layout.add_line((x, y - marker_arm), (x, y + marker_arm), dxfattribs=marker_attribs)


def _append_site_plan_to_layout(
    doc: ezdxf.document.Drawing,
    layout: Any,
    site_plan: dict[str, Any],
    *,
    bess_layer: str = "CADREAM_BESS",
    cable_layer: str = "CADREAM_CABLE",
) -> None:
    if not isinstance(site_plan, dict):
        return

    entities = site_plan.get("entities")
    if not isinstance(entities, dict):
        return

    _ensure_layer(doc, bess_layer)
    _ensure_layer(doc, cable_layer)
    if bess_layer in doc.layers:
        doc.layers.get(bess_layer).dxf.color = 3
    generic_bess_block = _ensure_generic_bess_block(doc)

    bess_items = entities.get("bess") if isinstance(entities.get("bess"), list) else []
    for bess in bess_items:
        if not isinstance(bess, dict):
            continue

        pos = bess.get("position") if isinstance(bess.get("position"), dict) else bess.get("cad_position")
        if not isinstance(pos, dict):
            continue

        ins = bess.get("insert") if isinstance(bess.get("insert"), dict) else bess.get("cad_insert")
        x = _to_float(pos.get("x"), 0.0)
        y = _to_float(pos.get("y"), 0.0)

        block_name = ins.get("blockName") if isinstance(ins, dict) else None
        if not isinstance(block_name, str) and isinstance(ins, dict):
            block_name = ins.get("block_name")

        rotation = _to_float(ins.get("rotationDeg"), 0.0) if isinstance(ins, dict) else 0.0
        if isinstance(ins, dict) and "rotationDeg" not in ins:
            rotation = _to_float(ins.get("rotation"), 0.0)

        xscale = _safe_scale(ins.get("xScale", ins.get("xscale", 1.0)) if isinstance(ins, dict) else 1.0)
        yscale = _safe_scale(ins.get("yScale", ins.get("yscale", 1.0)) if isinstance(ins, dict) else 1.0)

        inserted_source_block = False
        if isinstance(block_name, str) and block_name in doc.blocks:
            ref = layout.add_blockref(block_name, (x, y), dxfattribs={"layer": bess_layer, "color": 3})
            ref.dxf.rotation = rotation
            ref.dxf.xscale = xscale
            ref.dxf.yscale = yscale
            inserted_source_block = True

        if not inserted_source_block:
            generic_ref = layout.add_blockref(generic_bess_block, (x, y), dxfattribs={"layer": bess_layer, "color": 3})
            generic_ref.dxf.rotation = rotation
            generic_ref.dxf.xscale = xscale
            generic_ref.dxf.yscale = yscale

        _add_bess_marker(layout, x, y, bess_layer)

    cable_paths = entities.get("cablePaths") if isinstance(entities.get("cablePaths"), list) else entities.get("cable_paths")
    cable_items = cable_paths if isinstance(cable_paths, list) else []
    for cable in cable_items:
        if not isinstance(cable, dict):
            continue
        points = cable.get("points")
        if not isinstance(points, list):
            continue

        xy_points: list[tuple[float, float]] = []
        for point in points:
            if isinstance(point, dict):
                xy_points.append((_to_float(point.get("x"), 0.0), _to_float(point.get("y"), 0.0)))
            elif isinstance(point, list) and len(point) >= 2:
                xy_points.append((_to_float(point[0], 0.0), _to_float(point[1], 0.0)))

        if len(xy_points) >= 2:
            layout.add_lwpolyline(xy_points, dxfattribs={"layer": cable_layer})


def export_dxf_from_source_bytes(source_bytes: bytes, site_placements: dict[str, Any]) -> bytes:
    doc = load_dxf_from_bytes(source_bytes)
    modelspace = doc.modelspace()

    entities = site_placements.get("entities") if isinstance(site_placements, dict) else None
    if not isinstance(entities, dict):
        raise ValueError("Invalid site_placements payload")

    _append_site_plan_to_layout(doc, modelspace, {"entities": entities})

    stream = StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")
