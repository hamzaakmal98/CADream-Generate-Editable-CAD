from __future__ import annotations

from typing import Any


SITE_PAGE_PROFILE_VERSION = "site-page-profiles-v1"

PAGE_TITLE_NAMING_SPECS: dict[int, str] = {
    1: "Customer Name - (_kW, _kWh) Energy Storage System.",
    2: "Customer Name - Property Details",
    3: "Customer Name - EQORE System Overview",
    4: "Customer Name - Existing Switchgear",
    5: "Customer Name - Main Distribution Panel Detail",
    6: "Customer Name - Plan Overview & Total Impact Area",
    7: "Customer Name - Top View: Exterior Complete Expectation",
    8: "Customer Name - Top View: On-Pad Details",
    9: "Customer Name - Top View: Interior Conduit Run Details",
    10: "Customer Name - Conduit and Steel I-Beam Anchoring: Top View",
    11: "Customer Name - Equipment Attachment: Top View w/ Attachment Specs",
    12: "Customer Name - West View: Completed Expectation",
    13: "Customer Name - West View: Conduit Run & Interior",
    14: "Customer Name - West View: Conduit and Attachment details",
    15: "Customer Name - East View",
    16: "Customer Name - South View: Completed Expectation",
    17: "Customer Name - Conduit Run",
    18: "Customer Name - Interior Conduit Run Details",
    19: "Customer Name - South View: Outdoor Detail and Disconnect Details",
    20: "Customer Name - North View",
    21: "Customer Name - Concrete Slab Foundation Details",
    22: "Customer Name - Concrete Slab: Rebar Specification",
    23: "Customer Name - Concrete Slab: Steel I-Beam Specifications",
    24: "Customer Name - Single Line Diagram",
    25: "Customer Name - Line Diagram: Three Line",
    26: "Customer Name - Electrical Equipment: BESS Specifications",
    27: "Customer Name - Electrical Equipment: Inverter Specifications",
    28: "Customer Name - Electrical Equipment: Other Equipment Specifications",
    29: "Customer Name - Electrical Equipment: Other Equipment Specifications",
    30: "Customer Name - Electrical Equipment: Dynapower CPS1250",
    31: "Customer Name - Electrical Equipment: Isolation Transformer",
    32: "Customer Name - Electrical Equipment: Gotion Edge760",
    33: "Customer Name - Electrical Equipment: Gotion Edge760",
    34: "Customer Name - Electrical Equipment: Gotion Edge760",
    35: "Customer Name - Electrical Equipment: Disconnect & Breaker",
    36: "Customer Name - Electrical Calculations",
    37: "Customer Name - General Electrical Notes",
    38: "Customer Name - Other Lithium Batteries Safety",
    39: "Customer Name - Required Signage",
    40: "Customer Name - Fire Supression System: 1",
    41: "Customer Name - Fire Supression System: 2",
    42: "Customer Name - Fire Supression System: 3",
    43: "Customer Name - Fire Supression System: 4",
    44: "Customer Name - NFPA 855 Compliance: 1",
    45: "Customer Name - NFPA 855 Compliance: 2",
    46: "Customer Name - NFPA 855 Compliance: 3",
    47: "Customer Name - NFPA 855 Compliance: 4",
    48: "Customer Name - NFPA 855 Compliance: 5",
    49: "Customer Name - NFPA 855 Compliance: 6",
}


def _profile(
    page_number: int,
    sheet_title: str,
    purpose: str,
    view_strategy: str,
    required_inputs: list[str],
    layers: list[str],
    annotations: list[str],
) -> dict[str, Any]:
    return {
        "page_number": page_number,
        "sheet_title": sheet_title,
        "purpose": purpose,
        "view_strategy": view_strategy,
        "required_inputs": required_inputs,
        "layers": layers,
        "annotations": annotations,
        "editable_entities": [
            "block_insert",
            "polyline",
            "text",
            "leader",
        ],
    }


CORE_SITE_PAGE_PROFILES: list[dict[str, Any]] = [
    _profile(
        1,
        "Customer Name - (_kW, _kWh) Energy Storage System.",
        "Primary plan sheet with full site context, BESS placement, POI, and main routing corridor.",
        "fit-all-site-geometry",
        ["cad_ir", "site_plan"],
        ["CADREAM-P01-BORDER", "CADREAM-P01-EQUIP", "CADREAM-P01-CABLE", "CADREAM-P01-ANNO", "CADREAM-P01-TITLE"],
        ["north_arrow", "scale_note", "keyed_callouts", "bess_tags", "poi_tag"],
    ),
    _profile(
        2,
        "Customer Name - Property Details",
        "Enlarged equipment-side layout focused on BESS cluster and near-field access clearances.",
        "fit-bess-cluster-with-padding",
        ["cad_ir", "site_plan"],
        ["CADREAM-P02-BORDER", "CADREAM-P02-EQUIP", "CADREAM-P02-CABLE", "CADREAM-P02-ANNO", "CADREAM-P02-TITLE"],
        ["north_arrow", "scale_note", "clearance_dims", "bess_tags"],
    ),
    _profile(
        4,
        "Customer Name - Existing Switchgear",
        "Primary cable path plan from BESS to POI with route geometry and segment callouts.",
        "fit-cable-network",
        ["cad_ir", "site_plan"],
        ["CADREAM-P04-BORDER", "CADREAM-P04-EQUIP", "CADREAM-P04-CABLE", "CADREAM-P04-ANNO", "CADREAM-P04-TITLE"],
        ["north_arrow", "scale_note", "route_segments", "turn_markers", "poi_tag"],
    ),
    _profile(
        5,
        "Customer Name - Main Distribution Panel Detail",
        "Routing variant emphasizing conduit or trench pathing, bends, and transition points.",
        "fit-cable-network-focused",
        ["cad_ir", "site_plan"],
        ["CADREAM-P05-BORDER", "CADREAM-P05-EQUIP", "CADREAM-P05-CABLE", "CADREAM-P05-ANNO", "CADREAM-P05-TITLE"],
        ["north_arrow", "scale_note", "segment_lengths", "bend_callouts"],
    ),
    _profile(
        6,
        "Customer Name - Plan Overview & Total Impact Area",
        "POI-side interconnection zone with terminal equipment context and approach route.",
        "fit-poi-zone-with-buffer",
        ["cad_ir", "site_plan"],
        ["CADREAM-P06-BORDER", "CADREAM-P06-EQUIP", "CADREAM-P06-CABLE", "CADREAM-P06-ANNO", "CADREAM-P06-TITLE"],
        ["north_arrow", "scale_note", "poi_detail_tag", "equipment_refs"],
    ),
    _profile(
        7,
        "Customer Name - Top View: Exterior Complete Expectation",
        "BESS installation and access-oriented plan with placement references and access corridor notes.",
        "fit-bess-and-access-corridor",
        ["cad_ir", "site_plan"],
        ["CADREAM-P07-BORDER", "CADREAM-P07-EQUIP", "CADREAM-P07-CABLE", "CADREAM-P07-ANNO", "CADREAM-P07-TITLE"],
        ["north_arrow", "scale_note", "access_notes", "equipment_tags"],
    ),
]


FOLLOW_ON_SITE_PAGE_PROFILES: list[dict[str, Any]] = [
    _profile(
        12,
        "Site Notes + Keyed Plan",
        "Keyed site references and plan notes aligned to placement and route geometry.",
        "fit-site-with-note-zones",
        ["cad_ir", "site_plan"],
        ["CADREAM-P12-BORDER", "CADREAM-P12-EQUIP", "CADREAM-P12-CABLE", "CADREAM-P12-ANNO", "CADREAM-P12-TITLE"],
        ["north_arrow", "key_notes", "callout_index"],
    ),
    _profile(
        13,
        "Equipment Label Plan",
        "Tag-centric view with explicit equipment identifiers and reference markers.",
        "fit-bess-cluster-with-label-priority",
        ["cad_ir", "site_plan"],
        ["CADREAM-P13-BORDER", "CADREAM-P13-EQUIP", "CADREAM-P13-CABLE", "CADREAM-P13-ANNO", "CADREAM-P13-TITLE"],
        ["north_arrow", "equipment_tags", "reference_markers"],
    ),
    _profile(
        16,
        "Routing Detail A",
        "Detailed route segment breakdown for high-density or turning regions.",
        "fit-densest-route-region",
        ["cad_ir", "site_plan"],
        ["CADREAM-P16-BORDER", "CADREAM-P16-EQUIP", "CADREAM-P16-CABLE", "CADREAM-P16-ANNO", "CADREAM-P16-TITLE"],
        ["north_arrow", "segment_lengths", "detail_bubbles"],
    ),
    _profile(
        17,
        "Routing Detail B",
        "Secondary detailed routing region complementary to page 16.",
        "fit-second-densest-route-region",
        ["cad_ir", "site_plan"],
        ["CADREAM-P17-BORDER", "CADREAM-P17-EQUIP", "CADREAM-P17-CABLE", "CADREAM-P17-ANNO", "CADREAM-P17-TITLE"],
        ["north_arrow", "segment_lengths", "detail_bubbles"],
    ),
    _profile(
        42,
        "Civil / Utility Context A",
        "Context-oriented site overlay emphasizing utility corridor relation to route.",
        "fit-route-plus-utility-context",
        ["cad_ir", "site_plan"],
        ["CADREAM-P42-BORDER", "CADREAM-P42-EQUIP", "CADREAM-P42-CABLE", "CADREAM-P42-ANNO", "CADREAM-P42-TITLE"],
        ["north_arrow", "context_notes", "corridor_callouts"],
    ),
    _profile(
        43,
        "Civil / Utility Context B",
        "Companion context sheet for alternate corridor or tie-in area.",
        "fit-poi-context-emphasis",
        ["cad_ir", "site_plan"],
        ["CADREAM-P43-BORDER", "CADREAM-P43-EQUIP", "CADREAM-P43-CABLE", "CADREAM-P43-ANNO", "CADREAM-P43-TITLE"],
        ["north_arrow", "context_notes", "tie_in_callouts"],
    ),
]


def get_site_page_profiles(*, include_follow_on: bool = True) -> dict[str, Any]:
    profiles = list(CORE_SITE_PAGE_PROFILES)
    if include_follow_on:
        profiles.extend(FOLLOW_ON_SITE_PAGE_PROFILES)

    return {
        "schema_version": SITE_PAGE_PROFILE_VERSION,
        "core_pages": [profile["page_number"] for profile in CORE_SITE_PAGE_PROFILES],
        "follow_on_pages": [profile["page_number"] for profile in FOLLOW_ON_SITE_PAGE_PROFILES],
        "profiles": sorted(profiles, key=lambda item: int(item["page_number"])),
    }


def get_site_page_profile(page_number: int) -> dict[str, Any] | None:
    all_profiles = get_site_page_profiles(include_follow_on=True)["profiles"]
    for profile in all_profiles:
        if int(profile["page_number"]) == int(page_number):
            return profile
    return None
