from __future__ import annotations

from typing import Any


def validate_cad_ir_payload(cad_ir: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(cad_ir, dict):
        return {"valid": False, "errors": ["cad_ir must be an object"], "warnings": []}

    if cad_ir.get("schemaVersion") != "cad-ir-v1":
        errors.append("Unsupported cad_ir.schemaVersion (expected cad-ir-v1)")

    entities_by_id = cad_ir.get("entitiesById")
    if not isinstance(entities_by_id, dict):
        errors.append("cad_ir.entitiesById must be an object")
        entities_by_id = {}

    model_ids = cad_ir.get("modelSpaceEntityIds")
    if not isinstance(model_ids, list):
        errors.append("cad_ir.modelSpaceEntityIds must be an array")
    else:
        for entity_id in model_ids:
            if not isinstance(entity_id, str):
                errors.append("cad_ir.modelSpaceEntityIds must contain strings only")
                break
            if entity_id not in entities_by_id:
                errors.append(f"modelSpaceEntityId '{entity_id}' does not exist in entitiesById")

    blocks = cad_ir.get("blocksByName")
    if isinstance(blocks, dict):
        for block_name, block_def in blocks.items():
            if not isinstance(block_name, str) or not isinstance(block_def, dict):
                errors.append("cad_ir.blocksByName must map block-name strings to objects")
                continue
            ids = block_def.get("entityIds")
            if not isinstance(ids, list):
                errors.append(f"blocksByName['{block_name}'].entityIds must be an array")
                continue
            for entity_id in ids:
                if not isinstance(entity_id, str) or entity_id not in entities_by_id:
                    errors.append(f"blocksByName['{block_name}'] references unknown entity id '{entity_id}'")

    site_plan = cad_ir.get("sitePlan")
    if site_plan is None:
        warnings.append("cad_ir.sitePlan is missing (BESS/POI/cables not embedded in IR)")
    elif not isinstance(site_plan, dict):
        errors.append("cad_ir.sitePlan must be an object when provided")
    else:
        if site_plan.get("schemaVersion") != "cad-ir-site-v1":
            errors.append("cad_ir.sitePlan.schemaVersion must be cad-ir-site-v1")

        entities = site_plan.get("entities")
        if not isinstance(entities, dict):
            errors.append("cad_ir.sitePlan.entities must be an object")
        else:
            bess = entities.get("bess")
            poi = entities.get("poi")
            cable_paths = entities.get("cablePaths")

            bess_ids: set[int] = set()

            if not isinstance(bess, list):
                errors.append("cad_ir.sitePlan.entities.bess must be an array")
                bess = []

            for idx, b in enumerate(bess):
                if not isinstance(b, dict):
                    errors.append(f"bess[{idx}] must be an object")
                    continue
                placement_id = b.get("placementId")
                label = b.get("label")
                pos = b.get("position")
                ins = b.get("insert")

                if not isinstance(placement_id, int):
                    errors.append(f"bess[{idx}].placementId must be an integer")
                else:
                    if placement_id in bess_ids:
                        errors.append(f"Duplicate BESS placementId {placement_id}")
                    bess_ids.add(placement_id)

                if not isinstance(label, str) or not label.strip():
                    errors.append(f"bess[{idx}].label must be a non-empty string")

                if not isinstance(pos, dict) or not isinstance(pos.get("x"), (int, float)) or not isinstance(pos.get("y"), (int, float)):
                    errors.append(f"bess[{idx}].position must include numeric x/y")

                if not isinstance(ins, dict):
                    errors.append(f"bess[{idx}].insert must be an object")
                else:
                    for key in ["rotationDeg", "xScale", "yScale"]:
                        if not isinstance(ins.get(key), (int, float)):
                            errors.append(f"bess[{idx}].insert.{key} must be numeric")

            if poi is not None:
                if not isinstance(poi, dict) or not isinstance(poi.get("position"), dict):
                    errors.append("sitePlan.poi must be null or an object with position")
                else:
                    p = poi["position"]
                    if not isinstance(p.get("x"), (int, float)) or not isinstance(p.get("y"), (int, float)):
                        errors.append("sitePlan.poi.position must include numeric x/y")

            if not isinstance(cable_paths, list):
                errors.append("cad_ir.sitePlan.entities.cablePaths must be an array")
                cable_paths = []

            for idx, cable in enumerate(cable_paths):
                if not isinstance(cable, dict):
                    errors.append(f"cablePaths[{idx}] must be an object")
                    continue

                points = cable.get("points")
                topology = cable.get("topology")

                if not isinstance(cable.get("cableId"), int):
                    errors.append(f"cablePaths[{idx}].cableId must be an integer")

                if not isinstance(points, list) or len(points) < 2:
                    errors.append(f"cablePaths[{idx}].points must have at least 2 points")
                else:
                    for pt in points:
                        if not isinstance(pt, dict) or not isinstance(pt.get("x"), (int, float)) or not isinstance(pt.get("y"), (int, float)):
                            errors.append(f"cablePaths[{idx}] contains invalid point")
                            break

                if not isinstance(topology, dict):
                    errors.append(f"cablePaths[{idx}].topology must be an object")
                    continue

                from_id = topology.get("fromBessId")
                to_id = topology.get("toBessId")
                to_poi = topology.get("toPoi")

                if from_id is not None and from_id not in bess_ids:
                    errors.append(f"cablePaths[{idx}].topology.fromBessId references unknown BESS id {from_id}")
                if to_id is not None and to_id not in bess_ids:
                    errors.append(f"cablePaths[{idx}].topology.toBessId references unknown BESS id {to_id}")
                if not isinstance(to_poi, bool):
                    errors.append(f"cablePaths[{idx}].topology.toPoi must be boolean")

                if bool(to_poi) and poi is None:
                    errors.append(f"cablePaths[{idx}] targets POI but sitePlan.poi is null")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}
