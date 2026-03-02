from __future__ import annotations

from datetime import date
from io import StringIO
from typing import Any

import ezdxf

SHEET_WIDTH = 420.0
SHEET_HEIGHT = 297.0
SHEET_MARGIN = 5.0

PANEL_LEFT = 332.0
PANEL_RIGHT = SHEET_WIDTH - SHEET_MARGIN
PANEL_TOP = SHEET_HEIGHT - SHEET_MARGIN
PANEL_BOTTOM = SHEET_MARGIN


def _safe_str(value: Any, fallback: str = "") -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _ensure_layer(doc: ezdxf.document.Drawing, name: str, color: int) -> None:
    if name not in doc.layers:
        doc.layers.add(name)
    doc.layers.get(name).dxf.color = color


def _add_box(layout: Any, x1: float, y1: float, x2: float, y2: float, layer: str) -> None:
    poly = layout.add_lwpolyline(
        [(x1, y1), (x2, y1), (x2, y2), (x1, y2)],
        dxfattribs={"layer": layer},
    )
    poly.closed = True


def _add_label_value(
    layout: Any,
    *,
    x_left: float,
    x_right: float,
    y_top: float,
    row_height: float,
    label: str,
    value: str,
    border_layer: str,
    text_layer: str,
) -> float:
    y_bottom = y_top - row_height
    _add_box(layout, x_left, y_bottom, x_right, y_top, border_layer)
    split_x = x_left + 30.0
    layout.add_line((split_x, y_bottom), (split_x, y_top), dxfattribs={"layer": border_layer})

    layout.add_text(label, dxfattribs={"layer": text_layer, "height": 2.1}).set_placement((x_left + 1.0, y_top - 3.7))
    layout.add_text(value[:44], dxfattribs={"layer": text_layer, "height": 2.1}).set_placement((split_x + 1.0, y_top - 3.7))
    return y_bottom


def _add_section(
    layout: Any,
    *,
    x_left: float,
    x_right: float,
    y_top: float,
    title: str,
    body_lines: list[str],
    border_layer: str,
    text_layer: str,
    title_height: float = 8.0,
    body_height: float = 15.0,
) -> float:
    title_bottom = y_top - title_height
    body_bottom = title_bottom - body_height

    _add_box(layout, x_left, title_bottom, x_right, y_top, border_layer)
    _add_box(layout, x_left, body_bottom, x_right, title_bottom, border_layer)

    layout.add_text(title, dxfattribs={"layer": text_layer, "height": 2.2}).set_placement((x_left + 1.2, y_top - 3.4))

    text_y = title_bottom - 3.5
    for line in body_lines[:4]:
        layout.add_text(line[:56], dxfattribs={"layer": text_layer, "height": 1.9}).set_placement((x_left + 1.2, text_y))
        text_y -= 3.4

    return body_bottom


def _draw_common_right_panel(layout: Any, metadata: dict[str, str]) -> None:
    border_layer = "CADREAM-TEMPLATE-BORDER"
    text_layer = "CADREAM-TEMPLATE-TEXT"
    grid_layer = "CADREAM-TEMPLATE-GRID"

    _add_box(layout, SHEET_MARGIN, SHEET_MARGIN, SHEET_WIDTH - SHEET_MARGIN, SHEET_HEIGHT - SHEET_MARGIN, border_layer)
    layout.add_line((PANEL_LEFT, PANEL_BOTTOM), (PANEL_LEFT, PANEL_TOP), dxfattribs={"layer": border_layer})

    x_left = PANEL_LEFT
    x_right = PANEL_RIGHT
    width = x_right - x_left
    y = PANEL_TOP

    def draw_heading_box(title: str, total_h: float, heading_h: float = 6.2) -> tuple[float, float, float]:
        nonlocal y
        y_bottom = y - total_h
        _add_box(layout, x_left, y_bottom, x_right, y, grid_layer)
        layout.add_line((x_left, y - heading_h), (x_right, y - heading_h), dxfattribs={"layer": grid_layer})
        layout.add_text(title, dxfattribs={"layer": text_layer, "height": 2.2}).set_placement((x_left + 1.0, y - 4.2))
        return y_bottom, y - heading_h, total_h

    # 1) SYSTEM INFORMATION
    y_bottom, content_top, _ = draw_heading_box("SYSTEM INFORMATION", 38.0)
    info_lines = [
        f"AC System Size: {metadata.get('AC System Size', '')}",
        f"Inverter Model: {metadata.get('Inverter Model', '')}",
        f"DC System Size: {metadata.get('DC System Size', '')}",
        f"BESS: {metadata.get('BESS', '')}",
    ]
    text_y = content_top - 3.6
    for line in info_lines:
        layout.add_text(line[:58], dxfattribs={"layer": text_layer, "height": 1.8}).set_placement((x_left + 1.0, text_y))
        text_y -= 3.5
    y = y_bottom

    # 2) CUSTOMER INFORMATION
    y_bottom, content_top, _ = draw_heading_box("CUSTOMER INFORMATION", 40.0)
    customer_lines = [
        f"Name: {metadata.get('Customer Name', '')}",
        f"Address: {metadata.get('Customer Address', '')}",
        f"Website: {metadata.get('Customer Website', '')}",
        f"Phone: {metadata.get('Customer Phone', '')}",
        f"Contact: {metadata.get('Customer Contact', '')}",
    ]
    text_y = content_top - 3.6
    for line in customer_lines:
        layout.add_text(line[:58], dxfattribs={"layer": text_layer, "height": 1.8}).set_placement((x_left + 1.0, text_y))
        text_y -= 3.5
    y = y_bottom

    # 3) ENGINEER OF RECORD (signature image placeholder)
    y_bottom, content_top, _ = draw_heading_box("ENGINEER OF RECORD", 40.0)
    pad = 2.0
    _add_box(layout, x_left + pad, y_bottom + pad, x_right - pad, content_top - pad, grid_layer)
    layout.add_text("[Engineer Signature Image Placeholder]", dxfattribs={"layer": text_layer, "height": 1.7}).set_placement(
        (x_left + 6.0, (y_bottom + content_top) / 2)
    )
    y = y_bottom

    # 4) PREV/DATE/DESCRIPTION table (3 columns x 8 rows)
    table_h = 42.0
    y_bottom = y - table_h
    _add_box(layout, x_left, y_bottom, x_right, y, grid_layer)
    header_h = 6.0
    layout.add_line((x_left, y - header_h), (x_right, y - header_h), dxfattribs={"layer": grid_layer})
    col_prev = x_left + 10.0
    col_date = x_left + 26.0
    layout.add_line((col_prev, y_bottom), (col_prev, y), dxfattribs={"layer": grid_layer})
    layout.add_line((col_date, y_bottom), (col_date, y), dxfattribs={"layer": grid_layer})
    layout.add_text("PREV", dxfattribs={"layer": text_layer, "height": 1.8}).set_placement((x_left + 1.0, y - 4.0))
    layout.add_text("DATE", dxfattribs={"layer": text_layer, "height": 1.8}).set_placement((col_prev + 1.0, y - 4.0))
    layout.add_text("DESCRIPTION", dxfattribs={"layer": text_layer, "height": 1.8}).set_placement((col_date + 1.0, y - 4.0))
    body_h = table_h - header_h
    row_h = body_h / 8.0
    for row in range(1, 8):
        y_row = y - header_h - row * row_h
        layout.add_line((x_left, y_row), (x_right, y_row), dxfattribs={"layer": grid_layer})
    y = y_bottom

    # 5) AHJ (empty placeholder text field)
    y_bottom, content_top, _ = draw_heading_box("AHJ", 18.0)
    layout.add_text(metadata.get("AHJ", ""), dxfattribs={"layer": text_layer, "height": 1.8}).set_placement((x_left + 1.0, content_top - 3.8))
    y = y_bottom

    # 6) EQORE PROJECT (empty placeholder text field)
    y_bottom, content_top, _ = draw_heading_box("EQORE PROJECT", 18.0)
    layout.add_text(metadata.get("EQORE Project", ""), dxfattribs={"layer": text_layer, "height": 1.8}).set_placement(
        (x_left + 1.0, content_top - 3.8)
    )
    y = y_bottom

    # 7) DESIGNER
    y_bottom, content_top, _ = draw_heading_box("DESIGNER", 32.0)
    designer_lines = [
        f"Company: {metadata.get('Designer Company', '')}",
        f"Address: {metadata.get('Designer Address', '')}",
        f"Website: {metadata.get('Designer Website', '')}",
        f"Phone: {metadata.get('Designer Phone', '')}",
        f"Contact: {metadata.get('Designer Contact', '')}",
    ]
    text_y = content_top - 3.6
    for line in designer_lines:
        layout.add_text(line[:58], dxfattribs={"layer": text_layer, "height": 1.7}).set_placement((x_left + 1.0, text_y))
        text_y -= 3.1
    y = y_bottom

    # 8) PAGE NOTES
    y_bottom, content_top, _ = draw_heading_box("PAGE NOTES", 22.0)
    layout.add_text(metadata.get("Page Notes", ""), dxfattribs={"layer": text_layer, "height": 1.7}).set_placement((x_left + 1.0, content_top - 3.6))
    y = y_bottom

    # 9) Bottom small metadata grid
    meta_h = max(y - PANEL_BOTTOM, 16.0)
    y_bottom = y - meta_h
    _add_box(layout, x_left, y_bottom, x_right, y, grid_layer)
    labels = ["Scale", "Sheet", "Drawn By", "Checked By", "Approved By", "Date", "Sheet No", "Revision"]
    label_col = x_left + 20.0
    layout.add_line((label_col, y_bottom), (label_col, y), dxfattribs={"layer": grid_layer})
    row_h = meta_h / len(labels)
    for i in range(1, len(labels)):
        y_line = y - i * row_h
        layout.add_line((x_left, y_line), (x_right, y_line), dxfattribs={"layer": grid_layer})

    meta_values = {
        "Scale": metadata.get("Scale", "As Noted"),
        "Sheet": metadata.get("Sheet", ""),
        "Drawn By": metadata.get("Drawn By", ""),
        "Checked By": metadata.get("Checked By", ""),
        "Approved By": metadata.get("Approved By", ""),
        "Date": metadata.get("Date", ""),
        "Sheet No": metadata.get("Sheet No", ""),
        "Revision": metadata.get("Revision", ""),
    }

    for idx, label in enumerate(labels):
        y_text = y - idx * row_h - 3.0
        layout.add_text(label, dxfattribs={"layer": text_layer, "height": 1.45}).set_placement((x_left + 0.9, y_text))
        layout.add_text(meta_values[label][:34], dxfattribs={"layer": text_layer, "height": 1.45}).set_placement((label_col + 0.9, y_text))


def generate_common_template_sample_dxf(payload: dict[str, Any] | None = None) -> bytes:
    request_payload = payload if isinstance(payload, dict) else {}
    right_panel_payload = (
        request_payload.get("right_panel_metadata")
        if isinstance(request_payload.get("right_panel_metadata"), dict)
        else request_payload
    )
    title_block = right_panel_payload.get("title_block") if isinstance(right_panel_payload.get("title_block"), dict) else {}
    sheet_meta = right_panel_payload.get("sheet_metadata") if isinstance(right_panel_payload.get("sheet_metadata"), dict) else {}
    signature_payload = (
        right_panel_payload.get("engineer_signature_image")
        if isinstance(right_panel_payload.get("engineer_signature_image"), dict)
        else {}
    )

    metadata = {
        "Sheet No": _safe_str(sheet_meta.get("sheet_number"), "01"),
        "Sheet": _safe_str(sheet_meta.get("sheet_title"), "Page 1"),
        "Scale": _safe_str(sheet_meta.get("scale"), "As Noted"),
        "Date": _safe_str(sheet_meta.get("issue_date"), date.today().isoformat()),
        "Drawn By": _safe_str(title_block.get("drawn_by"), "DG"),
        "Checked By": _safe_str(title_block.get("checked_by"), "DG"),
        "Approved By": _safe_str(title_block.get("approved_by"), "A"),
        "Revision": _safe_str(sheet_meta.get("revision"), "A"),
        "AC System Size": _safe_str(right_panel_payload.get("ac_system_size"), "380kW"),
        "DC System Size": _safe_str(right_panel_payload.get("dc_system_size"), "760kWh"),
        "Inverter Model": _safe_str(right_panel_payload.get("inverter_model"), "Dynapower CPS1250"),
        "BESS": _safe_str(right_panel_payload.get("bess_model"), "Gotion Edge 760"),
        "Customer Name": _safe_str(title_block.get("client_name"), ""),
        "Customer Address": _safe_str(title_block.get("site_address"), ""),
        "Customer Website": _safe_str(right_panel_payload.get("customer_website"), ""),
        "Customer Phone": _safe_str(right_panel_payload.get("customer_phone"), ""),
        "Customer Contact": _safe_str(right_panel_payload.get("customer_contact"), ""),
        "AHJ": _safe_str(right_panel_payload.get("ahj"), ""),
        "EQORE Project": _safe_str(title_block.get("project_name"), ""),
        "Designer Company": _safe_str(right_panel_payload.get("designer_company"), "CADream"),
        "Designer Address": _safe_str(right_panel_payload.get("designer_address"), ""),
        "Designer Website": _safe_str(right_panel_payload.get("designer_website"), ""),
        "Designer Phone": _safe_str(right_panel_payload.get("designer_phone"), ""),
        "Designer Contact": _safe_str(right_panel_payload.get("designer_contact"), ""),
        "Page Notes": _safe_str(right_panel_payload.get("page_notes"), ""),
    }

    has_signature = any(
        isinstance(signature_payload.get(key), str) and signature_payload.get(key).strip() for key in ("base64", "uri")
    )
    if has_signature:
        metadata["Page Notes"] = (metadata["Page Notes"] + " | Signature Provided").strip(" |")

    doc = ezdxf.new("R2010")
    _ensure_layer(doc, "CADREAM-TEMPLATE-BORDER", 8)
    _ensure_layer(doc, "CADREAM-TEMPLATE-GRID", 8)
    _ensure_layer(doc, "CADREAM-TEMPLATE-TEXT", 5)

    layout = doc.modelspace()
    _draw_common_right_panel(layout, metadata)

    stream = StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")
