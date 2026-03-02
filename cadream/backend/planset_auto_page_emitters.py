from __future__ import annotations

from typing import Any

from planset_generation_annotations import segment_length_label, text_entity
from planset_generation_geometry import build_projector, compute_bounds, expand_bounds, project_point
from planset_generation_layers import page_layer

_SITE_LAYOUT_RECT = (24.0, 86.0, 312.0, 266.0)
_SLD_LAYOUT_RECT = (24.0, 86.0, 312.0, 266.0)

_SITE_PAGE_ALL_VIEW = {1, 7, 12, 42, 43}
_SITE_PAGE_BESS_VIEW = {2, 13}
_SITE_PAGE_CABLE_VIEW = {4, 5, 16, 17}
_SITE_PAGE_POI_VIEW = {6}
_SLD_PAGES = {24, 25}


_SITE_PAGE_PAD_RATIO: dict[int, float] = {
    1: 0.1,
    2: 0.08,
    4: 0.08,
    5: 0.06,
    6: 0.08,
    7: 0.1,
    12: 0.12,
    13: 0.06,
    16: 0.04,
    17: 0.04,
    42: 0.14,
    43: 0.14,
}


def _normalized_inputs(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = payload.get("normalized_inputs")
    if isinstance(normalized, dict):
        return normalized
    return {}


def _site_spec(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalized_inputs(payload)
    site_spec = normalized.get("site_design_spec")
    if isinstance(site_spec, dict):
        return site_spec
    return {}


def _sld_spec(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalized_inputs(payload)
    sld_spec = normalized.get("sld_design_spec")
    if isinstance(sld_spec, dict):
        return sld_spec
    return {}


def _collect_site_points(site_spec: dict[str, Any]) -> tuple[list[tuple[float, float]], list[tuple[float, float]], list[list[tuple[float, float]]], tuple[float, float] | None]:
    bess_points: list[tuple[float, float]] = []
    raw_bess = site_spec.get("bess") if isinstance(site_spec.get("bess"), list) else []
    for item in raw_bess:
        if not isinstance(item, dict):
            continue
        x = item.get("x")
        y = item.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            bess_points.append((float(x), float(y)))

    cable_polylines: list[list[tuple[float, float]]] = []
    cable_points: list[tuple[float, float]] = []
    raw_cables = site_spec.get("cables") if isinstance(site_spec.get("cables"), list) else []
    for cable in raw_cables:
        if not isinstance(cable, dict):
            continue
        raw_points = cable.get("points") if isinstance(cable.get("points"), list) else []
        points: list[tuple[float, float]] = []
        for point in raw_points:
            if not isinstance(point, dict):
                continue
            x = point.get("x")
            y = point.get("y")
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                points.append((float(x), float(y)))
                cable_points.append((float(x), float(y)))
        if len(points) >= 2:
            cable_polylines.append(points)

    poi = None
    raw_poi = site_spec.get("poi")
    if isinstance(raw_poi, dict):
        x = raw_poi.get("x")
        y = raw_poi.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            poi = (float(x), float(y))

    return bess_points, cable_points, cable_polylines, poi


def _build_site_entities(payload: dict[str, Any], page_number: int) -> list[dict[str, Any]]:
    site_spec = _site_spec(payload)
    bess_points, cable_points, cable_polylines, poi = _collect_site_points(site_spec)

    if page_number in _SITE_PAGE_BESS_VIEW:
        focus_points = list(bess_points)
        if poi:
            focus_points.append(poi)
    elif page_number in _SITE_PAGE_POI_VIEW:
        focus_points = []
        if poi:
            focus_points.append(poi)
        focus_points.extend(cable_points)
    elif page_number in _SITE_PAGE_CABLE_VIEW:
        focus_points = list(cable_points)
        if poi:
            focus_points.append(poi)
    else:
        focus_points = list(bess_points) + list(cable_points)
        if poi:
            focus_points.append(poi)

    bounds = compute_bounds(focus_points)
    if bounds is None:
        return []

    projector = build_projector(
        expand_bounds(bounds, pad_ratio=_SITE_PAGE_PAD_RATIO.get(page_number, 0.1), min_pad=2.0),
        dest_min_x=_SITE_LAYOUT_RECT[0],
        dest_min_y=_SITE_LAYOUT_RECT[1],
        dest_max_x=_SITE_LAYOUT_RECT[2],
        dest_max_y=_SITE_LAYOUT_RECT[3],
    )

    equip_layer = page_layer(page_number, "equip")
    cable_layer = page_layer(page_number, "cable")
    anno_layer = page_layer(page_number, "anno")

    entities: list[dict[str, Any]] = []

    for index, point in enumerate(bess_points, start=1):
        px, py = project_point(point, projector)
        entities.append(
            {
                "kind": "block_insert",
                "layer": equip_layer,
                "data": {
                    "block_name": "BESS_GENERIC",
                    "x": px,
                    "y": py,
                    "rotation": 0.0,
                },
            }
        )
        entities.append(text_entity(layer=anno_layer, text=f"BESS-{index}", x=px - 8.0, y=py - 7.0))

    if poi is not None:
        px, py = project_point(poi, projector)
        entities.append(
            {
                "kind": "circle",
                "layer": equip_layer,
                "data": {
                    "center": [px, py],
                    "r": 2.8,
                },
            }
        )
        entities.append(text_entity(layer=anno_layer, text="POI", x=px + 3.5, y=py + 3.5))

    for cable in cable_polylines:
        projected = [list(project_point(point, projector)) for point in cable]
        entities.append(
            {
                "kind": "polyline",
                "layer": cable_layer,
                "data": {
                    "points": projected,
                },
            }
        )

        if page_number in _SITE_PAGE_CABLE_VIEW:
            for start, end in zip(cable[:-1], cable[1:]):
                start_p = project_point(start, projector)
                end_p = project_point(end, projector)
                entities.append(segment_length_label(layer=anno_layer, start=start_p, end=end_p))

    if page_number in {12, 42, 43}:
        entities.append(
            text_entity(
                layer=anno_layer,
                text="Context / key-note overlay",
                x=_SITE_LAYOUT_RECT[0] + 4.0,
                y=_SITE_LAYOUT_RECT[1] + 6.0,
            )
        )

    if page_number == 6 and poi is not None:
        px, py = project_point(poi, projector)
        entities.append(text_entity(layer=anno_layer, text="Interconnection Area", x=px + 5.0, y=py + 7.0))

    if page_number in {16, 17}:
        entities.append(
            text_entity(
                layer=anno_layer,
                text=f"Routing Detail { 'A' if page_number == 16 else 'B' }",
                x=_SITE_LAYOUT_RECT[0] + 4.0,
                y=_SITE_LAYOUT_RECT[3] - 6.0,
            )
        )

    return entities


def _offset_polyline(points: list[list[float]], dy: float) -> list[list[float]]:
    return [[x, y + dy] for x, y in points]


def _build_sld_entities(payload: dict[str, Any], page_number: int) -> list[dict[str, Any]]:
    sld_spec = _sld_spec(payload)
    raw_symbols = sld_spec.get("symbols") if isinstance(sld_spec.get("symbols"), list) else []
    raw_connections = sld_spec.get("connections") if isinstance(sld_spec.get("connections"), list) else []

    symbol_points: list[tuple[float, float]] = []
    node_xy: dict[str, tuple[float, float]] = {}
    symbols: list[dict[str, Any]] = []

    for item in raw_symbols:
        if not isinstance(item, dict):
            continue
        symbol_id = item.get("id")
        x = item.get("x")
        y = item.get("y")
        if not isinstance(symbol_id, str) or not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            continue

        point = (float(x), float(y))
        symbol_points.append(point)
        node_xy[symbol_id] = point
        symbols.append(item)

    bounds = compute_bounds(symbol_points)
    if bounds is None:
        return []

    projector = build_projector(
        expand_bounds(bounds, pad_ratio=0.08, min_pad=3.0),
        dest_min_x=_SLD_LAYOUT_RECT[0],
        dest_min_y=_SLD_LAYOUT_RECT[1],
        dest_max_x=_SLD_LAYOUT_RECT[2],
        dest_max_y=_SLD_LAYOUT_RECT[3],
    )

    equip_layer = page_layer(page_number, "equip")
    wire_layer = page_layer(page_number, "wire")
    anno_layer = page_layer(page_number, "anno")

    entities: list[dict[str, Any]] = []

    for symbol in symbols:
        symbol_id = str(symbol.get("id"))
        symbol_type = str(symbol.get("symbol_type", "generic"))
        point = node_xy[symbol_id]
        px, py = project_point(point, projector)
        entities.append(
            {
                "kind": "block_insert",
                "layer": equip_layer,
                "data": {
                    "block_name": f"SLD_{symbol_type.upper().replace('-', '_')}",
                    "x": px,
                    "y": py,
                    "rotation": float(symbol.get("rotation", 0.0) or 0.0),
                },
            }
        )

        metadata = symbol.get("metadata") if isinstance(symbol.get("metadata"), dict) else {}
        label = metadata.get("label") if isinstance(metadata.get("label"), str) else symbol_type
        entities.append(text_entity(layer=anno_layer, text=label, x=px - 9.0, y=py - 8.0))

    for connection in raw_connections:
        if not isinstance(connection, dict):
            continue

        raw_vertices = connection.get("vertices") if isinstance(connection.get("vertices"), list) else []
        vertices: list[list[float]] = []
        for vertex in raw_vertices:
            if not isinstance(vertex, dict):
                continue
            x = vertex.get("x")
            y = vertex.get("y")
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                px, py = project_point((float(x), float(y)), projector)
                vertices.append([px, py])

        if len(vertices) < 2:
            from_id = connection.get("from_symbol_id")
            to_id = connection.get("to_symbol_id")
            if isinstance(from_id, str) and isinstance(to_id, str) and from_id in node_xy and to_id in node_xy:
                start = list(project_point(node_xy[from_id], projector))
                end = list(project_point(node_xy[to_id], projector))
                vertices = [start, end]

        if len(vertices) < 2:
            continue

        if page_number == 24:
            entities.append({"kind": "polyline", "layer": wire_layer, "data": {"points": vertices}})
        else:
            for offset in (-1.4, 0.0, 1.4):
                entities.append(
                    {
                        "kind": "polyline",
                        "layer": wire_layer,
                        "data": {
                            "points": _offset_polyline(vertices, offset),
                        },
                    }
                )

    return entities


def emit_auto_page_entities(payload: dict[str, Any], page_number: int) -> list[dict[str, Any]]:
    if (
        page_number in _SITE_PAGE_ALL_VIEW
        or page_number in _SITE_PAGE_BESS_VIEW
        or page_number in _SITE_PAGE_CABLE_VIEW
        or page_number in _SITE_PAGE_POI_VIEW
    ):
        return _build_site_entities(payload, page_number)

    if page_number in _SLD_PAGES:
        return _build_sld_entities(payload, page_number)

    return []
