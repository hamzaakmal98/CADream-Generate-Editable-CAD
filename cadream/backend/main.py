from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import ezdxf
from collections import Counter

from io import BytesIO
from ezdxf import recover

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


def polyline_xy_points(polyline_entity):
    pts = []

    try:
        for v in polyline_entity.vertices:
            loc = getattr(v.dxf, "location", None)
            if loc is not None:
                pts.append([loc.x, loc.y])
    except Exception:
        pass

    if pts:
        return pts

    try:
        pts = [[p[0], p[1]] for p in polyline_entity.points()]
    except Exception:
        pts = []

    return pts

def dxf_to_render_json(doc: ezdxf.document.Drawing, max_entities: int = 250000):
    msp = doc.modelspace()

    layers = []
    for layer in doc.layers:
        layers.append({
            "name": layer.dxf.name,
            "color": layer.color,
            "linetype": layer.dxf.linetype,
        })

    entities = []
    count = 0

    for e in msp:
        if count >= max_entities:
            break
        t = e.dxftype()

        try:
            layer = e.dxf.layer
        except Exception:
            layer = "0"

        if t == "LINE":
            entities.append({
                "type": "LINE",
                "layer": layer,
                "p1": [e.dxf.start.x, e.dxf.start.y],
                "p2": [e.dxf.end.x, e.dxf.end.y],
            })
            count += 1

        elif t in ("LWPOLYLINE",):
            pts = [[p[0], p[1]] for p in e.get_points("xy")]
            entities.append({
                "type": "LWPOLYLINE",
                "layer": layer,
                "points": pts,
                "closed": bool(e.closed),
            })
            count += 1

        elif t == "CIRCLE":
            entities.append({
                "type": "CIRCLE",
                "layer": layer,
                "center": [e.dxf.center.x, e.dxf.center.y],
                "r": float(e.dxf.radius),
            })
            count += 1

        elif t == "ARC":
            entities.append({
                "type": "ARC",
                "layer": layer,
                "center": [e.dxf.center.x, e.dxf.center.y],
                "r": float(e.dxf.radius),
                "start_angle": float(e.dxf.start_angle),
                "end_angle": float(e.dxf.end_angle),
            })
            count += 1

        elif t in ("TEXT", "MTEXT"):
            text = getattr(e.dxf, "text", None) or ""
            insert = getattr(e.dxf, "insert", None)
            if insert:
                pos = [insert.x, insert.y]
            else:
                pos = [0.0, 0.0]
            entities.append({
                "type": t,
                "layer": layer,
                "text": text,
                "pos": pos,
                "height": float(getattr(e.dxf, "height", 10.0) or 10.0),
            })
            count += 1

        elif t == "INSERT":
            insert = e.dxf.insert
            entities.append({
                "type": "INSERT",
                "layer": layer,
                "name": e.dxf.name,
                "pos": [insert.x, insert.y],
                "rotation": float(getattr(e.dxf, "rotation", 0.0) or 0.0),
                "xscale": float(getattr(e.dxf, "xscale", 1.0) or 1.0),
                "yscale": float(getattr(e.dxf, "yscale", 1.0) or 1.0),
            })
            count += 1
        
        elif t == "POLYLINE":
            try:
                pts = polyline_xy_points(e)
                if not pts:
                    continue

                entities.append({
                    "type": "LWPOLYLINE",
                    "layer": layer,
                    "points": pts,
                    "closed": bool(getattr(e, "is_closed", False)),
                })
                count += 1
            except Exception:
                pass

    IGNORE_LAYERS = {
        "Defpoints",
        "DEFPOINTS",
        "Drawing Frame",
        "DRAWING FRAME",
        "BORDER",
        "TITLEBLOCK",
        "Title Block",
    }

    PREFERRED_LAYERS = {
        "Base Map",
        "Unit Area Boundary",
        "Road",
        "Obstruction",
        "Ridge Line",
        "Switching Station",
        "Mounting Structure",
        "Module",
        "Inverter",
        "Transformer",
        "Combiner Box",
        "Cable Path",
        "AC Cable",
        "DC Cable",
        "Service Panel",
        "Shading",
        "0",
    }

    def compute_bounds(ents):
        xs, ys = [], []

        def add_point(x, y):
            xs.append(float(x))
            ys.append(float(y))

        for ent in ents:
            t = ent["type"]
            if t == "LINE":
                add_point(ent["p1"][0], ent["p1"][1])
                add_point(ent["p2"][0], ent["p2"][1])
            elif t == "LWPOLYLINE":
                for p in ent["points"]:
                    add_point(p[0], p[1])
            elif t in ("CIRCLE", "ARC"):
                cx, cy = ent["center"]
                r = ent["r"]
                add_point(cx - r, cy - r)
                add_point(cx + r, cy + r)
            elif t in ("TEXT", "MTEXT", "INSERT"):
                add_point(ent["pos"][0], ent["pos"][1])

        if xs and ys:
            return {"min": [min(xs), min(ys)], "max": [max(xs), max(ys)]}
        return None

    usable = [e for e in entities if e.get("layer", "0") not in IGNORE_LAYERS]

    preferred = [e for e in usable if e.get("layer", "0") in PREFERRED_LAYERS]
    bounds = compute_bounds(preferred)

    if bounds is None:
        bounds = compute_bounds(usable)
        
    type_counts = Counter([e["type"] for e in entities])
    print("ENTITY COUNTS:", type_counts)

    return {"layers": layers, "entities": entities, "bounds": bounds}


def extract_blocks(doc: ezdxf.document.Drawing, max_entities_per_block: int = 20000):
    blocks_out = {}

    for blk in doc.blocks:
        name = blk.name
        if name in ("*Model_Space", "*Paper_Space") or name.startswith("*Paper_Space"):
            continue

        ents = []
        count = 0

        for e in blk:
            if count >= max_entities_per_block:
                break

            t = e.dxftype()
            try:
                layer = e.dxf.layer
            except Exception:
                layer = "0"

            if t == "LINE":
                ents.append({"type": "LINE", "layer": layer, "p1": [e.dxf.start.x, e.dxf.start.y], "p2": [e.dxf.end.x, e.dxf.end.y]})
                count += 1

            elif t == "LWPOLYLINE":
                pts = [[p[0], p[1]] for p in e.get_points("xy")]
                ents.append({"type": "LWPOLYLINE", "layer": layer, "points": pts, "closed": bool(e.closed)})
                count += 1

            elif t == "POLYLINE":
                try:
                    pts = polyline_xy_points(e)
                    if not pts:
                        continue
                    ents.append({"type": "LWPOLYLINE", "layer": layer, "points": pts, "closed": bool(getattr(e, "is_closed", False))})
                    count += 1
                except Exception:
                    pass

            elif t == "CIRCLE":
                ents.append({"type": "CIRCLE", "layer": layer, "center": [e.dxf.center.x, e.dxf.center.y], "r": float(e.dxf.radius)})
                count += 1

            elif t == "ARC":
                ents.append({"type": "ARC", "layer": layer, "center": [e.dxf.center.x, e.dxf.center.y], "r": float(e.dxf.radius),
                             "start_angle": float(e.dxf.start_angle), "end_angle": float(e.dxf.end_angle)})
                count += 1

            elif t in ("TEXT", "MTEXT"):
                text = getattr(e.dxf, "text", None) or ""
                insert = getattr(e.dxf, "insert", None)
                pos = [insert.x, insert.y] if insert else [0.0, 0.0]
                ents.append({"type": t, "layer": layer, "text": text, "pos": pos, "height": float(getattr(e.dxf, "height", 10.0) or 10.0)})
                count += 1

            elif t == "INSERT":
                insert = e.dxf.insert
                ents.append({
                    "type": "INSERT",
                    "layer": layer,
                    "name": e.dxf.name,
                    "pos": [insert.x, insert.y],
                    "rotation": float(getattr(e.dxf, "rotation", 0.0) or 0.0),
                    "xscale": float(getattr(e.dxf, "xscale", 1.0) or 1.0),
                    "yscale": float(getattr(e.dxf, "yscale", 1.0) or 1.0),
                })
                count += 1

        if ents:
            blocks_out[name] = ents

    return blocks_out


def load_dxf_from_bytes(data: bytes):
    stream = BytesIO(data)
    try:
        return ezdxf.read(stream)
    except Exception:
        stream.seek(0)
        doc, auditor = recover.read(stream)
        return doc

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