from __future__ import annotations

import base64
from datetime import date
from io import BytesIO
from typing import Any

from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from planset_manifest import build_plan_set_manifest


def _safe_str(value: Any, fallback: str = "") -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _resolve_right_panel_payload(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = payload.get("right_panel_metadata")
    if isinstance(candidate, dict):
        return candidate
    return payload


def _extract_signature_image_bytes(engineer_signature_image: Any) -> bytes | None:
    if not isinstance(engineer_signature_image, dict):
        return None

    base64_value = engineer_signature_image.get("base64")
    if isinstance(base64_value, str) and base64_value.strip():
        try:
            return base64.b64decode(base64_value, validate=False)
        except Exception:
            return None

    uri_value = engineer_signature_image.get("uri")
    if isinstance(uri_value, str) and uri_value.startswith("data:") and "," in uri_value:
        try:
            encoded = uri_value.split(",", 1)[1]
            return base64.b64decode(encoded, validate=False)
        except Exception:
            return None

    return None


def _build_right_panel_metadata(payload: dict[str, Any], page_number: int) -> tuple[dict[str, str], bytes | None]:
    right_panel_payload = _resolve_right_panel_payload(payload)
    title_block = right_panel_payload.get("title_block") if isinstance(right_panel_payload.get("title_block"), dict) else {}
    sheet_metadata = (
        right_panel_payload.get("sheet_metadata") if isinstance(right_panel_payload.get("sheet_metadata"), dict) else {}
    )

    metadata = {
        "Sheet No": _safe_str(sheet_metadata.get("sheet_number"), str(page_number).zfill(2)),
        "Sheet": _safe_str(sheet_metadata.get("sheet_title"), f"Page {page_number}"),
        "Scale": _safe_str(sheet_metadata.get("scale"), "As Noted"),
        "Date": _safe_str(sheet_metadata.get("issue_date"), date.today().isoformat()),
        "Drawn By": _safe_str(sheet_metadata.get("drawn_by"), _safe_str(title_block.get("drawn_by"), "DG")),
        "Checked By": _safe_str(sheet_metadata.get("checked_by"), _safe_str(title_block.get("checked_by"), "DG")),
        "Approved By": _safe_str(sheet_metadata.get("approved_by"), _safe_str(title_block.get("approved_by"), "A")),
        "Revision": _safe_str(sheet_metadata.get("revision"), "A"),
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

    signature_bytes = _extract_signature_image_bytes(right_panel_payload.get("engineer_signature_image"))
    return metadata, signature_bytes


def _draw_box(pdf: canvas.Canvas, x: float, y: float, w: float, h: float) -> None:
    pdf.rect(x, y, w, h)


def _draw_signature_box(
    pdf: canvas.Canvas,
    *,
    x: float,
    y_bottom: float,
    width: float,
    height: float,
    signature_image_bytes: bytes | None,
) -> None:
    inset = 2 * mm
    box_x = x + inset
    box_y = y_bottom + inset
    box_w = width - 2 * inset
    box_h = height - 2 * inset
    _draw_box(pdf, box_x, box_y, box_w, box_h)

    if not signature_image_bytes:
        pdf.setFont("Helvetica", 6.5)
        pdf.drawCentredString(x + width / 2, y_bottom + height / 2, "[Engineer Signature Image Placeholder]")
        return

    try:
        image = ImageReader(BytesIO(signature_image_bytes))
        img_w, img_h = image.getSize()
        if img_w <= 0 or img_h <= 0:
            raise ValueError("Invalid signature image dimensions")

        scale = min(box_w / img_w, box_h / img_h)
        draw_w = img_w * scale
        draw_h = img_h * scale
        draw_x = box_x + (box_w - draw_w) / 2
        draw_y = box_y + (box_h - draw_h) / 2
        pdf.drawImage(image, draw_x, draw_y, width=draw_w, height=draw_h, preserveAspectRatio=True, mask="auto")
    except Exception:
        pdf.setFont("Helvetica", 6.2)
        pdf.drawCentredString(x + width / 2, y_bottom + height / 2, "[Invalid Engineer Signature Image]")


def _draw_right_template_panel(
    pdf: canvas.Canvas,
    *,
    page_w: float,
    page_h: float,
    metadata: dict[str, str],
    signature_image_bytes: bytes | None,
) -> None:
    margin = 5 * mm
    panel_w = 82 * mm
    x = page_w - margin - panel_w
    y_bottom = margin
    y_top = page_h - margin

    _draw_box(pdf, margin, margin, page_w - 2 * margin, page_h - 2 * margin)
    pdf.line(x, y_bottom, x, y_top)

    y = y_top

    def heading_box(title: str, total_h_mm: float, heading_h_mm: float = 6.2) -> tuple[float, float]:
        nonlocal y
        total_h = total_h_mm * mm
        heading_h = heading_h_mm * mm
        section_bottom = y - total_h
        _draw_box(pdf, x, section_bottom, panel_w, total_h)
        pdf.line(x, y - heading_h, x + panel_w, y - heading_h)
        pdf.setFont("Helvetica-Bold", 7.1)
        pdf.drawString(x + 1.2 * mm, y - 4.6 * mm, title)
        return section_bottom, y - heading_h

    # 1) SYSTEM INFORMATION
    section_bottom, content_top = heading_box("SYSTEM INFORMATION", 38.0)
    pdf.setFont("Helvetica", 6.8)
    lines = [
        f"AC System Size: {metadata.get('AC System Size', '')}",
        f"Inverter Model: {metadata.get('Inverter Model', '')}",
        f"DC System Size: {metadata.get('DC System Size', '')}",
        f"BESS: {metadata.get('BESS', '')}",
    ]
    ty = content_top - 3.8 * mm
    for line in lines:
        pdf.drawString(x + 1.2 * mm, ty, line[:70])
        ty -= 3.45 * mm
    y = section_bottom

    # 2) CUSTOMER INFORMATION
    section_bottom, content_top = heading_box("CUSTOMER INFORMATION", 40.0)
    customer_lines = [
        f"Name: {metadata.get('Customer Name', '')}",
        f"Address: {metadata.get('Customer Address', '')}",
        f"Website: {metadata.get('Customer Website', '')}",
        f"Phone: {metadata.get('Customer Phone', '')}",
        f"Contact: {metadata.get('Customer Contact', '')}",
    ]
    ty = content_top - 3.8 * mm
    for line in customer_lines:
        pdf.drawString(x + 1.2 * mm, ty, line[:70])
        ty -= 3.25 * mm
    y = section_bottom

    # 3) ENGINEER OF RECORD (signature image)
    section_bottom, content_top = heading_box("ENGINEER OF RECORD", 40.0)
    _draw_signature_box(
        pdf,
        x=x,
        y_bottom=section_bottom,
        width=panel_w,
        height=(content_top - section_bottom),
        signature_image_bytes=signature_image_bytes,
    )
    y = section_bottom

    # 4) PREV/DATE/DESCRIPTION table with 8 rows
    table_h = 42 * mm
    table_bottom = y - table_h
    _draw_box(pdf, x, table_bottom, panel_w, table_h)
    header_h = 6 * mm
    pdf.line(x, y - header_h, x + panel_w, y - header_h)
    col_prev = x + 10 * mm
    col_date = x + 26 * mm
    pdf.line(col_prev, table_bottom, col_prev, y)
    pdf.line(col_date, table_bottom, col_date, y)
    pdf.setFont("Helvetica-Bold", 6.8)
    pdf.drawString(x + 1.0 * mm, y - 4.2 * mm, "PREV")
    pdf.drawString(col_prev + 1.0 * mm, y - 4.2 * mm, "DATE")
    pdf.drawString(col_date + 1.0 * mm, y - 4.2 * mm, "DESCRIPTION")
    row_h = (table_h - header_h) / 8
    for row in range(1, 8):
        y_row = y - header_h - row * row_h
        pdf.line(x, y_row, x + panel_w, y_row)
    y = table_bottom

    # 5) AHJ
    section_bottom, content_top = heading_box("AHJ", 18.0)
    pdf.setFont("Helvetica", 6.8)
    pdf.drawString(x + 1.2 * mm, content_top - 3.8 * mm, metadata.get("AHJ", "")[:70])
    y = section_bottom

    # 6) EQORE PROJECT
    section_bottom, content_top = heading_box("EQORE PROJECT", 18.0)
    pdf.setFont("Helvetica", 6.8)
    pdf.drawString(x + 1.2 * mm, content_top - 3.8 * mm, metadata.get("EQORE Project", "")[:70])
    y = section_bottom

    # 7) DESIGNER
    section_bottom, content_top = heading_box("DESIGNER", 32.0)
    designer_lines = [
        f"Company: {metadata.get('Designer Company', '')}",
        f"Address: {metadata.get('Designer Address', '')}",
        f"Website: {metadata.get('Designer Website', '')}",
        f"Phone: {metadata.get('Designer Phone', '')}",
        f"Contact: {metadata.get('Designer Contact', '')}",
    ]
    pdf.setFont("Helvetica", 6.5)
    ty = content_top - 3.5 * mm
    for line in designer_lines:
        pdf.drawString(x + 1.2 * mm, ty, line[:70])
        ty -= 3.1 * mm
    y = section_bottom

    # 8) PAGE NOTES
    section_bottom, content_top = heading_box("PAGE NOTES", 22.0)
    pdf.setFont("Helvetica", 6.5)
    pdf.drawString(x + 1.2 * mm, content_top - 3.8 * mm, metadata.get("Page Notes", "")[:70])
    y = section_bottom

    # 9) bottom small metadata grid
    meta_h = max(y - y_bottom, 16 * mm)
    meta_bottom = y - meta_h
    _draw_box(pdf, x, meta_bottom, panel_w, meta_h)
    labels = ["Scale", "Sheet", "Drawn By", "Checked By", "Approved By", "Date", "Sheet No", "Revision"]
    label_col = x + 20 * mm
    pdf.line(label_col, meta_bottom, label_col, y)
    row_h = meta_h / len(labels)
    for row in range(1, len(labels)):
        y_row = y - row * row_h
        pdf.line(x, y_row, x + panel_w, y_row)

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
    pdf.setFont("Helvetica", 5.9)
    for idx, label in enumerate(labels):
        yt = y - idx * row_h - 4.2
        pdf.drawString(x + 0.8 * mm, yt, label)
        pdf.drawString(label_col + 0.8 * mm, yt, str(meta_values[label])[:40])


def _draw_content_preview(
    pdf: canvas.Canvas,
    *,
    page_w: float,
    page_h: float,
    page_info: dict[str, Any],
) -> None:
    return


def generate_planset_pages_pdf(payload: dict[str, Any]) -> bytes:
    manifest = build_plan_set_manifest(payload)
    pages = manifest.get("pages") if isinstance(manifest.get("pages"), list) else []

    page_size = landscape(A3)
    page_w, page_h = page_size

    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=page_size)

    for page in pages:
        if not isinstance(page, dict):
            continue

        page_number = int(page.get("page_number", 0))
        metadata, signature_image_bytes = _build_right_panel_metadata(payload, page_number)

        _draw_right_template_panel(
            pdf,
            page_w=page_w,
            page_h=page_h,
            metadata=metadata,
            signature_image_bytes=signature_image_bytes,
        )
        _draw_content_preview(pdf, page_w=page_w, page_h=page_h, page_info=page)
        pdf.showPage()

    pdf.save()
    return stream.getvalue()
