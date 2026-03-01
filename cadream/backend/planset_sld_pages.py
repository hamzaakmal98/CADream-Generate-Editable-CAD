from __future__ import annotations

from io import BytesIO, StringIO
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import ezdxf

PAGE_24 = 24
PAGE_25 = 25
SHEET_WIDTH = 420.0
SHEET_HEIGHT = 297.0

DRAW_MIN_X = 24.0
DRAW_MAX_X = 312.0
DRAW_MIN_Y = 84.0
DRAW_MAX_Y = 268.0

SYMBOL_BLOCK_MAP: dict[str, str] = {
    "utility-grid": "SLD_UTILITY_GRID",
    "utility-meter": "SLD_UTILITY_METER",
    "main-disconnect": "SLD_MAIN_DISCONNECT",
    "main-distribution-panel": "SLD_MAIN_DISTRIBUTION_PANEL",
    "eqore-computing-unit": "SLD_EQORE_COMPUTING_UNIT",
    "battery-system-electrical-disconnect": "SLD_BATTERY_SYSTEM_ELECTRICAL_DISCONNECT",
    "battery-storage-system-breaker": "SLD_BATTERY_STORAGE_SYSTEM_BREAKER",
    "inverter": "SLD_INVERTER",
    "isolation-transformer": "SLD_ISOLATION_TRANSFORMER",
    "transformer": "SLD_TRANSFORMER",
    "subpanel": "SLD_SUBPANEL_208_120V",
    "bess": "SLD_BESS_GOTION_EDGE_760",
    "load": "SLD_LOAD",
    "current-sensor-input": "SLD_CURRENT_SENSOR_INPUT",
}

SYMBOL_DISPLAY_LABEL: dict[str, str] = {
    "utility-grid": "Utility Grid",
    "utility-meter": "Utility Meter",
    "main-disconnect": "Main Disconnect",
    "main-distribution-panel": "Main Distribution Panel",
    "eqore-computing-unit": "EQORE Computing Unit",
    "battery-system-electrical-disconnect": "Battery System Electrical Disconnect",
    "battery-storage-system-breaker": "Battery Storage System Breaker",
    "inverter": "Inverter",
    "isolation-transformer": "Isolation Transformer",
    "transformer": "Transformer",
    "subpanel": "208/120V Subpanel",
    "bess": "BESS",
    "load": "Load",
    "current-sensor-input": "Current Sensor Input",
}

NODE_HALF_WIDTH = 15.0


def _orthogonal_route(start: tuple[float, float], end: tuple[float, float]) -> list[tuple[float, float]]:
    sx, sy = start
    ex, ey = end

    if abs(sy - ey) < 1e-6:
        return [(sx, sy), (ex, ey)]

    mid_x = (sx + ex) / 2
    return [(sx, sy), (mid_x, sy), (mid_x, ey), (ex, ey)]


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_str(value: Any, default: str = "") -> str:
    if isinstance(value, str) and value.strip():
        return value
    return default


def _normalize_sld_nodes(sld_session: dict[str, Any]) -> list[dict[str, Any]]:
    raw_nodes = sld_session.get("nodes")
    if not isinstance(raw_nodes, list):
        return []

    result: list[dict[str, Any]] = []
    for item in raw_nodes:
        if not isinstance(item, dict):
            continue

        node_id = _safe_str(item.get("id"))
        symbol_type = _safe_str(item.get("symbol_type"))
        label = _safe_str(item.get("label"), SYMBOL_DISPLAY_LABEL.get(symbol_type, "Node"))
        x = _to_float(item.get("x"))
        y = _to_float(item.get("y"))
        rotation = _to_float(item.get("rotation_deg"), 0.0)

        if not node_id:
            continue

        result.append(
            {
                "id": node_id,
                "symbol_type": symbol_type,
                "label": label,
                "x": x,
                "y": y,
                "rotation_deg": rotation,
            }
        )

    return result


def _normalize_sld_edges(sld_session: dict[str, Any]) -> list[dict[str, Any]]:
    raw_edges = sld_session.get("edges")
    if not isinstance(raw_edges, list):
        return []

    result: list[dict[str, Any]] = []
    for item in raw_edges:
        if not isinstance(item, dict):
            continue

        edge_id = _safe_str(item.get("id"))
        from_node_id = _safe_str(item.get("from_node_id"))
        to_node_id = _safe_str(item.get("to_node_id"))
        raw_points = item.get("points")

        points: list[tuple[float, float]] = []
        if isinstance(raw_points, list):
            for point in raw_points:
                if isinstance(point, list) and len(point) >= 2:
                    points.append((_to_float(point[0]), _to_float(point[1])))

        if not edge_id or not from_node_id or not to_node_id:
            continue

        result.append(
            {
                "id": edge_id,
                "from_node_id": from_node_id,
                "to_node_id": to_node_id,
                "points": points,
            }
        )

    return result


def _compute_transform(nodes: list[dict[str, Any]]) -> tuple[float, float, float, float]:
    if not nodes:
        return 0.0, 1.0, 0.0, 1.0

    xs = [node["x"] for node in nodes]
    ys = [node["y"] for node in nodes]

    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)

    return min_x, max_x, min_y, max_y


def _project_point(x: float, y: float, transform: tuple[float, float, float, float]) -> tuple[float, float]:
    min_x, max_x, min_y, max_y = transform

    source_w = max(max_x - min_x, 1.0)
    source_h = max(max_y - min_y, 1.0)

    target_w = DRAW_MAX_X - DRAW_MIN_X
    target_h = DRAW_MAX_Y - DRAW_MIN_Y

    scale = min(target_w / source_w, target_h / source_h)
    fitted_w = source_w * scale
    fitted_h = source_h * scale

    offset_x = DRAW_MIN_X + (target_w - fitted_w) / 2
    offset_y = DRAW_MIN_Y + (target_h - fitted_h) / 2

    tx = offset_x + (x - min_x) * scale
    ty = offset_y + (max_y - y) * scale
    return tx, ty


def _ensure_layer(doc: ezdxf.document.Drawing, layer_name: str, color: int) -> None:
    if layer_name not in doc.layers:
        doc.layers.add(layer_name)
    doc.layers.get(layer_name).dxf.color = color


def _ensure_symbol_block(doc: ezdxf.document.Drawing, block_name: str, display_label: str) -> None:
    if block_name in doc.blocks:
        return

    width = 30.0
    height = 18.0
    block = doc.blocks.new(name=block_name)
    poly = block.add_lwpolyline(
        [(-width / 2, -height / 2), (width / 2, -height / 2), (width / 2, height / 2), (-width / 2, height / 2)],
        dxfattribs={"layer": "0"},
    )
    poly.closed = True
    block.add_text(display_label[:20], dxfattribs={"layer": "0", "height": 2.5}).set_placement((-width / 2 + 1.0, -1.0))


def _draw_page_template(
    layout: Any,
    *,
    border_layer: str,
    title_layer: str,
    project_name: str,
    sheet_number: int,
    sheet_title: str,
) -> None:
    layout.add_lwpolyline(
        [(5.0, 5.0), (SHEET_WIDTH - 5.0, 5.0), (SHEET_WIDTH - 5.0, SHEET_HEIGHT - 5.0), (5.0, SHEET_HEIGHT - 5.0)],
        dxfattribs={"layer": border_layer},
    ).closed = True

    layout.add_lwpolyline(
        [(338.0, 5.0), (SHEET_WIDTH - 5.0, 5.0), (SHEET_WIDTH - 5.0, 70.0), (338.0, 70.0)],
        dxfattribs={"layer": border_layer},
    ).closed = True

    layout.add_text(project_name, dxfattribs={"layer": title_layer, "height": 3.2}).set_placement((342.0, 63.0))
    layout.add_text(f"Sheet: {sheet_number}", dxfattribs={"layer": title_layer, "height": 2.5}).set_placement((342.0, 54.0))
    layout.add_text(sheet_title, dxfattribs={"layer": title_layer, "height": 2.5}).set_placement((342.0, 47.0))
    layout.add_text("Generated by CADream Planset Orchestrator", dxfattribs={"layer": title_layer, "height": 2.0}).set_placement((342.0, 40.0))


def _draw_sld_nodes(
    doc: ezdxf.document.Drawing,
    layout: Any,
    nodes: list[dict[str, Any]],
    node_points: dict[str, tuple[float, float]],
    *,
    equip_layer: str,
    annotation_layer: str,
) -> None:
    for node in nodes:
        symbol_type = node["symbol_type"]
        block_name = SYMBOL_BLOCK_MAP.get(symbol_type, "SLD_GENERIC_NODE")
        display_label = SYMBOL_DISPLAY_LABEL.get(symbol_type, node["label"])
        _ensure_symbol_block(doc, block_name, display_label)

        x, y = node_points[node["id"]]

        ref = layout.add_blockref(block_name, (x, y), dxfattribs={"layer": equip_layer})
        ref.dxf.rotation = _to_float(node.get("rotation_deg"), 0.0)

        annotation = f"{node['label']} ({symbol_type or 'generic'})"
        layout.add_text(annotation[:72], dxfattribs={"layer": annotation_layer, "height": 2.2}).set_placement((x - 18.0, y - 14.0))


def _draw_sld_edges_page_24(
    layout: Any,
    edges: list[dict[str, Any]],
    node_points: dict[str, tuple[float, float]],
    *,
    wire_layer: str,
    annotation_layer: str,
) -> None:
    for index, edge in enumerate(edges, start=1):
        from_center = node_points.get(edge["from_node_id"])
        to_center = node_points.get(edge["to_node_id"])

        from_anchor: tuple[float, float] | None = None
        to_anchor: tuple[float, float] | None = None
        if from_center and to_center:
            left_to_right = to_center[0] >= from_center[0]
            from_anchor = (
                from_center[0] + NODE_HALF_WIDTH if left_to_right else from_center[0] - NODE_HALF_WIDTH,
                from_center[1],
            )
            to_anchor = (
                to_center[0] - NODE_HALF_WIDTH if left_to_right else to_center[0] + NODE_HALF_WIDTH,
                to_center[1],
            )

        if not from_anchor or not to_anchor:
            continue

        polyline_points = _orthogonal_route(from_anchor, to_anchor)

        if len(polyline_points) < 2:
            continue

        layout.add_lwpolyline(polyline_points, dxfattribs={"layer": wire_layer})
        mid_point = polyline_points[len(polyline_points) // 2]
        layout.add_text(f"W-{index:02d}", dxfattribs={"layer": annotation_layer, "height": 2.0}).set_placement(
            (mid_point[0] + 1.5, mid_point[1] + 1.5)
        )


def _draw_sld_edges_page_25(
    layout: Any,
    edges: list[dict[str, Any]],
    node_points: dict[str, tuple[float, float]],
    *,
    wire_layer: str,
    annotation_layer: str,
) -> None:
    offsets = (-1.5, 0.0, 1.5)

    for index, edge in enumerate(edges, start=1):
        from_center = node_points.get(edge["from_node_id"])
        to_center = node_points.get(edge["to_node_id"])

        from_anchor: tuple[float, float] | None = None
        to_anchor: tuple[float, float] | None = None
        if from_center and to_center:
            left_to_right = to_center[0] >= from_center[0]
            from_anchor = (
                from_center[0] + NODE_HALF_WIDTH if left_to_right else from_center[0] - NODE_HALF_WIDTH,
                from_center[1],
            )
            to_anchor = (
                to_center[0] - NODE_HALF_WIDTH if left_to_right else to_center[0] + NODE_HALF_WIDTH,
                to_center[1],
            )

        if not from_anchor or not to_anchor:
            continue

        polyline_points = _orthogonal_route(from_anchor, to_anchor)

        if len(polyline_points) < 2:
            continue

        for offset in offsets:
            shifted = [(x, y + offset) for x, y in polyline_points]
            layout.add_lwpolyline(shifted, dxfattribs={"layer": wire_layer})

        mid_point = polyline_points[len(polyline_points) // 2]
        layout.add_text(f"3PH-W-{index:02d}", dxfattribs={"layer": annotation_layer, "height": 2.0}).set_placement(
            (mid_point[0] + 2.0, mid_point[1] + 2.0)
        )


def _serialize_doc(doc: ezdxf.document.Drawing) -> bytes:
    stream = StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")


def _build_page_doc(
    page_number: int,
    *,
    sheet_title: str,
    project_name: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> bytes:
    doc = ezdxf.new("R2010")
    layout = doc.modelspace()

    border_layer = f"CADREAM-P{page_number}-BORDER"
    equip_layer = f"CADREAM-P{page_number}-EQUIP"
    wire_layer = f"CADREAM-P{page_number}-WIRE"
    annotation_layer = f"CADREAM-P{page_number}-ANNO"
    title_layer = f"CADREAM-P{page_number}-TITLE"

    _ensure_layer(doc, border_layer, 8)
    _ensure_layer(doc, equip_layer, 7)
    _ensure_layer(doc, wire_layer, 3)
    _ensure_layer(doc, annotation_layer, 2)
    _ensure_layer(doc, title_layer, 5)

    _draw_page_template(
        layout,
        border_layer=border_layer,
        title_layer=title_layer,
        project_name=project_name,
        sheet_number=page_number,
        sheet_title=sheet_title,
    )

    transform = _compute_transform(nodes)
    node_points = {node["id"]: _project_point(node["x"], node["y"], transform) for node in nodes}

    _draw_sld_nodes(
        doc,
        layout,
        nodes,
        node_points,
        equip_layer=equip_layer,
        annotation_layer=annotation_layer,
    )

    projected_edges: list[dict[str, Any]] = []
    for edge in edges:
        projected_points = [_project_point(x, y, transform) for x, y in edge["points"]] if edge["points"] else []
        projected_edges.append({**edge, "points": projected_points})

    if page_number == PAGE_24:
        _draw_sld_edges_page_24(
            layout,
            projected_edges,
            node_points,
            wire_layer=wire_layer,
            annotation_layer=annotation_layer,
        )
    else:
        _draw_sld_edges_page_25(
            layout,
            projected_edges,
            node_points,
            wire_layer=wire_layer,
            annotation_layer=annotation_layer,
        )

    return _serialize_doc(doc)


def generate_sld_vertical_slice_pages_24_25(payload: dict[str, Any]) -> dict[str, bytes]:
    sld_session = payload.get("sld_session")
    if not isinstance(sld_session, dict):
        raise ValueError("Missing sld_session in request body")

    nodes = _normalize_sld_nodes(sld_session)
    edges = _normalize_sld_edges(sld_session)

    if not nodes:
        raise ValueError("SLD session has no nodes; cannot generate pages 24/25")

    title_block = payload.get("title_block") if isinstance(payload.get("title_block"), dict) else {}
    project_name = _safe_str(title_block.get("project_name"), "CADream SLD Vertical Slice")

    page_24 = _build_page_doc(
        PAGE_24,
        sheet_title="Single Line Diagram",
        project_name=project_name,
        nodes=nodes,
        edges=edges,
    )

    page_25 = _build_page_doc(
        PAGE_25,
        sheet_title="Three Line Diagram",
        project_name=project_name,
        nodes=nodes,
        edges=edges,
    )

    return {
        "page24.dxf": page_24,
        "page25.dxf": page_25,
    }


def export_sld_vertical_slice_zip(payload: dict[str, Any]) -> bytes:
    pages = generate_sld_vertical_slice_pages_24_25(payload)

    zip_stream = BytesIO()
    with ZipFile(zip_stream, mode="w", compression=ZIP_DEFLATED) as archive:
        for file_name, content in pages.items():
            archive.writestr(file_name, content)

    return zip_stream.getvalue()
