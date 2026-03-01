from __future__ import annotations

from typing import Any

AUTO_GENERATED_PAGES = [1, 2, 4, 5, 6, 7, 12, 13, 16, 17, 24, 25, 42, 43]
SITE_PLAN_AUTO_PAGES = [1, 2, 4, 5, 6, 7, 12, 13, 16, 17, 42, 43]
SLD_AUTO_PAGES = [24, 25]


def _has_cad_ir_input(cad_ir: Any) -> tuple[bool, list[str]]:
    if not isinstance(cad_ir, dict):
        return False, ["cad_ir payload missing"]

    if cad_ir.get("schemaVersion") != "cad-ir-v1":
        return False, ["cad_ir.schemaVersion must be cad-ir-v1"]

    return True, []


def _has_site_inputs(site_placements: Any) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    if not isinstance(site_placements, dict):
        return False, ["site_placements payload missing"]

    entities = site_placements.get("entities")
    if not isinstance(entities, dict):
        return False, ["site_placements.entities missing"]

    bess = entities.get("bess")
    cables = entities.get("cable_paths")
    poi = entities.get("poi")

    has_bess = isinstance(bess, list) and len(bess) > 0
    has_cables = isinstance(cables, list) and len(cables) > 0
    has_poi = isinstance(poi, dict) and isinstance(poi.get("x"), (int, float)) and isinstance(poi.get("y"), (int, float))

    if not has_bess:
        reasons.append("missing BESS placements")
    if not has_cables:
        reasons.append("missing cable paths")
    if not has_poi:
        reasons.append("missing POI")

    return len(reasons) == 0, reasons


def _has_sld_inputs(sld_session: Any) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    if not isinstance(sld_session, dict):
        return False, ["sld_session payload missing"]

    nodes = sld_session.get("nodes")
    edges = sld_session.get("edges")

    has_nodes = isinstance(nodes, list) and len(nodes) > 0
    has_edges = isinstance(edges, list) and len(edges) > 0

    if not has_nodes:
        reasons.append("missing SLD nodes")
    if not has_edges:
        reasons.append("missing SLD edges")

    return len(reasons) == 0, reasons


def build_plan_set_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    total_pages_raw = payload.get("total_pages")
    total_pages = int(total_pages_raw) if isinstance(total_pages_raw, int) and total_pages_raw > 0 else 43

    cad_ir_ready, cad_ir_reasons = _has_cad_ir_input(payload.get("cad_ir"))
    site_ready, site_reasons = _has_site_inputs(payload.get("site_placements"))
    sld_ready, sld_reasons = _has_sld_inputs(payload.get("sld_session"))

    pages: list[dict[str, Any]] = []

    auto_page_set = set(AUTO_GENERATED_PAGES)
    site_page_set = set(SITE_PLAN_AUTO_PAGES)
    sld_page_set = set(SLD_AUTO_PAGES)

    for page_number in range(1, total_pages + 1):
        if page_number not in auto_page_set:
            pages.append(
                {
                    "page_number": page_number,
                    "generation_mode": "fixed",
                    "status": "fixed",
                    "requirements": [],
                }
            )
            continue

        requirements = ["cad_ir"]
        reasons: list[str] = []

        if not cad_ir_ready:
            reasons.extend(cad_ir_reasons)

        if page_number in site_page_set:
            requirements.append("site_plan")
            if not site_ready:
                reasons.extend(site_reasons)

        if page_number in sld_page_set:
            requirements.append("sld")
            if not sld_ready:
                reasons.extend(sld_reasons)

        status = "auto" if len(reasons) == 0 else "pending"

        pages.append(
            {
                "page_number": page_number,
                "generation_mode": "auto",
                "status": status,
                "requirements": requirements,
                "missing_reasons": reasons,
            }
        )

    auto_pages = [page for page in pages if page["status"] == "auto"]
    pending_pages = [page for page in pages if page["status"] == "pending"]
    fixed_pages = [page for page in pages if page["status"] == "fixed"]

    return {
        "schema_version": "planset-manifest-v1",
        "summary": {
            "total_pages": total_pages,
            "auto_pages": len(auto_pages),
            "fixed_pages": len(fixed_pages),
            "pending_pages": len(pending_pages),
        },
        "input_status": {
            "cad_ir": {
                "ready": cad_ir_ready,
                "missing_reasons": cad_ir_reasons,
            },
            "site_plan": {
                "ready": site_ready,
                "missing_reasons": site_reasons,
            },
            "sld": {
                "ready": sld_ready,
                "missing_reasons": sld_reasons,
            },
        },
        "pages": pages,
    }
