from __future__ import annotations

from io import BytesIO, StringIO
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import ezdxf
from ezdxf.enums import TextEntityAlignment

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
CANVAS_NODE_HEIGHT = 64.0

SYMBOL_CANVAS_WIDTH: dict[str, float] = {
    "utility-grid": 96.0,
    "utility-meter": 96.0,
    "main-disconnect": 130.0,
    "main-distribution-panel": 150.0,
    "eqore-computing-unit": 160.0,
    "battery-system-electrical-disconnect": 190.0,
    "battery-storage-system-breaker": 180.0,
    "inverter": 108.0,
    "isolation-transformer": 146.0,
    "transformer": 110.0,
    "subpanel": 130.0,
    "bess": 110.0,
    "load": 92.0,
    "current-sensor-input": 150.0,
}

SYMBOL_BLOCK_HALF_WIDTH: dict[str, float] = {
    "utility-grid": 8.5,
    "load": 8.5,
}


def _orthogonal_route(start: tuple[float, float], end: tuple[float, float]) -> list[tuple[float, float]]:
    sx, sy = start
    ex, ey = end

    if abs(sy - ey) < 1e-6:
        return [(sx, sy), (ex, ey)]

    mid_x = (sx + ex) / 2
    return [(sx, sy), (mid_x, sy), (mid_x, ey), (ex, ey)]


def _orthogonalize_polyline(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(points) < 2:
        return points

    output: list[tuple[float, float]] = [points[0]]
    for next_point in points[1:]:
        prev_x, prev_y = output[-1]
        next_x, next_y = next_point

        if abs(prev_x - next_x) < 1e-6 or abs(prev_y - next_y) < 1e-6:
            output.append((next_x, next_y))
            continue

        output.append((next_x, prev_y))
        output.append((next_x, next_y))

    deduped: list[tuple[float, float]] = [output[0]]
    for point in output[1:]:
        if abs(point[0] - deduped[-1][0]) > 1e-6 or abs(point[1] - deduped[-1][1]) > 1e-6:
            deduped.append(point)

    return deduped


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

    min_x = float("inf")
    max_x = float("-inf")
    min_y = float("inf")
    max_y = float("-inf")

    for node in nodes:
        symbol_type = _safe_str(node.get("symbol_type"))
        node_width = SYMBOL_CANVAS_WIDTH.get(symbol_type, 120.0)
        node_x = _to_float(node.get("x"))
        node_y = _to_float(node.get("y"))

        min_x = min(min_x, node_x)
        max_x = max(max_x, node_x + node_width)
        min_y = min(min_y, node_y)
        max_y = max(max_y, node_y + CANVAS_NODE_HEIGHT)

    if min_x == float("inf") or min_y == float("inf"):
        return 0.0, 1.0, 0.0, 1.0

    return min_x, max_x, min_y, max_y


def _compute_transform_with_edges(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> tuple[float, float, float, float]:
    min_x, max_x, min_y, max_y = _compute_transform(nodes)

    for edge in edges:
        points = edge.get("points")
        if not isinstance(points, list):
            continue
        for point in points:
            if not isinstance(point, tuple) or len(point) < 2:
                continue
            px, py = point
            min_x = min(min_x, px)
            max_x = max(max_x, px)
            min_y = min(min_y, py)
            max_y = max(max_y, py)

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


def _fit_text_height(
    text: str,
    *,
    max_width: float,
    max_height: float,
    default_height: float,
    min_height: float = 0.55,
) -> float:
    safe_text = text.strip()
    if not safe_text:
        return max(min_height, min(default_height, max_height))

    estimated_char_width_factor = 0.72
    width_limited = max_width / max(len(safe_text) * estimated_char_width_factor, 1.0)
    fitted = min(default_height, max_height, width_limited)
    return max(min_height, fitted * 0.9)


def _split_label_two_lines(text: str) -> tuple[str, str] | None:
    words = [part for part in text.strip().split(" ") if part]
    if len(words) < 2:
        return None

    best: tuple[str, str] | None = None
    best_delta = float("inf")
    for idx in range(1, len(words)):
        left = " ".join(words[:idx]).strip()
        right = " ".join(words[idx:]).strip()
        if not left or not right:
            continue
        delta = abs(len(left) - len(right))
        if delta < best_delta:
            best_delta = delta
            best = (left, right)

    return best


def _add_fitted_symbol_text(
    block: Any,
    text: str,
    *,
    max_width: float,
    max_height: float,
    default_height: float,
) -> None:
    label = text.strip()
    if not label:
        return

    single_height = _fit_text_height(
        label,
        max_width=max_width,
        max_height=max_height,
        default_height=default_height,
    )
    single_width_ratio = (len(label) * single_height * 0.72) / max(max_width, 1.0)

    split = _split_label_two_lines(label)
    if split is None:
        block.add_text(label, dxfattribs={"layer": "0", "height": single_height}).set_placement(
            (0.0, 0.0), align=TextEntityAlignment.MIDDLE_CENTER
        )
        return

    line_1, line_2 = split
    per_line_height_limit = max_height * 0.46
    line_height = min(
        _fit_text_height(line_1, max_width=max_width, max_height=per_line_height_limit, default_height=default_height),
        _fit_text_height(line_2, max_width=max_width, max_height=per_line_height_limit, default_height=default_height),
    )

    should_prefer_multiline = len(label) >= 18 or single_width_ratio >= 0.8
    if line_height <= single_height * 1.05 and not should_prefer_multiline:
        block.add_text(label, dxfattribs={"layer": "0", "height": single_height}).set_placement(
            (0.0, 0.0), align=TextEntityAlignment.MIDDLE_CENTER
        )
        return

    line_gap = line_height * 0.45
    y_offset = (line_height + line_gap) / 2

    block.add_text(line_1, dxfattribs={"layer": "0", "height": line_height}).set_placement(
        (0.0, y_offset), align=TextEntityAlignment.MIDDLE_CENTER
    )
    block.add_text(line_2, dxfattribs={"layer": "0", "height": line_height}).set_placement(
        (0.0, -y_offset), align=TextEntityAlignment.MIDDLE_CENTER
    )


def _route_with_straight_preference(
    from_anchor: tuple[float, float],
    to_anchor: tuple[float, float],
    points: Any,
) -> list[tuple[float, float]]:
    if abs(from_anchor[1] - to_anchor[1]) < 1e-6:
        return [from_anchor, to_anchor]

    if isinstance(points, list) and len(points) >= 2:
        polyline_points = list(points)
        polyline_points[0] = from_anchor
        polyline_points[-1] = to_anchor
        return polyline_points

    return _orthogonal_route(from_anchor, to_anchor)


def _ensure_symbol_block(doc: ezdxf.document.Drawing, block_name: str, display_label: str, symbol_type: str) -> None:
    if block_name in doc.blocks:
        return

    width = 30.0
    height = 18.0
    block = doc.blocks.new(name=block_name)

    if symbol_type in {"utility-grid", "load"}:
        radius = 8.5
        block.add_circle((0.0, 0.0), radius, dxfattribs={"layer": "0"})
        _add_fitted_symbol_text(
            block,
            display_label,
            max_width=radius * 1.7,
            max_height=radius * 0.9,
            default_height=1.6,
        )
        return

    poly = block.add_lwpolyline(
        [(-width / 2, -height / 2), (width / 2, -height / 2), (width / 2, height / 2), (-width / 2, height / 2)],
        dxfattribs={"layer": "0"},
    )
    poly.closed = True
    _add_fitted_symbol_text(
        block,
        display_label,
        max_width=width - 2.0,
        max_height=height - 2.0,
        default_height=1.8,
    )


def _node_block_half_width(symbol_type: str) -> float:
    return SYMBOL_BLOCK_HALF_WIDTH.get(symbol_type, NODE_HALF_WIDTH)


def _anchor_point(
    center: tuple[float, float],
    symbol_type: str,
    toward_x: float,
) -> tuple[float, float]:
    half_width = _node_block_half_width(symbol_type)
    cx, cy = center
    return (cx + half_width if toward_x >= cx else cx - half_width, cy)


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
) -> None:
    for node in nodes:
        symbol_type = node["symbol_type"]
        block_name = SYMBOL_BLOCK_MAP.get(symbol_type, "SLD_GENERIC_NODE")
        display_label = SYMBOL_DISPLAY_LABEL.get(symbol_type, node["label"])
        _ensure_symbol_block(doc, block_name, display_label, symbol_type)

        x, y = node_points[node["id"]]

        ref = layout.add_blockref(block_name, (x, y), dxfattribs={"layer": equip_layer})
        ref.dxf.rotation = _to_float(node.get("rotation_deg"), 0.0)


def _draw_sld_edges_page_24(
    layout: Any,
    edges: list[dict[str, Any]],
    node_points: dict[str, tuple[float, float]],
    node_symbol_types: dict[str, str],
    *,
    wire_layer: str,
) -> None:
    for edge in edges:
        from_center = node_points.get(edge["from_node_id"])
        to_center = node_points.get(edge["to_node_id"])

        from_anchor: tuple[float, float] | None = None
        to_anchor: tuple[float, float] | None = None
        if from_center and to_center:
            points = edge["points"]
            start_toward_x = to_center[0]
            end_toward_x = from_center[0]
            if isinstance(points, list) and len(points) >= 2:
                start_toward_x = points[1][0]
                end_toward_x = points[-2][0]

            from_anchor = _anchor_point(
                from_center,
                node_symbol_types.get(edge["from_node_id"], ""),
                start_toward_x,
            )
            to_anchor = _anchor_point(
                to_center,
                node_symbol_types.get(edge["to_node_id"], ""),
                end_toward_x,
            )

        if not from_anchor or not to_anchor:
            continue

        points = edge["points"]
        polyline_points = _route_with_straight_preference(from_anchor, to_anchor, points)

        polyline_points = _orthogonalize_polyline(polyline_points)

        if len(polyline_points) < 2:
            continue

        layout.add_lwpolyline(polyline_points, dxfattribs={"layer": wire_layer})


def _draw_sld_edges_page_25(
    layout: Any,
    edges: list[dict[str, Any]],
    node_points: dict[str, tuple[float, float]],
    node_symbol_types: dict[str, str],
    *,
    wire_layer: str,
) -> None:
    offsets = (-1.5, 0.0, 1.5)

    for edge in edges:
        from_center = node_points.get(edge["from_node_id"])
        to_center = node_points.get(edge["to_node_id"])

        from_anchor: tuple[float, float] | None = None
        to_anchor: tuple[float, float] | None = None
        if from_center and to_center:
            points = edge["points"]
            start_toward_x = to_center[0]
            end_toward_x = from_center[0]
            if isinstance(points, list) and len(points) >= 2:
                start_toward_x = points[1][0]
                end_toward_x = points[-2][0]

            from_anchor = _anchor_point(
                from_center,
                node_symbol_types.get(edge["from_node_id"], ""),
                start_toward_x,
            )
            to_anchor = _anchor_point(
                to_center,
                node_symbol_types.get(edge["to_node_id"], ""),
                end_toward_x,
            )

        if not from_anchor or not to_anchor:
            continue

        points = edge["points"]
        polyline_points = _route_with_straight_preference(from_anchor, to_anchor, points)

        polyline_points = _orthogonalize_polyline(polyline_points)

        if len(polyline_points) < 2:
            continue

        for offset in offsets:
            shifted = [(x, y + offset) for x, y in polyline_points]
            layout.add_lwpolyline(shifted, dxfattribs={"layer": wire_layer})


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
    title_layer = f"CADREAM-P{page_number}-TITLE"

    _ensure_layer(doc, border_layer, 8)
    _ensure_layer(doc, equip_layer, 7)
    _ensure_layer(doc, wire_layer, 3)
    _ensure_layer(doc, title_layer, 5)

    _draw_page_template(
        layout,
        border_layer=border_layer,
        title_layer=title_layer,
        project_name=project_name,
        sheet_number=page_number,
        sheet_title=sheet_title,
    )

    transform = _compute_transform_with_edges(nodes, edges)

    node_points: dict[str, tuple[float, float]] = {}
    node_symbol_types: dict[str, str] = {}
    for node in nodes:
        symbol_type = _safe_str(node.get("symbol_type"))
        source_width = SYMBOL_CANVAS_WIDTH.get(symbol_type, 120.0)
        center_x = node["x"] + source_width / 2
        center_y = node["y"] + CANVAS_NODE_HEIGHT / 2
        node_points[node["id"]] = _project_point(center_x, center_y, transform)
        node_symbol_types[node["id"]] = symbol_type

    _draw_sld_nodes(
        doc,
        layout,
        nodes,
        node_points,
        equip_layer=equip_layer,
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
            node_symbol_types,
            wire_layer=wire_layer,
        )
    else:
        _draw_sld_edges_page_25(
            layout,
            projected_edges,
            node_points,
            node_symbol_types,
            wire_layer=wire_layer,
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


def generate_sld_pages_pdf(payload: dict[str, Any]) -> bytes:
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as rl_canvas

    sld_session = payload.get("sld_session")
    if not isinstance(sld_session, dict):
        raise ValueError("Missing sld_session in request body")

    nodes = _normalize_sld_nodes(sld_session)
    edges = _normalize_sld_edges(sld_session)

    if not nodes:
        raise ValueError("SLD session has no nodes; cannot generate PDF")

    title_block = payload.get("title_block") if isinstance(payload.get("title_block"), dict) else {}
    project_name = _safe_str(title_block.get("project_name"), "CADream SLD")

    transform = _compute_transform_with_edges(nodes, edges)

    node_points: dict[str, tuple[float, float]] = {}
    node_symbol_types: dict[str, str] = {}
    for node in nodes:
        symbol_type = _safe_str(node.get("symbol_type"))
        source_width = SYMBOL_CANVAS_WIDTH.get(symbol_type, 120.0)
        center_x = node["x"] + source_width / 2
        center_y = node["y"] + CANVAS_NODE_HEIGHT / 2
        node_points[node["id"]] = _project_point(center_x, center_y, transform)
        node_symbol_types[node["id"]] = symbol_type

    projected_edges: list[dict[str, Any]] = []
    for edge in edges:
        projected_points = [_project_point(x, y, transform) for x, y in edge["points"]] if edge["points"] else []
        projected_edges.append({**edge, "points": projected_points})

    page_size = landscape(A3)
    stream = BytesIO()
    pdf = rl_canvas.Canvas(stream, pagesize=page_size)

    tb_left_mm = 338.0

    for page_num in [PAGE_24, PAGE_25]:
        sheet_title = "Single Line Diagram" if page_num == PAGE_24 else "Three Line Diagram"
        three_line = page_num == PAGE_25

        pdf.setLineWidth(0.5)
        pdf.rect(5 * mm, 5 * mm, (SHEET_WIDTH - 10) * mm, (SHEET_HEIGHT - 10) * mm)

        pdf.line(tb_left_mm * mm, 5 * mm, tb_left_mm * mm, (SHEET_HEIGHT - 5) * mm)
        pdf.rect(tb_left_mm * mm, 5 * mm, (SHEET_WIDTH - tb_left_mm - 5) * mm, 65 * mm)

        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString((tb_left_mm + 2) * mm, 63 * mm, project_name[:50])
        pdf.setFont("Helvetica", 7)
        pdf.drawString((tb_left_mm + 2) * mm, 54 * mm, f"Sheet: {page_num}")
        pdf.drawString((tb_left_mm + 2) * mm, 47 * mm, sheet_title)
        pdf.drawString((tb_left_mm + 2) * mm, 40 * mm, "Generated by CADream Planset Orchestrator")

        content_cx = (DRAW_MIN_X + tb_left_mm) / 2
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawCentredString(content_cx * mm, (SHEET_HEIGHT - 12) * mm, sheet_title)

        pdf.setLineWidth(0.7)
        for node in nodes:
            symbol_type = node["symbol_type"]
            display_label = SYMBOL_DISPLAY_LABEL.get(symbol_type, node["label"])
            x_mm, y_mm = node_points[node["id"]]
            px = x_mm * mm
            py = y_mm * mm

            if symbol_type in {"utility-grid", "load"}:
                r = 8.5 * mm
                pdf.circle(px, py, r, stroke=1, fill=0)
            else:
                w = 30.0 * mm
                h = 18.0 * mm
                pdf.rect(px - w / 2, py - h / 2, w, h, stroke=1, fill=0)

            pdf.setFont("Helvetica", 5.5)
            pdf.drawCentredString(px, py - 1.5 * mm, display_label[:22])

        pdf.setLineWidth(0.5)
        for edge in projected_edges:
            from_center = node_points.get(edge["from_node_id"])
            to_center = node_points.get(edge["to_node_id"])
            if not from_center or not to_center:
                continue

            points = edge["points"]
            start_toward_x = to_center[0]
            end_toward_x = from_center[0]
            if isinstance(points, list) and len(points) >= 2:
                start_toward_x = points[1][0]
                end_toward_x = points[-2][0]

            from_anchor = _anchor_point(from_center, node_symbol_types.get(edge["from_node_id"], ""), start_toward_x)
            to_anchor = _anchor_point(to_center, node_symbol_types.get(edge["to_node_id"], ""), end_toward_x)
            polyline_pts = _route_with_straight_preference(from_anchor, to_anchor, points)
            polyline_pts = _orthogonalize_polyline(polyline_pts)

            if len(polyline_pts) < 2:
                continue

            offsets = [-1.5, 0.0, 1.5] if three_line else [0.0]
            for offset in offsets:
                path = pdf.beginPath()
                path.moveTo(polyline_pts[0][0] * mm, (polyline_pts[0][1] + offset) * mm)
                for xp, yp in polyline_pts[1:]:
                    path.lineTo(xp * mm, (yp + offset) * mm)
                pdf.drawPath(path, stroke=1, fill=0)

        pdf.showPage()

    pdf.save()
    return stream.getvalue()
