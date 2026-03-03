from __future__ import annotations

from io import StringIO
from typing import Any

import ezdxf

from cad_export import _append_site_plan_to_layout
from cad_parser import load_dxf_from_bytes
from page_view_spec import PageViewSpec


SHEET_BORDER_LAYER = "SHEET_BORDER"
SHEET_TITLEBLOCK_LAYER = "SHEET_TITLEBLOCK"
SHEET_TEXT_LAYER = "SHEET_TEXT"
SHEET_CALLOUTS_LAYER = "SHEET_CALLOUTS"
SHEET_VIEWPORT_FRAME_LAYER = "SHEET_VIEWPORT_FRAME"
SHEET_OVERLAYS_LAYER = "SHEET_OVERLAYS"

_LEGACY_DXF_VERSIONS = {"AC1009", "AC1012", "AC1014"}
_MIN_SUPPORTED_MODERN_VERSION = "AC1015"


def _ensure_layer(doc: ezdxf.document.Drawing, layer_name: str, color: int) -> None:
    if layer_name not in doc.layers:
        doc.layers.add(layer_name)
    doc.layers.get(layer_name).dxf.color = color


def _ensure_sheet_layers(doc: ezdxf.document.Drawing) -> None:
    _ensure_layer(doc, SHEET_BORDER_LAYER, 8)
    _ensure_layer(doc, SHEET_TITLEBLOCK_LAYER, 7)
    _ensure_layer(doc, SHEET_TEXT_LAYER, 5)
    _ensure_layer(doc, SHEET_CALLOUTS_LAYER, 3)
    _ensure_layer(doc, SHEET_VIEWPORT_FRAME_LAYER, 6)
    _ensure_layer(doc, SHEET_OVERLAYS_LAYER, 4)


def _serialize_doc(doc: ezdxf.document.Drawing) -> bytes:
    doc.audit()
    stream = StringIO()
    doc.write(stream)
    encoding = getattr(doc, "output_encoding", None) or "cp1252"
    return stream.getvalue().encode(encoding, errors="replace")


def _ensure_modern_dxf_version(doc: ezdxf.document.Drawing) -> None:
    version = str(getattr(doc, "dxfversion", "")).upper()
    if version in _LEGACY_DXF_VERSIONS:
        doc.dxfversion = _MIN_SUPPORTED_MODERN_VERSION


def _ensure_title_block_block(doc: ezdxf.document.Drawing, block_name: str) -> str:
    safe_name = block_name.strip() or "CADREAM_TITLEBLOCK_V1"
    if safe_name in doc.blocks:
        return safe_name

    block = doc.blocks.new(name=safe_name)
    poly = block.add_lwpolyline([(0.0, 0.0), (88.0, 0.0), (88.0, 38.0), (0.0, 38.0)], dxfattribs={"layer": SHEET_TITLEBLOCK_LAYER})
    poly.closed = True
    block.add_line((0.0, 24.0), (88.0, 24.0), dxfattribs={"layer": SHEET_TITLEBLOCK_LAYER})
    block.add_line((0.0, 12.0), (88.0, 12.0), dxfattribs={"layer": SHEET_TITLEBLOCK_LAYER})
    block.add_text("CADream", dxfattribs={"layer": SHEET_TITLEBLOCK_LAYER, "height": 4.0}).set_placement((4.0, 28.0))
    block.add_text("Title Block", dxfattribs={"layer": SHEET_TITLEBLOCK_LAYER, "height": 2.8}).set_placement((4.0, 16.0))
    return safe_name


def _clear_layout(layout: Any) -> None:
    for entity in list(layout):
        if entity.dxftype() == "VIEWPORT" and int(getattr(entity.dxf, "id", 0) or 0) == 1:
            continue
        layout.delete_entity(entity)


def _ensure_page_layout(doc: ezdxf.document.Drawing, page_number: int) -> Any:
    del page_number
    layout_name = "Layout1"
    if layout_name in doc.layouts:
        layout = doc.layouts.get(layout_name)
        _clear_layout(layout)
        return layout
    return doc.layouts.new(layout_name)


def _draw_sheet_geometry(layout: Any, spec: PageViewSpec) -> None:
    sheet_w = spec.sheet.width
    sheet_h = spec.sheet.height

    frame = layout.add_lwpolyline(
        [(0.0, 0.0), (sheet_w, 0.0), (sheet_w, sheet_h), (0.0, sheet_h)],
        dxfattribs={"layer": SHEET_BORDER_LAYER},
    )
    frame.closed = True

    title = layout.add_text(
        f"PAGE {spec.page_number:02d} - {spec.page_name}",
        dxfattribs={"layer": SHEET_TEXT_LAYER, "height": 4.0},
    )
    title.set_placement((8.0, max(6.0, sheet_h - 10.0)))


def _insert_title_block(layout: Any, doc: ezdxf.document.Drawing, spec: PageViewSpec) -> None:
    block_name = _ensure_title_block_block(doc, spec.template.title_block_block_name)
    x_insert = max(0.0, spec.sheet.width - 92.0)
    y_insert = 4.0
    layout.add_blockref(block_name, (x_insert, y_insert), dxfattribs={"layer": SHEET_TITLEBLOCK_LAYER})


def _draw_viewport_frame(layout: Any, spec: PageViewSpec) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = spec.viewport_rect
    frame = layout.add_lwpolyline(
        [(x1, y1), (x2, y1), (x2, y2), (x1, y2)],
        dxfattribs={"layer": SHEET_VIEWPORT_FRAME_LAYER},
    )
    frame.closed = True
    return x1, y1, x2, y2


def _viewport_view_height(spec: PageViewSpec, viewport_rect: tuple[float, float, float, float]) -> float:
    x1, y1, x2, y2 = viewport_rect
    vp_w = max(1e-6, x2 - x1)
    vp_h = max(1e-6, y2 - y1)
    vp_aspect = vp_w / vp_h

    model_w = spec.view_bounds.max_x - spec.view_bounds.min_x
    model_h = spec.view_bounds.max_y - spec.view_bounds.min_y
    model_h = max(model_h, model_w / max(vp_aspect, 1e-6))
    return max(model_h, 1.0)


def _add_paperspace_viewport(layout: Any, spec: PageViewSpec, viewport_rect: tuple[float, float, float, float]) -> None:
    x1, y1, x2, y2 = viewport_rect
    cx = (x1 + x2) * 0.5
    cy = (y1 + y2) * 0.5

    model_cx = (spec.view_bounds.min_x + spec.view_bounds.max_x) * 0.5
    model_cy = (spec.view_bounds.min_y + spec.view_bounds.max_y) * 0.5

    layout.add_viewport(
        center=(cx, cy),
        size=(max(1e-6, x2 - x1), max(1e-6, y2 - y1)),
        view_center_point=(model_cx, model_cy),
        view_height=_viewport_view_height(spec, viewport_rect),
        dxfattribs={"layer": SHEET_VIEWPORT_FRAME_LAYER},
    )


def _append_overlays(doc: ezdxf.document.Drawing, modelspace: Any, overlays: dict[str, Any] | None) -> None:
    if not isinstance(overlays, dict):
        return

    site_plan = overlays.get("site_plan") if isinstance(overlays.get("site_plan"), dict) else None
    entities = overlays.get("entities") if isinstance(overlays.get("entities"), dict) else None

    if isinstance(site_plan, dict):
        _append_site_plan_to_layout(
            doc,
            modelspace,
            site_plan,
            bess_layer=SHEET_OVERLAYS_LAYER,
            cable_layer=SHEET_OVERLAYS_LAYER,
        )
        return

    if isinstance(entities, dict):
        _append_site_plan_to_layout(
            doc,
            modelspace,
            {"entities": entities},
            bess_layer=SHEET_OVERLAYS_LAYER,
            cable_layer=SHEET_OVERLAYS_LAYER,
        )


def _coerce_spec(spec: PageViewSpec | dict[str, Any]) -> PageViewSpec:
    if isinstance(spec, PageViewSpec):
        return spec
    if isinstance(spec, dict):
        return PageViewSpec.from_dict(spec)
    raise ValueError("spec must be a PageViewSpec or dict")


def build_page_dxf_from_source_bytes(
    source_bytes: bytes,
    spec: PageViewSpec | dict[str, Any],
    overlays: dict[str, Any] | None = None,
) -> bytes:
    page_spec = _coerce_spec(spec)

    doc = load_dxf_from_bytes(source_bytes)
    _ensure_modern_dxf_version(doc)
    modelspace = doc.modelspace()

    _ensure_sheet_layers(doc)
    _append_overlays(doc, modelspace, overlays)

    paperspace = _ensure_page_layout(doc, page_spec.page_number)
    _draw_sheet_geometry(paperspace, page_spec)
    _insert_title_block(paperspace, doc, page_spec)
    viewport_rect = _draw_viewport_frame(paperspace, page_spec)
    _add_paperspace_viewport(paperspace, page_spec, viewport_rect)

    doc.header["$TILEMODE"] = 0
    return _serialize_doc(doc)
