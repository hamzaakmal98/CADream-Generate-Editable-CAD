from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


_SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
_PROJECT_METADATA_VALIDATOR = Draft202012Validator(
    json.loads((_SCHEMA_DIR / "project-metadata.schema.json").read_text(encoding="utf-8"))
)
_SITE_DESIGN_SPEC_VALIDATOR = Draft202012Validator(
    json.loads((_SCHEMA_DIR / "site-design-spec.schema.json").read_text(encoding="utf-8"))
)
_SLD_DESIGN_SPEC_VALIDATOR = Draft202012Validator(
    json.loads((_SCHEMA_DIR / "sld-design-spec.schema.json").read_text(encoding="utf-8"))
)


def _safe_str(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_project_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    right_panel = payload.get("right_panel_metadata") if isinstance(payload.get("right_panel_metadata"), dict) else payload
    title_block = right_panel.get("title_block") if isinstance(right_panel.get("title_block"), dict) else {}

    return {
        "schema_version": "project-metadata-v1",
        "project_name": _safe_str(title_block.get("project_name"), "Untitled Project"),
        "client_name": _safe_str(title_block.get("client_name"), "Unknown Client"),
        "site_address": _safe_str(title_block.get("site_address"), "Unknown Site Address"),
        "ac_system_size": _safe_str(right_panel.get("ac_system_size"), "_kW"),
        "dc_system_size": _safe_str(right_panel.get("dc_system_size"), "_kWh"),
        "customer_contact": _safe_str(right_panel.get("customer_contact"), ""),
        "customer_phone": _safe_str(right_panel.get("customer_phone"), ""),
        "customer_website": _safe_str(right_panel.get("customer_website"), ""),
        "ahj": _safe_str(right_panel.get("ahj"), ""),
        "designer": {
            "company": _safe_str(right_panel.get("designer_company"), "CADream"),
            "address": _safe_str(right_panel.get("designer_address"), ""),
            "website": _safe_str(right_panel.get("designer_website"), ""),
            "phone": _safe_str(right_panel.get("designer_phone"), ""),
            "contact": _safe_str(right_panel.get("designer_contact"), ""),
        },
        "sheet_defaults": {
            "scale": _safe_str(right_panel.get("sheet_metadata", {}).get("scale") if isinstance(right_panel.get("sheet_metadata"), dict) else "", "As Noted"),
            "drawn_by": _safe_str(title_block.get("drawn_by"), "DG"),
            "checked_by": _safe_str(title_block.get("checked_by"), "DG"),
            "approved_by": _safe_str(title_block.get("approved_by"), "A"),
            "issue_date": _safe_str(right_panel.get("sheet_metadata", {}).get("issue_date") if isinstance(right_panel.get("sheet_metadata"), dict) else "", "1970-01-01"),
            "revision": _safe_str(right_panel.get("sheet_metadata", {}).get("revision") if isinstance(right_panel.get("sheet_metadata"), dict) else "", "A"),
        },
    }


def _normalize_site_design_spec(payload: dict[str, Any]) -> dict[str, Any]:
    site_placements = payload.get("site_placements") if isinstance(payload.get("site_placements"), dict) else {}
    entities = site_placements.get("entities") if isinstance(site_placements.get("entities"), dict) else {}

    bess_items: list[dict[str, Any]] = []
    raw_bess = entities.get("bess") if isinstance(entities.get("bess"), list) else []
    for index, bess in enumerate(raw_bess, start=1):
        if not isinstance(bess, dict):
            continue
        position = bess.get("cad_position") if isinstance(bess.get("cad_position"), dict) else {}
        insert = bess.get("cad_insert") if isinstance(bess.get("cad_insert"), dict) else {}
        bess_items.append(
            {
                "id": _safe_str(bess.get("id"), f"bess-{index}"),
                "x": _to_float(position.get("x")),
                "y": _to_float(position.get("y")),
                "rotation": _to_float(insert.get("rotation")),
                "scale": max(0.0001, _to_float(insert.get("xscale"), 1.0)),
            }
        )

    poi_raw = entities.get("poi") if isinstance(entities.get("poi"), dict) else None
    poi = None
    if isinstance(poi_raw, dict):
        poi = {
            "x": _to_float(poi_raw.get("x")),
            "y": _to_float(poi_raw.get("y")),
            "label": _safe_str(poi_raw.get("label"), "POI"),
        }

    cables: list[dict[str, Any]] = []
    raw_cables = entities.get("cable_paths") if isinstance(entities.get("cable_paths"), list) else []
    for index, cable in enumerate(raw_cables, start=1):
        if not isinstance(cable, dict):
            continue
        raw_points = cable.get("points") if isinstance(cable.get("points"), list) else []
        points = []
        for point in raw_points:
            if isinstance(point, list) and len(point) >= 2:
                points.append({"x": _to_float(point[0]), "y": _to_float(point[1])})
        if len(points) < 2:
            continue
        cables.append(
            {
                "id": _safe_str(cable.get("id"), f"cable-{index}"),
                "points": points,
            }
        )

    return {
        "schema_version": "site-design-spec-v1",
        "source_token": _safe_str(payload.get("source_token"), ""),
        "bess": bess_items,
        "poi": poi,
        "cables": cables,
    }


def _normalize_sld_design_spec(payload: dict[str, Any]) -> dict[str, Any]:
    sld_session = payload.get("sld_session") if isinstance(payload.get("sld_session"), dict) else {}

    symbols: list[dict[str, Any]] = []
    raw_nodes = sld_session.get("nodes") if isinstance(sld_session.get("nodes"), list) else []
    for index, node in enumerate(raw_nodes, start=1):
        if not isinstance(node, dict):
            continue
        symbols.append(
            {
                "id": _safe_str(node.get("id"), f"node-{index}"),
                "symbol_type": _safe_str(node.get("symbol_type"), "generic"),
                "x": _to_float(node.get("x")),
                "y": _to_float(node.get("y")),
                "rotation": _to_float(node.get("rotation_deg")),
                "metadata": {
                    "label": _safe_str(node.get("label"), ""),
                },
            }
        )

    connections: list[dict[str, Any]] = []
    raw_edges = sld_session.get("edges") if isinstance(sld_session.get("edges"), list) else []
    for index, edge in enumerate(raw_edges, start=1):
        if not isinstance(edge, dict):
            continue

        raw_points = edge.get("points") if isinstance(edge.get("points"), list) else []
        vertices = []
        for point in raw_points:
            if isinstance(point, list) and len(point) >= 2:
                vertices.append({"x": _to_float(point[0]), "y": _to_float(point[1])})

        if len(vertices) < 2:
            continue

        connections.append(
            {
                "id": _safe_str(edge.get("id"), f"edge-{index}"),
                "from_symbol_id": _safe_str(edge.get("from_node_id"), "unknown-from"),
                "to_symbol_id": _safe_str(edge.get("to_node_id"), "unknown-to"),
                "wire_type": _safe_str(edge.get("wire_type"), ""),
                "label": _safe_str(edge.get("label"), ""),
                "vertices": vertices,
            }
        )

    return {
        "schema_version": "sld-design-spec-v1",
        "symbols": symbols,
        "connections": connections,
    }


def normalize_planset_request(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_metadata": _normalize_project_metadata(payload),
        "site_design_spec": _normalize_site_design_spec(payload),
        "sld_design_spec": _normalize_sld_design_spec(payload),
    }


def validate_normalized_planset_request(normalized: dict[str, Any]) -> list[str]:
    checks = [
        ("project_metadata", _PROJECT_METADATA_VALIDATOR, normalized.get("project_metadata")),
        ("site_design_spec", _SITE_DESIGN_SPEC_VALIDATOR, normalized.get("site_design_spec")),
        ("sld_design_spec", _SLD_DESIGN_SPEC_VALIDATOR, normalized.get("sld_design_spec")),
    ]

    errors: list[str] = []
    for field_name, validator, field_payload in checks:
        for error in sorted(validator.iter_errors(field_payload), key=lambda item: list(item.path)):
            path = ".".join(str(part) for part in error.path) if error.path else field_name
            errors.append(f"{field_name}.{path}: {error.message}")

    return errors


def enrich_payload_with_normalized_inputs(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_planset_request(payload)
    validation_errors = validate_normalized_planset_request(normalized)
    if validation_errors:
        raise ValueError("; ".join(validation_errors))

    enriched = dict(payload)
    enriched["normalized_inputs"] = normalized
    return enriched
