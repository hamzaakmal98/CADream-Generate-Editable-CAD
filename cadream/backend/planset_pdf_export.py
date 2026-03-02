from __future__ import annotations

import base64
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any
import threading

from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter, Transformation

from planset_manifest import AUTO_GENERATED_PAGES, build_plan_set_manifest


_DEFAULT_TEMPLATE_PDF_PATH = Path(__file__).resolve().parents[2] / "sample-files" / "Template_Project.pdf"

_TEMPLATE_PDF_CACHE_LOCK = threading.Lock()
_TEMPLATE_PDF_CACHE: dict[str, tuple[float, int, bytes]] = {}

_PAGE_TITLE_BY_NUMBER: dict[int, str] = {
    1: "Energy Storage System.",
    2: "Property Details",
    3: "EQORE System Overview",
    4: "Existing Switchgear",
    5: "Main Distribution Panel Detail",
    6: "Plan Overview & Total Impact Area",
    7: "Top View: Exterior Complete Expectation",
    8: "Top View: On-Pad Details",
    9: "Top View: Interior Conduit Run Details",
    10: "Conduit and Steel I-Beam Anchoring: Top View",
    11: "Equipment Attachment: Top View w/ Attachment Specs",
    12: "West View: Completed Expectation",
    13: "West View: Conduit Run & Interior",
    14: "West View: Conduit and Attachment details",
    15: "East View",
    16: "South View: Completed Expectation",
    17: "Conduit Run",
    18: "Interior Conduit Run Details",
    19: "South View: Outdoor Detail and Disconnect Details",
    20: "North View",
    21: "Concrete Slab Foundation Details",
    22: "Concrete Slab: Rebar Specification",
    23: "Concrete Slab: Steel I-Beam Specifications",
    24: "Single Line Diagram",
    25: "Line Diagram: Three Line",
    26: "Electrical Equipment: BESS Specifications",
    27: "Electrical Equipment: Inverter Specifications",
    28: "Electrical Equipment: Other Equipment Specifications",
    29: "Electrical Equipment: Other Equipment Specifications",
    30: "Electrical Equipment: Dynapower CPS1250",
    31: "Electrical Equipment: Isolation Transformer",
    32: "Electrical Equipment: Gotion Edge760",
    33: "Electrical Equipment: Gotion Edge760",
    34: "Electrical Equipment: Gotion Edge760",
    35: "Electrical Equipment: Disconnect & Breaker",
    36: "Electrical Calculations",
    37: "General Electrical Notes",
    38: "Other Lithium Batteries Safety",
    39: "Required Signage",
    40: "Fire Supression System: 1",
    41: "Fire Supression System: 2",
    42: "Fire Supression System: 3",
    43: "Fire Supression System: 4",
    44: "NFPA 855 Compliance: 1",
    45: "NFPA 855 Compliance: 2",
    46: "NFPA 855 Compliance: 3",
    47: "NFPA 855 Compliance: 4",
    48: "NFPA 855 Compliance: 5",
    49: "NFPA 855 Compliance: 6",
}


def _safe_str(value: Any, fallback: str = "") -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _resolve_right_panel_payload(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = payload.get("right_panel_metadata")
    if isinstance(candidate, dict):
        return candidate
    return payload


def _resolve_customer_name(payload: dict[str, Any]) -> str:
    right_panel_payload = _resolve_right_panel_payload(payload)
    title_block = right_panel_payload.get("title_block") if isinstance(right_panel_payload.get("title_block"), dict) else {}

    candidates = [
        title_block.get("client_name"),
        right_panel_payload.get("customer_name"),
        right_panel_payload.get("company_name"),
        title_block.get("company_name"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return "Customer Name"


def _resolve_page_title(page_number: int) -> str:
    return _PAGE_TITLE_BY_NUMBER.get(page_number, f"Page {page_number}")


def _resolve_generated_page_title(payload: dict[str, Any], page_number: int) -> str:
    right_panel_payload = _resolve_right_panel_payload(payload)
    customer_name = _resolve_customer_name(payload)
    ac_size = _safe_str(right_panel_payload.get("ac_system_size"), "_kW")
    dc_size = _safe_str(right_panel_payload.get("dc_system_size"), "_kWh")

    if page_number == 1:
        return f"{customer_name} - ({ac_size}, {dc_size}) Energy Storage System."

    if page_number in {2, 3, 4, 5, 6, 7}:
        return f"{customer_name} - {_resolve_page_title(page_number)}"

    if page_number == 8:
        return f"{customer_name} - Top View: On-Pad Details"

    if page_number == 9:
        return f"{customer_name} - Top View: Interior Conduit Run Details"

    if page_number == 10:
        return f"{customer_name} -  Conduit and Steel I-Beam Anchoring: Top View"

    if page_number == 11:
        return f"{customer_name} - Equipment Attachment: Top View w/ Attachment Specs"

    if page_number == 12:
        return f"{customer_name} -  West View: Completed Expectation"

    if page_number == 13:
        return f"{customer_name} - West View: Conduit Run & Interior"

    if page_number == 14:
        return f"{customer_name} -West View: Conduit and Attachment details"

    if page_number == 15:
        return f"{customer_name} - East View"

    if page_number == 16:
        return f"{customer_name} -South View: Completed Expectation"

    if page_number == 17:
        return f"{customer_name} - Conduit Run"

    if page_number == 18:
        return f"{customer_name} - Interior Conduit Run Details"

    if page_number == 19:
        return f"{customer_name} - South View: Outdoor Detail and Disconnect Details"

    if page_number == 20:
        return f"{customer_name} -  North View"

    if page_number == 21:
        return f"{customer_name} - Concrete Slab Foundation Details"

    if page_number == 22:
        return f"{customer_name} - Concrete Slab: Rebar Specification"

    if page_number == 23:
        return f"{customer_name} - Concrete Slab: Steel I-Beam Specifications"

    if page_number == 24:
        return f"{customer_name} - Single Line Diagram"

    if page_number == 25:
        return f"{customer_name} - Line Diagram: Three Line"

    if page_number == 26:
        return f"{customer_name} -  Electrical Equipment: BESS Specifications"

    if page_number == 27:
        return f"{customer_name} - Electrical Equipment: Inverter Specifications"

    if page_number == 28:
        return f"{customer_name} - Electrical Equipment: Other Equipment Specifications"

    if page_number == 29:
        return f"{customer_name} - Electrical Equipment: Other Equipment Specifications"

    if page_number == 30:
        return f"{customer_name} - Electrical Equipment: Dynapower CPS1250"

    if page_number == 31:
        return f"{customer_name} -  Electrical Equipment: Isolation Transformer"

    if page_number == 32:
        return f"{customer_name} -  Electrical Equipment: Gotion Edge760"

    if page_number == 33:
        return f"{customer_name} - Electrical Equipment: Gotion Edge760"

    if page_number == 34:
        return f"{customer_name} - Electrical Equipment: Gotion Edge760"

    if page_number == 35:
        return f"{customer_name} - Electrical Equipment: Disconnect & Breaker"

    return f"{customer_name} - {_resolve_page_title(page_number)}"


def _draw_generated_title_box(
    pdf: canvas.Canvas,
    *,
    page_w: float,
    page_h: float,
    title_text: str,
    right_crop_gutter_mm: float,
    title_box_height_mm: float,
) -> None:
    margin = 5 * mm
    panel_w = 82 * mm
    gutter = _mm_to_points(max(0.0, right_crop_gutter_mm))

    left_x = margin
    right_x = page_w - margin - panel_w - gutter
    if right_x <= left_x + 20:
        return

    box_h = _mm_to_points(max(6.0, title_box_height_mm))
    top_y = page_h - margin
    bottom_y = top_y - box_h

    _draw_box(pdf, left_x, bottom_y, right_x - left_x, box_h)
    pdf.setFont("Helvetica", 14)
    pdf.drawCentredString((left_x + right_x) / 2, bottom_y + box_h * 0.34, title_text[:110])


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


def _resolve_template_pdf_path(payload: dict[str, Any]) -> Path:
    custom_value = payload.get("fixed_template_pdf_path")
    if isinstance(custom_value, str) and custom_value.strip():
        candidate = Path(custom_value.strip())
        if not candidate.is_absolute():
            candidate = Path(__file__).resolve().parents[2] / candidate
        return candidate
    return _DEFAULT_TEMPLATE_PDF_PATH


def _load_template_pdf_bytes(template_path: Path) -> bytes:
    if not template_path.exists():
        raise FileNotFoundError(f"Template PDF not found: {template_path}")

    stat = template_path.stat()
    key = str(template_path.resolve())
    mtime = float(stat.st_mtime)
    size = int(stat.st_size)

    with _TEMPLATE_PDF_CACHE_LOCK:
        cached = _TEMPLATE_PDF_CACHE.get(key)
        if cached and cached[0] == mtime and cached[1] == size:
            return cached[2]

        data = template_path.read_bytes()
        _TEMPLATE_PDF_CACHE[key] = (mtime, size, data)
        return data


def _mm_to_points(mm_value: float) -> float:
    return mm_value * 72.0 / 25.4


def _fixed_page_numbers_from_manifest(pages: list[dict[str, Any]]) -> list[int]:
    fixed_pages: list[int] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        if page.get("generation_mode") != "fixed":
            continue
        page_number = page.get("page_number")
        if isinstance(page_number, int) and page_number > 0:
            fixed_pages.append(page_number)
    return fixed_pages


def _compose_fixed_left_panels(
    *,
    base_pdf_bytes: bytes,
    template_path: Path,
    fixed_page_numbers: list[int],
    right_crop_gutter_mm: float,
    left_panel_zoom: float,
    top_title_strip_mm: float,
    left_dest_expand_mm: float,
) -> bytes:
    base_reader = PdfReader(BytesIO(base_pdf_bytes))
    template_reader = PdfReader(BytesIO(_load_template_pdf_bytes(template_path)))
    writer = PdfWriter()

    fixed_page_set = set(fixed_page_numbers)

    for page_index, base_page in enumerate(base_reader.pages):
        page_number = page_index + 1
        writer.add_page(base_page)
        out_page = writer.pages[-1]

        if page_number not in fixed_page_set:
            continue

        template_index = page_number - 1
        if template_index >= len(template_reader.pages):
            raise ValueError(
                f"Template PDF has only {len(template_reader.pages)} pages; cannot map fixed page {page_number}"
            )

        page_w = float(out_page.mediabox.width)
        page_h = float(out_page.mediabox.height)
        margin = _mm_to_points(5.0)
        panel_w = _mm_to_points(82.0)
        split_x = page_w - margin - panel_w
        split_x_adjusted = split_x - _mm_to_points(max(0.0, right_crop_gutter_mm))
        if split_x_adjusted <= margin:
            split_x_adjusted = split_x

        split_x_adjusted = split_x_adjusted + _mm_to_points(max(0.0, left_dest_expand_mm))
        max_right = page_w - margin
        if split_x_adjusted > max_right:
            split_x_adjusted = max_right

        dest_x0 = margin
        dest_y0 = margin
        dest_x1 = split_x_adjusted
        dest_y1 = page_h - margin
        dest_w = dest_x1 - dest_x0
        dest_h = dest_y1 - dest_y0

        template_page_ref = template_reader.pages[template_index]
        template_w = float(template_page_ref.mediabox.width)
        template_h = float(template_page_ref.mediabox.height)

        src_x0 = template_w * (dest_x0 / page_w)
        src_x1 = template_w * (dest_x1 / page_w)
        src_y0 = template_h * (dest_y0 / page_h)
        src_y1 = template_h * (dest_y1 / page_h)
        src_y1 = src_y1 - _mm_to_points(max(0.0, top_title_strip_mm))
        src_w = src_x1 - src_x0
        src_h = src_y1 - src_y0

        if src_w <= 0 or src_h <= 0 or dest_w <= 0 or dest_h <= 0:
            continue

        zoom = left_panel_zoom if 0 < left_panel_zoom <= 1.0 else 1.0
        fit = min(dest_w / src_w, dest_h / src_h) * zoom
        draw_w = src_w * fit
        draw_h = src_h * fit
        pad_x = (dest_w - draw_w) / 2
        pad_y = (dest_h - draw_h) / 2
        translate_x = dest_x0 + pad_x - src_x0 * fit
        translate_y = dest_y0 + pad_y - src_y0 * fit

        temp_writer = PdfWriter()
        temp_writer.add_page(template_page_ref)
        left_panel = temp_writer.pages[0]
        left_panel.cropbox.lower_left = (src_x0, src_y0)
        left_panel.cropbox.upper_right = (src_x1, src_y1)
        left_panel.trimbox.lower_left = (src_x0, src_y0)
        left_panel.trimbox.upper_right = (src_x1, src_y1)

        transform = Transformation().scale(fit, fit).translate(translate_x, translate_y)
        out_page.merge_transformed_page(left_panel, transform)

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


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


def generate_planset_fixed_pages_pdf(payload: dict[str, Any]) -> bytes:
    manifest = build_plan_set_manifest(payload)
    pages = manifest.get("pages") if isinstance(manifest.get("pages"), list) else []
    fixed_page_numbers = _fixed_page_numbers_from_manifest(pages)

    full_pdf = generate_planset_pages_pdf(payload)
    full_reader = PdfReader(BytesIO(full_pdf))
    writer = PdfWriter()
    fixed_set = set(fixed_page_numbers)
    for idx, page in enumerate(full_reader.pages):
        if (idx + 1) in fixed_set:
            writer.add_page(page)

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def generate_planset_pages_pdf(payload: dict[str, Any]) -> bytes:
    manifest = build_plan_set_manifest(payload)
    pages = manifest.get("pages") if isinstance(manifest.get("pages"), list) else []
    fixed_page_numbers = _fixed_page_numbers_from_manifest(pages)

    right_crop_gutter_mm_raw = payload.get("fixed_left_crop_right_gutter_mm")
    if isinstance(right_crop_gutter_mm_raw, (int, float)):
        right_crop_gutter_mm = float(right_crop_gutter_mm_raw)
    else:
        right_crop_gutter_mm = 0.0

    left_panel_zoom_raw = payload.get("fixed_left_panel_zoom")
    if isinstance(left_panel_zoom_raw, (int, float)):
        left_panel_zoom = float(left_panel_zoom_raw)
    else:
        left_panel_zoom = 0.93

    top_title_strip_mm_raw = payload.get("fixed_left_crop_top_strip_mm")
    if isinstance(top_title_strip_mm_raw, (int, float)):
        top_title_strip_mm = float(top_title_strip_mm_raw)
    else:
        top_title_strip_mm = 30.0

    title_box_height_mm_raw = payload.get("generated_title_box_height_mm")
    if isinstance(title_box_height_mm_raw, (int, float)):
        title_box_height_mm = float(title_box_height_mm_raw)
    else:
        title_box_height_mm = 10.0

    left_dest_expand_mm_raw = payload.get("fixed_left_dest_expand_mm")
    if isinstance(left_dest_expand_mm_raw, (int, float)):
        left_dest_expand_mm = float(left_dest_expand_mm_raw)
    else:
        left_dest_expand_mm = 6.0

    page_size = landscape(A3)
    page_w, page_h = page_size

    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=page_size)

    for page in pages:
        if not isinstance(page, dict):
            continue

        page_number = int(page.get("page_number", 0))
        metadata, signature_image_bytes = _build_right_panel_metadata(payload, page_number)
        metadata["Sheet No"] = str(page_number).zfill(2)
        if not metadata.get("Sheet"):
            metadata["Sheet"] = f"Page {page_number}"

        generated_title_text = _resolve_generated_page_title(payload, page_number)

        _draw_generated_title_box(
            pdf,
            page_w=page_w,
            page_h=page_h,
            title_text=generated_title_text,
            right_crop_gutter_mm=right_crop_gutter_mm,
            title_box_height_mm=title_box_height_mm,
        )

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
    base_pdf_bytes = stream.getvalue()

    template_path = _resolve_template_pdf_path(payload)
    if not template_path.exists():
        raise FileNotFoundError(f"Template PDF not found: {template_path}")

    return _compose_fixed_left_panels(
        base_pdf_bytes=base_pdf_bytes,
        template_path=template_path,
        fixed_page_numbers=fixed_page_numbers,
        right_crop_gutter_mm=right_crop_gutter_mm,
        left_panel_zoom=left_panel_zoom,
        top_title_strip_mm=top_title_strip_mm,
        left_dest_expand_mm=left_dest_expand_mm,
    )
