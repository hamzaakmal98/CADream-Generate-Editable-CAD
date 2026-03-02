from __future__ import annotations

from io import BytesIO, StringIO
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import ezdxf

from planset_auto_page_emitters import emit_auto_page_entities
from planset_manifest import build_plan_set_manifest


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


def _build_page_dxf(payload: dict[str, Any], page_number: int) -> bytes:
    doc = ezdxf.new("R2010")
    layout = doc.modelspace()

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


def export_auto_pages_dxf_zip(payload: dict[str, Any]) -> bytes:
    files = generate_auto_pages_dxf_files(payload)
    if not files:
        raise ValueError("No auto pages are ready for DXF export")

    zip_stream = BytesIO()
    with ZipFile(zip_stream, mode="w", compression=ZIP_DEFLATED) as archive:
        for file_name, content in sorted(files.items()):
            archive.writestr(file_name, content)

    return zip_stream.getvalue()
