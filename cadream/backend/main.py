from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from cad_parser import dxf_to_render_json, extract_blocks, load_dxf_from_bytes
from cad_export import export_dxf_from_cad_ir, export_dxf_from_source_bytes
from cad_ir_validation import validate_cad_ir_payload
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