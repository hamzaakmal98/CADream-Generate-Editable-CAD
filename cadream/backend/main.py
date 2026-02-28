from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from cad_parser import dxf_to_render_json, extract_blocks, load_dxf_from_bytes

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
        doc = load_dxf_from_bytes(data)
        payload = dxf_to_render_json(doc, max_entities=50000)
        payload["blocks"] = extract_blocks(doc)
        payload["debug"] = {
            "layers": len(payload["layers"]),
            "entities": len(payload["entities"]),
            "blocks": len(payload["blocks"]),
        }
        return payload
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"DXF parse failed: {repr(e)}")