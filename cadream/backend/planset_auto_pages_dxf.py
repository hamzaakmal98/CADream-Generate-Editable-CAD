from __future__ import annotations

import json
from io import BytesIO, StringIO
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import ezdxf

from planset_auto_page_emitters import emit_auto_page_entities
from planset_manifest import build_plan_set_manifest
from planset_pdf_titles import build_right_panel_metadata, resolve_generated_page_title


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


def _build_page_dxf(payload: dict[str, Any], page_number: int) -> bytes:
    doc = ezdxf.new("R2010")
    layout = doc.modelspace()

    _draw_title_block_geometry(layout, doc)
    _draw_metadata_panel(layout, doc, payload, page_number)

    entities = emit_auto_page_entities(payload, page_number)
    for entity in entities:
        if isinstance(entity, dict):
            _draw_entity(layout, entity, doc)

    return _serialize_doc(doc)


def generate_auto_pages_dxf_files(payload: dict[str, Any]) -> dict[str, bytes]:
    manifest = build_plan_set_manifest(payload)
    pages = manifest.get("pages") if isinstance(manifest.get("pages"), list) else []

    output: dict[str, bytes] = {}
    for page in pages:
        if not isinstance(page, dict):
            continue
        if page.get("generation_mode") != "auto" or page.get("status") != "auto":
            continue
        page_number = page.get("page_number")
        if not isinstance(page_number, int) or page_number <= 0:
            continue
        output[f"planset-page-{str(page_number).zfill(2)}.dxf"] = _build_page_dxf(payload, page_number)

    return output


def _build_auto_pages_zip_manifest(payload: dict[str, Any], dxf_files: dict[str, bytes]) -> dict[str, Any]:
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
    files = generate_auto_pages_dxf_files(payload)
    if not files:
        raise ValueError("No auto pages are ready for DXF export")

    package_manifest = _build_auto_pages_zip_manifest(payload, files)
    manifest_bytes = json.dumps(package_manifest, indent=2, sort_keys=True).encode("utf-8")

    zip_stream = BytesIO()
    with ZipFile(zip_stream, mode="w", compression=ZIP_DEFLATED) as archive:
        for file_name, content in sorted(files.items()):
            archive.writestr(file_name, content)
        archive.writestr("auto-pages-manifest.json", manifest_bytes)

    return zip_stream.getvalue()
