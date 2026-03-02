import asyncio

from planset_request_envelope import enrich_payload_with_normalized_inputs
from planset_manifest import build_plan_set_manifest
from planset_payload_stubs import build_plan_set_payload_stubs
from planset_pdf_export import generate_planset_pages_pdf, generate_planset_fixed_pages_pdf
from planset_sld_pages import export_sld_vertical_slice_zip
import main


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)

minimal_payload = {"total_pages": 49, "cad_ir": {"schemaVersion": "cad-ir-v1"}}
enriched_min = enrich_payload_with_normalized_inputs(minimal_payload)
manifest_min = build_plan_set_manifest(enriched_min)
assert_true(manifest_min["summary"]["total_pages"] == 49, "total pages mismatch")
assert_true("normalized_inputs" in enriched_min, "normalized inputs missing")

pdf_min = generate_planset_pages_pdf(enriched_min)
assert_true(pdf_min[:4] == b"%PDF", "minimal PDF invalid")

fixed_min = generate_planset_fixed_pages_pdf(enriched_min)
assert_true(fixed_min[:4] == b"%PDF", "fixed PDF invalid")

rich_payload = {
    "total_pages": 49,
    "cad_ir": {"schemaVersion": "cad-ir-v1"},
    "right_panel_metadata": {
        "title_block": {
            "project_name": "Demo Project",
            "client_name": "Hamza",
            "site_address": "Austin",
        }
    },
    "site_placements": {
        "entities": {
            "bess": [
                {"id": "b1", "cad_position": {"x": 10, "y": 20}, "cad_insert": {"xscale": 1, "rotation": 0}},
                {"id": "b2", "cad_position": {"x": 16, "y": 22}, "cad_insert": {"xscale": 1, "rotation": 0}},
            ],
            "poi": {"x": 60, "y": 50},
            "cable_paths": [
                {"id": "c1", "points": [[10, 20], [30, 20], [60, 50]]},
                {"id": "c2", "points": [[16, 22], [35, 24], [60, 50]]},
            ],
        }
    },
    "sld_session": {
        "nodes": [
            {"id": "n1", "symbol_type": "utility-meter", "x": 0, "y": 0, "label": "Meter"},
            {"id": "n2", "symbol_type": "main-disconnect", "x": 120, "y": 0, "label": "MDP"},
        ],
        "edges": [
            {"id": "e1", "from_node_id": "n1", "to_node_id": "n2", "points": [[0, 0], [120, 0]]}
        ],
    },
}

enriched = enrich_payload_with_normalized_inputs(rich_payload)
stubs = build_plan_set_payload_stubs(enriched)
required = {1,2,4,5,6,7,12,13,16,17,24,25,42,43}
seen = {
    item["page_number"]
    for item in stubs["page_payloads"]
    if item["status"] == "auto" and ((item.get("payload") or {}).get("content") or {}).get("entities")
}
assert_true(required.issubset(seen), "not all required auto pages emitted entities")

zip_bytes = export_sld_vertical_slice_zip(enriched)
assert_true(zip_bytes[:2] == b"PK", "SLD ZIP invalid")

pdf_rich = generate_planset_pages_pdf(enriched)
assert_true(pdf_rich[:4] == b"%PDF", "rich PDF invalid")

async def route_smoke():
    await main.preview_plan_set(rich_payload)
    await main.preview_plan_set_payload_stubs(rich_payload)
    await main.export_planset_pages_pdf(rich_payload)

asyncio.run(route_smoke())
print("ALL_SMOKE_CHECKS_PASSED")
