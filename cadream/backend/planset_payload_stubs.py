from __future__ import annotations

from datetime import date
from typing import Any

from planset_manifest import build_plan_set_manifest


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_sld_entities_for_page(payload: dict[str, Any], page_number: int) -> list[dict[str, Any]]:
    if page_number not in {24, 25}:
        return []

    sld_session = payload.get("sld_session")
    if not isinstance(sld_session, dict):
        return []

    nodes = sld_session.get("nodes")
    edges = sld_session.get("edges")

    if not isinstance(nodes, list) or not isinstance(edges, list):
        return []

    node_positions: dict[str, tuple[float, float]] = {}
    entities: list[dict[str, Any]] = []

    for node in nodes:
        if not isinstance(node, dict):
            continue

        node_id = node.get("id")
        if not isinstance(node_id, str):
            continue

        x = _to_float(node.get("x"), 0.0)
        y = _to_float(node.get("y"), 0.0)
        symbol_type = str(node.get("symbol_type", "generic"))
        label = str(node.get("label", symbol_type))

        node_positions[node_id] = (x, y)

        entities.append(
            {
                "kind": "block_insert",
                "layer": f"CADREAM-P{page_number}-EQUIP",
                "data": {
                    "block_name": f"SLD_{symbol_type.upper().replace('-', '_')}",
                    "x": x,
                    "y": y,
                    "rotation": _to_float(node.get("rotation_deg"), 0.0),
                },
            }
        )

        entities.append(
            {
                "kind": "text",
                "layer": f"CADREAM-P{page_number}-ANNO",
                "data": {
                    "text": f"{label}",
                    "x": x - 12.0,
                    "y": y - 10.0,
                    "height": 2.2,
                },
            }
        )

    for index, edge in enumerate(edges, start=1):
        if not isinstance(edge, dict):
            continue

        points = edge.get("points")
        poly_points: list[list[float]] = []

        if isinstance(points, list):
            for point in points:
                if isinstance(point, list) and len(point) >= 2:
                    poly_points.append([_to_float(point[0]), _to_float(point[1])])

        if len(poly_points) < 2:
            from_node = edge.get("from_node_id")
            to_node = edge.get("to_node_id")
            if isinstance(from_node, str) and isinstance(to_node, str):
                if from_node in node_positions and to_node in node_positions:
                    sx, sy = node_positions[from_node]
                    ex, ey = node_positions[to_node]
                    poly_points = [[sx, sy], [ex, ey]]

        if len(poly_points) < 2:
            continue

        if page_number == 24:
            entities.append(
                {
                    "kind": "polyline",
                    "layer": f"CADREAM-P{page_number}-WIRE",
                    "data": {
                        "points": poly_points,
                    },
                }
            )
        else:
            for offset in (-1.5, 0.0, 1.5):
                entities.append(
                    {
                        "kind": "polyline",
                        "layer": f"CADREAM-P{page_number}-WIRE",
                        "data": {
                            "points": [[x, y + offset] for x, y in poly_points],
                        },
                    }
                )

        mid = poly_points[len(poly_points) // 2]
        entities.append(
            {
                "kind": "text",
                "layer": f"CADREAM-P{page_number}-ANNO",
                "data": {
                    "text": f"W-{index:02d}" if page_number == 24 else f"3PH-W-{index:02d}",
                    "x": mid[0] + 1.5,
                    "y": mid[1] + 1.5,
                    "height": 2.0,
                },
            }
        )

    return entities


def _build_default_sheet_metadata(page_number: int) -> dict[str, Any]:
    return {
        "sheet_number": str(page_number).zfill(2),
        "sheet_title": f"Sheet {page_number}",
        "discipline": "Electrical",
        "scale": "NTS",
        "revision": "A",
        "issue_date": date.today().isoformat(),
        "north_arrow": page_number in {1, 2, 4, 5, 6, 7, 12, 13, 16, 17, 42, 43},
    }


def _build_default_title_block(payload: dict[str, Any]) -> dict[str, Any]:
    title_block = payload.get("title_block")
    if isinstance(title_block, dict):
        return {
            "project_name": str(title_block.get("project_name", "Untitled Project")),
            "client_name": str(title_block.get("client_name", "Unknown Client")),
            "site_name": str(title_block.get("site_name", "Unknown Site")),
            "site_address": str(title_block.get("site_address", "")),
            "project_number": str(title_block.get("project_number", "")),
            "drawn_by": str(title_block.get("drawn_by", "CADream")),
            "checked_by": str(title_block.get("checked_by", "")),
            "approved_by": str(title_block.get("approved_by", "")),
            "company_name": str(title_block.get("company_name", "")),
        }

    return {
        "project_name": "Untitled Project",
        "client_name": "Unknown Client",
        "site_name": "Unknown Site",
        "site_address": "",
        "project_number": "",
        "drawn_by": "CADream",
        "checked_by": "",
        "approved_by": "",
        "company_name": "",
    }


def _build_auto_stub(page_number: int, requirements: list[str], payload: dict[str, Any]) -> dict[str, Any]:
    generated_entities = _build_sld_entities_for_page(payload, page_number)

    return {
        "schema_version": "auto-page-payload-v1",
        "generation_mode": "auto",
        "page_number": page_number,
        "generator": {
            "name": "planset-orchestrator-stub",
            "version": "v1",
        },
        "sheet_metadata": _build_default_sheet_metadata(page_number),
        "title_block": _build_default_title_block(payload),
        "inputs_used": sorted(set(requirements + ["cad_ir"])),
        "content": {
            "entities": generated_entities,
            "notes": [
                "Stub payload generated by /planset/payload-stubs.",
                "Pages 24/25 apply SLD vertical-slice mapping rules for symbols, wires, and annotations.",
            ],
        },
    }


def _build_fixed_stub(page_number: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "fixed-page-payload-v1",
        "generation_mode": "fixed",
        "page_number": page_number,
        "template": {
            "template_id": f"page-{str(page_number).zfill(2)}-template",
            "include_strategy": "overlay_metadata",
            "source_path": f"templates/page-{str(page_number).zfill(2)}.dxf",
        },
        "sheet_metadata": _build_default_sheet_metadata(page_number),
        "title_block": _build_default_title_block(payload),
    }


def build_plan_set_payload_stubs(payload: dict[str, Any]) -> dict[str, Any]:
    manifest = build_plan_set_manifest(payload)

    page_payloads: list[dict[str, Any]] = []
    for page in manifest["pages"]:
        page_number = int(page["page_number"])
        status = str(page["status"])
        requirements = list(page.get("requirements", []))

        if status == "auto":
            page_payloads.append(
                {
                    "page_number": page_number,
                    "status": status,
                    "payload_schema": "auto-page-payload-v1",
                    "payload": _build_auto_stub(page_number, requirements, payload),
                }
            )
            continue

        if status == "fixed":
            page_payloads.append(
                {
                    "page_number": page_number,
                    "status": status,
                    "payload_schema": "fixed-page-payload-v1",
                    "payload": _build_fixed_stub(page_number, payload),
                }
            )
            continue

        page_payloads.append(
            {
                "page_number": page_number,
                "status": "pending",
                "payload_schema": None,
                "payload": None,
                "missing_reasons": page.get("missing_reasons", []),
            }
        )

    return {
        "schema_version": "planset-payload-stubs-v1",
        "manifest": manifest,
        "page_payloads": page_payloads,
    }
