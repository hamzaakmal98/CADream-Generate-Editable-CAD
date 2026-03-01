from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from cad_parser import dxf_to_render_json, extract_blocks, load_dxf_from_bytes
from cad_export import export_dxf_from_cad_ir, export_dxf_from_source_bytes
from cad_ir_validation import validate_cad_ir_payload
from planset_manifest import build_plan_set_manifest
from planset_payload_stubs import build_plan_set_payload_stubs
from planset_sld_pages import export_sld_vertical_slice_zip
import hashlib

SOURCE_DXF_CACHE: dict[str, bytes] = {}

app = FastAPI(title="CADream Backend")

@app.get("/debug/whoami")
def whoami():
    return {
        "file": __file__,
        "cors": "enabled",
    }

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/dxf/parse")
async def parse_dxf(file: UploadFile = File(...)):
    try:
        data = await file.read()
        source_token = hashlib.sha256(data).hexdigest()
        SOURCE_DXF_CACHE[source_token] = data
        doc = load_dxf_from_bytes(data)
        payload = dxf_to_render_json(doc, max_entities=50000)
        payload["blocks"] = extract_blocks(doc)
        payload["source_token"] = source_token
        payload["debug"] = {
            "layers": len(payload["layers"]),
            "entities": len(payload["entities"]),
            "blocks": len(payload["blocks"]),
        }
        return payload
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"DXF parse failed: {repr(e)}")


@app.post("/dxf/export")
async def export_dxf(payload: dict):
    try:
        source_name = payload.get("source_file_name")
        if not isinstance(source_name, str) or not source_name.strip():
            source_name = "cadream-export"

        source_token = payload.get("source_token")
        site_placements = payload.get("site_placements")

        dxf_bytes: bytes
        if isinstance(source_token, str) and source_token in SOURCE_DXF_CACHE and isinstance(site_placements, dict):
            dxf_bytes = export_dxf_from_source_bytes(SOURCE_DXF_CACHE[source_token], site_placements)
        else:
            if isinstance(site_placements, dict):
                raise HTTPException(
                    status_code=400,
                    detail="Source DXF is not available in backend cache. Please re-upload the DXF in this session, then export again.",
                )
            cad_ir = payload.get("cad_ir")
            if cad_ir is None:
                raise HTTPException(status_code=400, detail="Missing cad_ir in request body")
            dxf_bytes = export_dxf_from_cad_ir(cad_ir)

        filename = f"{source_name.rsplit('.', 1)[0]}.dxf"

        return Response(
            content=dxf_bytes,
            media_type="application/dxf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"DXF export failed: {repr(e)}")


@app.post("/cad-ir/validate")
async def validate_cad_ir(payload: dict):
    try:
        cad_ir = payload.get("cad_ir")
        result = validate_cad_ir_payload(cad_ir)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CAD IR validation failed: {repr(e)}")


@app.post("/planset/preview")
async def preview_plan_set(payload: dict):
    try:
        manifest = build_plan_set_manifest(payload)
        return manifest
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Plan-set preview failed: {repr(e)}")


@app.post("/planset/payload-stubs")
async def preview_plan_set_payload_stubs(payload: dict):
    try:
        result = build_plan_set_payload_stubs(payload)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Plan-set payload stub preview failed: {repr(e)}")


@app.post("/planset/pages-24-25/export")
async def export_planset_vertical_slice_pages_24_25(payload: dict):
    try:
        zip_bytes = export_sld_vertical_slice_zip(payload)
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=planset-pages-24-25.zip"},
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Plan-set pages 24/25 export failed: {repr(e)}")