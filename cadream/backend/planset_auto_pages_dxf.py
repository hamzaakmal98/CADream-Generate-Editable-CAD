from __future__ import annotations

import json
import math
from io import BytesIO, StringIO
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import ezdxf
from cad_export import _append_site_plan_to_layout
from cad_parser import load_dxf_from_bytes

from planset_auto_page_emitters import emit_auto_page_entities
from planset_generation_geometry import build_projector, compute_bounds, expand_bounds, project_point
from planset_manifest import build_plan_set_manifest
from planset_pdf_titles import build_right_panel_metadata, resolve_generated_page_title


_CONTENT_RECT = (24.0, 86.0, 312.0, 266.0)
_SITE_PAGE_ALL_VIEW = {1, 7, 12, 42, 43}
_SITE_PAGE_BESS_VIEW = {2, 13}
_SITE_PAGE_CABLE_VIEW = {4, 5, 16, 17}
_SITE_PAGE_POI_VIEW = {6}


def _ensure_layer(doc: ezdxf.document.Drawing, name: str, color: int) -> None:
    if name not in doc.layers:
        doc.layers.add(name)
    doc.layers.get(name).dxf.color = color


def _ensure_block(doc: ezdxf.document.Drawing, block_name: str) -> str:
    safe_name = block_name.strip() or "CADREAM_BLOCK"
    if safe_name in doc.blocks:
        return safe_name

    block = doc.blocks.new(name=safe_name)
    poly = block.add_lwpolyline([(-1.6, -1.6), (1.6, -1.6), (1.6, 1.6), (-1.6, 1.6)])
    poly.closed = True
    block.add_line((-1.2, 0.0), (1.2, 0.0))
    block.add_line((0.0, -1.2), (0.0, 1.2))
    return safe_name


def _layer_color(layer_name: str) -> int:
    lower = layer_name.lower()
    if "wire" in lower or "cable" in lower:
        return 3
    if "anno" in lower:
        return 5
    if "equip" in lower:
        return 7
    return 8


def _draw_entity(layout: Any, entity: dict[str, Any], doc: ezdxf.document.Drawing) -> None:
    kind = entity.get("kind")
    layer_name = str(entity.get("layer") or "0")
    data = entity.get("data") if isinstance(entity.get("data"), dict) else {}

    _ensure_layer(doc, layer_name, _layer_color(layer_name))
    attribs = {"layer": layer_name}

    if kind == "polyline":
        raw_points = data.get("points") if isinstance(data.get("points"), list) else []
        points: list[tuple[float, float]] = []
        for point in raw_points:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            x_raw, y_raw = point[0], point[1]
            if isinstance(x_raw, (int, float)) and isinstance(y_raw, (int, float)):
                points.append((float(x_raw), float(y_raw)))
        if len(points) >= 2:
            layout.add_lwpolyline(points, dxfattribs=attribs)
        return

    if kind == "circle":
        center = data.get("center") if isinstance(data.get("center"), (list, tuple)) else None
        radius = data.get("r")
        if (
            isinstance(center, (list, tuple))
            and len(center) >= 2
            and isinstance(center[0], (int, float))
            and isinstance(center[1], (int, float))
            and isinstance(radius, (int, float))
        ):
            layout.add_circle((float(center[0]), float(center[1])), float(radius), dxfattribs=attribs)
        return

    if kind == "text":
        text_value = data.get("text")
        x_value = data.get("x")
        y_value = data.get("y")
        height = data.get("height")
        if (
            isinstance(text_value, str)
            and isinstance(x_value, (int, float))
            and isinstance(y_value, (int, float))
        ):
            text_entity = layout.add_text(
                text_value,
                dxfattribs={
                    **attribs,
                    "height": float(height) if isinstance(height, (int, float)) else 2.2,
                },
            )
            text_entity.set_placement((float(x_value), float(y_value)))
        return

    if kind == "block_insert":
        block_name = data.get("block_name")
        x_value = data.get("x")
        y_value = data.get("y")
        rotation = data.get("rotation")
        if isinstance(block_name, str) and isinstance(x_value, (int, float)) and isinstance(y_value, (int, float)):
            resolved_name = _ensure_block(doc, block_name)
            insert = layout.add_blockref(resolved_name, (float(x_value), float(y_value)), dxfattribs=attribs)
            insert.dxf.rotation = float(rotation) if isinstance(rotation, (int, float)) else 0.0


def _serialize_doc(doc: ezdxf.document.Drawing) -> bytes:
    stream = StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")


def _add_rect(layout: Any, layer_name: str, x_left: float, y_bottom: float, x_right: float, y_top: float) -> None:
    poly = layout.add_lwpolyline(
        [(x_left, y_bottom), (x_right, y_bottom), (x_right, y_top), (x_left, y_top)],
        dxfattribs={"layer": layer_name},
    )
    poly.closed = True


def _draw_title_block_geometry(layout: Any, doc: ezdxf.document.Drawing) -> None:
    layer_name = "CADREAM-TITLEBLOCK"
    _ensure_layer(doc, layer_name, 8)

    sheet_left = 5.0
    sheet_bottom = 5.0
    sheet_right = 415.0
    sheet_top = 292.0
    right_panel_left = 332.0

    _add_rect(layout, layer_name, sheet_left, sheet_bottom, sheet_right, sheet_top)
    layout.add_line((right_panel_left, sheet_bottom), (right_panel_left, sheet_top), dxfattribs={"layer": layer_name})

    section_heights = [32.0, 30.0, 28.0, 26.0, 24.0, 22.0, 20.0, 18.0]
    y_cursor = sheet_top
    for height in section_heights:
        y_cursor -= height
        if y_cursor <= sheet_bottom:
            break
        layout.add_line((right_panel_left, y_cursor), (sheet_right, y_cursor), dxfattribs={"layer": layer_name})

    label_split_x = right_panel_left + 20.0
    layout.add_line((label_split_x, sheet_bottom), (label_split_x, sheet_bottom + 48.0), dxfattribs={"layer": layer_name})


def _draw_metadata_panel(layout: Any, doc: ezdxf.document.Drawing, payload: dict[str, Any], page_number: int) -> None:
    layer_name = "CADREAM-META"
    _ensure_layer(doc, layer_name, 5)

    metadata, _ = build_right_panel_metadata(payload, page_number)
    sheet_title = resolve_generated_page_title(payload, page_number)

    rows = [
        ("Sheet No", str(metadata.get("Sheet No", str(page_number).zfill(2)))),
        ("Sheet", str(metadata.get("Sheet", sheet_title))),
        ("Scale", str(metadata.get("Scale", "As Noted"))),
        ("Date", str(metadata.get("Date", ""))),
        ("Revision", str(metadata.get("Revision", "A"))),
        ("Project", str(metadata.get("EQORE Project", ""))),
        ("Client", str(metadata.get("Customer Name", ""))),
        ("Address", str(metadata.get("Customer Address", ""))),
        ("Drawn By", str(metadata.get("Drawn By", ""))),
        ("Checked By", str(metadata.get("Checked By", ""))),
        ("Approved By", str(metadata.get("Approved By", ""))),
    ]

    x_left = 320.0
    x_right = 415.0
    y_top = 290.0
    row_h = 7.2
    panel_h = row_h * (len(rows) + 1)
    y_bottom = y_top - panel_h

    frame = layout.add_lwpolyline(
        [(x_left, y_bottom), (x_right, y_bottom), (x_right, y_top), (x_left, y_top)],
        dxfattribs={"layer": layer_name},
    )
    frame.closed = True

    layout.add_text(
        f"AUTO PAGE {str(page_number).zfill(2)}",
        dxfattribs={"layer": layer_name, "height": 2.6},
    ).set_placement((x_left + 1.5, y_top - 4.8))

    for row_index, (label, value) in enumerate(rows, start=1):
        y = y_top - row_h * row_index
        layout.add_line((x_left, y), (x_right, y), dxfattribs={"layer": layer_name})
        layout.add_text(
            label,
            dxfattribs={"layer": layer_name, "height": 2.0},
        ).set_placement((x_left + 1.5, y - 4.6))
        layout.add_text(
            value[:58],
            dxfattribs={"layer": layer_name, "height": 2.0},
        ).set_placement((x_left + 30.0, y - 4.6))


def _extract_context_primitives(payload: dict[str, Any], *, max_entities: int = 5000) -> tuple[list[dict[str, Any]], list[tuple[float, float]]]:
    cad_ir = payload.get("cad_ir") if isinstance(payload.get("cad_ir"), dict) else {}
    entities_by_id = cad_ir.get("entitiesById") if isinstance(cad_ir.get("entitiesById"), dict) else {}
    model_ids = cad_ir.get("modelSpaceEntityIds") if isinstance(cad_ir.get("modelSpaceEntityIds"), list) else []

    primitives: list[dict[str, Any]] = []
    bounds_points: list[tuple[float, float]] = []

    for entity_id in model_ids:
        if len(primitives) >= max_entities:
            break
        if not isinstance(entity_id, str):
            continue
        entity = entities_by_id.get(entity_id)
        if not isinstance(entity, dict):
            continue

        entity_type = entity.get("type")

        if entity_type == "LINE":
            start = entity.get("start") if isinstance(entity.get("start"), list) else []
            end = entity.get("end") if isinstance(entity.get("end"), list) else []
            if len(start) >= 2 and len(end) >= 2 and isinstance(start[0], (int, float)) and isinstance(start[1], (int, float)) and isinstance(end[0], (int, float)) and isinstance(end[1], (int, float)):
                points = [(float(start[0]), float(start[1])), (float(end[0]), float(end[1]))]
                primitives.append({"kind": "polyline", "points": points})
                bounds_points.extend(points)
            continue

        if entity_type == "LWPOLYLINE":
            vertices = entity.get("vertices") if isinstance(entity.get("vertices"), list) else []
            points: list[tuple[float, float]] = []
            for vertex in vertices:
                if not isinstance(vertex, dict):
                    continue
                x = vertex.get("x")
                y = vertex.get("y")
                if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                    points.append((float(x), float(y)))
            if len(points) >= 2:
                if bool(entity.get("closed")):
                    points = points + [points[0]]
                primitives.append({"kind": "polyline", "points": points})
                bounds_points.extend(points)
            continue

        if entity_type == "CIRCLE":
            center = entity.get("center") if isinstance(entity.get("center"), list) else []
            radius = entity.get("radius")
            if len(center) >= 2 and isinstance(center[0], (int, float)) and isinstance(center[1], (int, float)) and isinstance(radius, (int, float)):
                cx = float(center[0])
                cy = float(center[1])
                r = abs(float(radius))
                primitives.append({"kind": "circle", "center": (cx, cy), "radius": r})
                bounds_points.extend([(cx - r, cy - r), (cx + r, cy + r)])
            continue

        if entity_type == "ARC":
            center = entity.get("center") if isinstance(entity.get("center"), list) else []
            radius = entity.get("radius")
            start_angle = entity.get("startAngleDeg")
            end_angle = entity.get("endAngleDeg")
            if (
                len(center) >= 2
                and isinstance(center[0], (int, float))
                and isinstance(center[1], (int, float))
                and isinstance(radius, (int, float))
                and isinstance(start_angle, (int, float))
                and isinstance(end_angle, (int, float))
            ):
                cx = float(center[0])
                cy = float(center[1])
                r = abs(float(radius))
                start = float(start_angle)
                end = float(end_angle)
                if end < start:
                    end += 360.0
                segments = max(12, int((end - start) / 15.0))
                points: list[tuple[float, float]] = []
                for index in range(segments + 1):
                    t = start + (end - start) * (index / segments)
                    rad = math.radians(t)
                    points.append((cx + r * math.cos(rad), cy + r * math.sin(rad)))
                if len(points) >= 2:
                    primitives.append({"kind": "polyline", "points": points})
                    bounds_points.extend(points)

    return primitives, bounds_points


def _draw_projected_context(layout: Any, doc: ezdxf.document.Drawing, payload: dict[str, Any]) -> None:
    primitives, bounds_points = _extract_context_primitives(payload)
    bounds = compute_bounds(bounds_points)
    if bounds is None or not primitives:
        return

    projector = build_projector(
        expand_bounds(bounds, pad_ratio=0.04, min_pad=2.0),
        dest_min_x=_CONTENT_RECT[0],
        dest_min_y=_CONTENT_RECT[1],
        dest_max_x=_CONTENT_RECT[2],
        dest_max_y=_CONTENT_RECT[3],
    )

    scale, _, _ = projector

    layer_name = "CADREAM-CONTEXT"
    _ensure_layer(doc, layer_name, 8)

    for primitive in primitives:
        kind = primitive.get("kind")
        if kind == "polyline":
            source_points = primitive.get("points") if isinstance(primitive.get("points"), list) else []
            points: list[tuple[float, float]] = []
            for point in source_points:
                if isinstance(point, tuple) and len(point) == 2:
                    points.append(project_point(point, projector))
            if len(points) >= 2:
                layout.add_lwpolyline(points, dxfattribs={"layer": layer_name})
            continue

        if kind == "circle":
            center = primitive.get("center")
            radius = primitive.get("radius")
            if isinstance(center, tuple) and len(center) == 2 and isinstance(radius, (int, float)):
                px, py = project_point(center, projector)
                layout.add_circle((px, py), max(0.0001, abs(float(radius)) * scale), dxfattribs={"layer": layer_name})


def _collect_site_points_from_placements(payload: dict[str, Any]) -> tuple[list[tuple[float, float]], list[tuple[float, float]], tuple[float, float] | None]:
    site_placements = payload.get("site_placements") if isinstance(payload.get("site_placements"), dict) else {}
    entities = site_placements.get("entities") if isinstance(site_placements.get("entities"), dict) else {}

    bess_points: list[tuple[float, float]] = []
    raw_bess = entities.get("bess") if isinstance(entities.get("bess"), list) else []
    for item in raw_bess:
        if not isinstance(item, dict):
            continue
        pos = item.get("cad_position") if isinstance(item.get("cad_position"), dict) else item.get("position")
        if not isinstance(pos, dict):
            continue
        x = pos.get("x")
        y = pos.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            bess_points.append((float(x), float(y)))

    cable_points: list[tuple[float, float]] = []
    raw_cables = entities.get("cable_paths") if isinstance(entities.get("cable_paths"), list) else entities.get("cablePaths")
    if isinstance(raw_cables, list):
        for cable in raw_cables:
            if not isinstance(cable, dict):
                continue
            points = cable.get("points") if isinstance(cable.get("points"), list) else []
            for point in points:
                if isinstance(point, list) and len(point) >= 2:
                    x = point[0]
                    y = point[1]
                    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                        cable_points.append((float(x), float(y)))
                elif isinstance(point, dict):
                    x = point.get("x")
                    y = point.get("y")
                    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                        cable_points.append((float(x), float(y)))

    poi = entities.get("poi") if isinstance(entities.get("poi"), dict) else None
    poi_point: tuple[float, float] | None = None
    if isinstance(poi, dict):
        x = poi.get("x")
        y = poi.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            poi_point = (float(x), float(y))

    return bess_points, cable_points, poi_point


def _focus_bounds_for_page(payload: dict[str, Any], page_number: int) -> tuple[float, float, float, float] | None:
    bess_points, cable_points, poi = _collect_site_points_from_placements(payload)

    if page_number in _SITE_PAGE_BESS_VIEW:
        focus_points = list(bess_points)
        if poi is not None:
            focus_points.append(poi)
    elif page_number in _SITE_PAGE_POI_VIEW:
        focus_points = list(cable_points)
        if poi is not None:
            focus_points.append(poi)
    elif page_number in _SITE_PAGE_CABLE_VIEW:
        focus_points = list(cable_points)
        if poi is not None:
            focus_points.append(poi)
    else:
        focus_points = list(bess_points) + list(cable_points)
        if poi is not None:
            focus_points.append(poi)

    bounds = compute_bounds(focus_points)
    if bounds is None:
        return None
    return expand_bounds(bounds, pad_ratio=0.14 if page_number in _SITE_PAGE_ALL_VIEW else 0.08, min_pad=8.0)


def _draw_page_focus_window(layout: Any, doc: ezdxf.document.Drawing, bounds: tuple[float, float, float, float], page_number: int) -> None:
    layer_name = "CADREAM-PAGE-WINDOW"
    _ensure_layer(doc, layer_name, 6)

    min_x, min_y, max_x, max_y = bounds
    poly = layout.add_lwpolyline(
        [(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)],
        dxfattribs={"layer": layer_name},
    )
    poly.closed = True
    label = layout.add_text(
        f"AUTO PAGE {str(page_number).zfill(2)} WINDOW",
        dxfattribs={"layer": layer_name, "height": max(2.5, (max_y - min_y) * 0.015)},
    )
    label.set_placement((min_x, max_y + max(2.0, (max_y - min_y) * 0.01)))


def _ensure_auto_page_layout_view(doc: ezdxf.document.Drawing, bounds: tuple[float, float, float, float], page_number: int, sheet_title: str) -> None:
    layout_name = f"AUTO_PAGE_{str(page_number).zfill(2)}"
    if layout_name in doc.layouts:
        paperspace = doc.layouts.get(layout_name)
    else:
        paperspace = doc.layouts.new(layout_name)

    layer_name = "CADREAM-PAPER"
    _ensure_layer(doc, layer_name, 7)

    frame = paperspace.add_lwpolyline(
        [(10.0, 10.0), (410.0, 10.0), (410.0, 287.0), (10.0, 287.0)],
        dxfattribs={"layer": layer_name},
    )
    frame.closed = True

    paperspace.add_text(
        f"AUTO PAGE {str(page_number).zfill(2)} - {sheet_title}",
        dxfattribs={"layer": layer_name, "height": 4.0},
    ).set_placement((14.0, 280.0))

    min_x, min_y, max_x, max_y = bounds
    view_center = ((min_x + max_x) * 0.5, (min_y + max_y) * 0.5)
    view_height = max(1.0, (max_y - min_y))

    paperspace.add_viewport(
        center=(210.0, 145.0),
        size=(360.0, 240.0),
        view_center_point=view_center,
        view_height=view_height,
        dxfattribs={"layer": layer_name},
    )

    doc.header["$TILEMODE"] = 0


def _build_page_dxf(payload: dict[str, Any], page_number: int) -> bytes:
    doc = ezdxf.new("R2010")
    layout = doc.modelspace()

    _draw_title_block_geometry(layout, doc)
    _draw_metadata_panel(layout, doc, payload, page_number)
    _draw_projected_context(layout, doc, payload)

    entities = emit_auto_page_entities(payload, page_number)
    for entity in entities:
        if isinstance(entity, dict):
            _draw_entity(layout, entity, doc)

    return _serialize_doc(doc)


def _build_preserved_page_dxf(payload: dict[str, Any], page_number: int, source_bytes: bytes) -> bytes:
    site_placements = payload.get("site_placements")
    if not isinstance(site_placements, dict):
        raise ValueError("Missing site_placements for preserved auto-page DXF export")

    entities = site_placements.get("entities") if isinstance(site_placements.get("entities"), dict) else None
    if not isinstance(entities, dict):
        raise ValueError("Invalid site_placements payload")

    doc = load_dxf_from_bytes(source_bytes)
    layout = doc.modelspace()
    doc.header["$TILEMODE"] = 1
    _append_site_plan_to_layout(doc, layout, {"entities": entities})

    layer_name = "CADREAM-AUTOPAGE"
    _ensure_layer(doc, layer_name, 5)
    metadata, _ = build_right_panel_metadata(payload, page_number)
    sheet_no = str(metadata.get("Sheet No", str(page_number).zfill(2)))
    sheet_title = resolve_generated_page_title(payload, page_number)

    text = layout.add_text(
        f"AUTO PAGE {sheet_no} - {sheet_title}",
        dxfattribs={"layer": layer_name, "height": 2.8},
    )
    text.set_placement((10.0, 10.0))

    focus_bounds = _focus_bounds_for_page(payload, page_number)
    if focus_bounds is not None:
        _draw_page_focus_window(layout, doc, focus_bounds, page_number)

    return _serialize_doc(doc)


def _page_numbers_ready_for_auto(payload: dict[str, Any]) -> list[int]:
    manifest = build_plan_set_manifest(payload)
    pages = manifest.get("pages") if isinstance(manifest.get("pages"), list) else []

    page_numbers: list[int] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        if page.get("generation_mode") != "auto" or page.get("status") != "auto":
            continue
        page_number = page.get("page_number")
        if isinstance(page_number, int) and page_number > 0:
            page_numbers.append(page_number)

    return sorted(set(page_numbers))


def generate_auto_pages_dxf_files(payload: dict[str, Any]) -> tuple[dict[str, bytes], str]:
    page_numbers = _page_numbers_ready_for_auto(payload)

    source_bytes = payload.get("__source_dxf_bytes")
    if isinstance(source_bytes, (bytes, bytearray)) and isinstance(payload.get("site_placements"), dict):
        output: dict[str, bytes] = {}
        for page_number in page_numbers:
            output[f"planset-page-{str(page_number).zfill(2)}.dxf"] = _build_preserved_page_dxf(payload, page_number, bytes(source_bytes))
        return output, "preserved-source"

    output: dict[str, bytes] = {}
    for page_number in page_numbers:
        output[f"planset-page-{str(page_number).zfill(2)}.dxf"] = _build_page_dxf(payload, page_number)

    return output, "generated-auto-pages"


def _build_auto_pages_zip_manifest(payload: dict[str, Any], dxf_files: dict[str, bytes], dxf_export_mode: str) -> dict[str, Any]:
    manifest = build_plan_set_manifest(payload)
    pages = manifest.get("pages") if isinstance(manifest.get("pages"), list) else []

    exported_page_numbers: list[int] = []
    for file_name in sorted(dxf_files.keys()):
        if not file_name.endswith(".dxf"):
            continue
        token = file_name.replace("planset-page-", "").replace(".dxf", "")
        if token.isdigit():
            exported_page_numbers.append(int(token))

    auto_ready_pages: list[int] = []
    pending_auto_pages: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        if page.get("generation_mode") != "auto":
            continue
        page_number = page.get("page_number")
        if not isinstance(page_number, int):
            continue
        if page.get("status") == "auto":
            auto_ready_pages.append(page_number)
        elif page.get("status") == "pending":
            pending_auto_pages.append(
                {
                    "page_number": page_number,
                    "missing_reasons": page.get("missing_reasons") if isinstance(page.get("missing_reasons"), list) else [],
                }
            )

    return {
        "schema_version": "planset-auto-pages-package-v1",
        "dxf_export_mode": dxf_export_mode,
        "files": sorted(dxf_files.keys()),
        "counts": {
            "exported_dxf_pages": len(exported_page_numbers),
            "auto_ready_pages": len(auto_ready_pages),
            "pending_auto_pages": len(pending_auto_pages),
        },
        "exported_page_numbers": exported_page_numbers,
        "auto_ready_page_numbers": sorted(auto_ready_pages),
        "pending_auto_pages": pending_auto_pages,
    }


def export_auto_pages_dxf_zip(payload: dict[str, Any]) -> bytes:
    files, dxf_export_mode = generate_auto_pages_dxf_files(payload)
    if not files:
        raise ValueError("No auto pages are ready for DXF export")

    package_manifest = _build_auto_pages_zip_manifest(payload, files, dxf_export_mode)
    manifest_bytes = json.dumps(package_manifest, indent=2, sort_keys=True).encode("utf-8")

    zip_stream = BytesIO()
    with ZipFile(zip_stream, mode="w", compression=ZIP_DEFLATED) as archive:
        for file_name, content in sorted(files.items()):
            archive.writestr(file_name, content)
        archive.writestr("auto-pages-manifest.json", manifest_bytes)

    return zip_stream.getvalue()
