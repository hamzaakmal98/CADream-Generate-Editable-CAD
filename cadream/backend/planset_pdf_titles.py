from __future__ import annotations

import base64
from datetime import date
from typing import Any

from planset_site_page_profiles import PAGE_TITLE_NAMING_SPECS


def safe_str(value: Any, fallback: str = "") -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def resolve_right_panel_payload(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = payload.get("right_panel_metadata")
    if isinstance(candidate, dict):
        return candidate
    return payload


def resolve_customer_name(payload: dict[str, Any]) -> str:
    right_panel_payload = resolve_right_panel_payload(payload)
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


def resolve_generated_page_title(payload: dict[str, Any], page_number: int) -> str:
    customer_name = resolve_customer_name(payload)
    right_panel_payload = resolve_right_panel_payload(payload)
    ac_size = safe_str(right_panel_payload.get("ac_system_size"), "_kW")
    dc_size = safe_str(right_panel_payload.get("dc_system_size"), "_kWh")

    title_template = PAGE_TITLE_NAMING_SPECS.get(page_number)
    if not isinstance(title_template, str) or not title_template.strip():
        return f"{customer_name} - Page {page_number}"

    return (
        title_template.replace("Customer Name", customer_name)
        .replace("(_kW, _kWh)", f"({ac_size}, {dc_size})")
        .strip()
    )


def extract_signature_image_bytes(engineer_signature_image: Any) -> bytes | None:
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


def build_right_panel_metadata(payload: dict[str, Any], page_number: int) -> tuple[dict[str, str], bytes | None]:
    right_panel_payload = resolve_right_panel_payload(payload)
    title_block = right_panel_payload.get("title_block") if isinstance(right_panel_payload.get("title_block"), dict) else {}
    sheet_metadata = (
        right_panel_payload.get("sheet_metadata") if isinstance(right_panel_payload.get("sheet_metadata"), dict) else {}
    )

    metadata = {
        "Sheet No": safe_str(sheet_metadata.get("sheet_number"), str(page_number).zfill(2)),
        "Sheet": safe_str(sheet_metadata.get("sheet_title"), f"Page {page_number}"),
        "Scale": safe_str(sheet_metadata.get("scale"), "As Noted"),
        "Date": safe_str(sheet_metadata.get("issue_date"), date.today().isoformat()),
        "Drawn By": safe_str(sheet_metadata.get("drawn_by"), safe_str(title_block.get("drawn_by"), "DG")),
        "Checked By": safe_str(sheet_metadata.get("checked_by"), safe_str(title_block.get("checked_by"), "DG")),
        "Approved By": safe_str(sheet_metadata.get("approved_by"), safe_str(title_block.get("approved_by"), "A")),
        "Revision": safe_str(sheet_metadata.get("revision"), "A"),
        "AC System Size": safe_str(right_panel_payload.get("ac_system_size"), "380kW"),
        "DC System Size": safe_str(right_panel_payload.get("dc_system_size"), "760kWh"),
        "Inverter Model": safe_str(right_panel_payload.get("inverter_model"), "Dynapower CPS1250"),
        "BESS": safe_str(right_panel_payload.get("bess_model"), "Gotion Edge 760"),
        "Customer Name": safe_str(title_block.get("client_name"), ""),
        "Customer Address": safe_str(title_block.get("site_address"), ""),
        "Customer Website": safe_str(right_panel_payload.get("customer_website"), ""),
        "Customer Phone": safe_str(right_panel_payload.get("customer_phone"), ""),
        "Customer Contact": safe_str(right_panel_payload.get("customer_contact"), ""),
        "AHJ": safe_str(right_panel_payload.get("ahj"), ""),
        "EQORE Project": safe_str(title_block.get("project_name"), ""),
        "Designer Company": safe_str(right_panel_payload.get("designer_company"), "CADream"),
        "Designer Address": safe_str(right_panel_payload.get("designer_address"), ""),
        "Designer Website": safe_str(right_panel_payload.get("designer_website"), ""),
        "Designer Phone": safe_str(right_panel_payload.get("designer_phone"), ""),
        "Designer Contact": safe_str(right_panel_payload.get("designer_contact"), ""),
        "Page Notes": safe_str(right_panel_payload.get("page_notes"), ""),
    }

    signature_bytes = extract_signature_image_bytes(right_panel_payload.get("engineer_signature_image"))
    return metadata, signature_bytes
