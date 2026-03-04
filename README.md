# CADream — Generate Editable CAD PlanSets

## Demo Video

[![Watch the demo on YouTube](https://img.youtube.com/vi/zMv_rB19UcQ/maxresdefault.jpg)](https://youtu.be/zMv_rB19UcQ)

CADream is a DXF-first workflow for building editable BESS plan-set outputs.
It combines:
- a FastAPI backend for DXF parsing, validation, auto-page generation, SLD/page export, and packaging,
- a React + Vite frontend for interactive site placement and SLD editing,
- an ML-assisted viewport pipeline for auto-page crop inference.

## Repository Structure

- `cadream/backend` — FastAPI server + CAD/PlanSet/ML pipeline
- `cadream/frontend` — React app (interactive site plan + SLD editor)
- `cadream/ml` — model training/inference utilities for viewport box prediction
- `sample-files` — sample DXFs (`Input_Sample_*.dxf`)
- `dataset` — dataset assets and indexes for ML work
- `schemas` — JSON schemas used in validation

## Prerequisites

- Python `3.11+`
- Node.js `20+`
- npm `10+`

## Local Setup

### 1) Backend setup

```powershell
cd cadream/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install fastapi uvicorn[standard] python-multipart ezdxf numpy pillow reportlab pypdf jsonschema torch
```

### 2) Frontend setup

```powershell
cd cadream/frontend
npm install
```

## Run Locally

### Start backend (terminal 1)

```powershell
cd cadream/backend
.\.venv\Scripts\Activate.ps1
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### Start frontend (terminal 2)

```powershell
cd cadream/frontend
npm run dev
```

Open `http://localhost:5173`.

The Vite dev server proxies `/api/*` to the FastAPI backend at `http://127.0.0.1:8000`.

## Test

Backend smoke tests:

```powershell
cd cadream/backend
.\.venv\Scripts\Activate.ps1
python -m unittest tests.test_page_generation tests.test_ml_infer
```

## Design Write-up

### 1) How input CAD is parsed/rendered

- DXF ingest starts in `cadream/backend/main.py` at `/dxf/parse`.
- Raw bytes are loaded with resilient fallbacks in `cadream/backend/cad_parser.py` (`ezdxf.read`, file recovery, text decode recovery).
- Entities are converted into a normalized render payload (`LINE`, `LWPOLYLINE`, `CIRCLE`, `ARC`, `TEXT/MTEXT`, `INSERT`) and sanitized for finite coordinates, valid radii, and non-degenerate geometry.
- The response includes `layers`, `entities`, `bounds`, and extracted block contents; frontend renders this via CAD render adapters (`cadream/frontend/src/renderers/cad/*`).

### 2) How placement + cable routing data is represented

- Interactive site placement lives in `SitePlacementExport` / `SitePlanSessionState` in `cadream/frontend/src/types/cad.ts`.
- Core site payload shape:
  - `entities.bess[]` with CAD placement (`cad_position`) and insert transform (`cad_insert`: block name, rotation, scales)
  - `entities.poi` as a CAD-world anchor point
  - `entities.cable_paths[]` as polylines with endpoint metadata (`from_bess_id`, `to_poi`, etc.)
- Cable drafting/snap behavior is implemented in `cadream/frontend/src/hooks/useCableRouting.ts` (snap to nearest BESS, force terminal point to POI, edit cable start).

### 3) How the SLD editor stores symbols, connections, and metadata

- SLD session state (`schema_version: sld-v1`) stores:
  - `nodes[]` with `symbol_type`, position/rotation, terminal definitions, and per-node metadata
  - `edges[]` with from/to node+terminal IDs and polyline points
  - `tool_settings.viewport` and mode
- Symbol definitions (dimensions, CAD block mapping, layer, terminals) are centrally defined in `cadream/frontend/src/utils/sld/symbolRegistry.ts`.
- Editing logic in `cadream/frontend/src/hooks/useSldEditor.ts` handles deterministic IDs, grid normalization, directional connection validation, orthogonal routing, and undo/redo.

### 4) How automated pages vs fixed pages are generated

- Manifesting and readiness gates are built in `cadream/backend/planset_manifest.py` using the registry in `cadream/backend/config/planset_page_registry.json`.
- `static_template` pages are marked fixed.
- Auto pages are marked `auto`/`pending` based on available `cad_ir`, `site_placements`, and `sld_session`.
- Auto DXF pages are produced through `cadream/backend/planset_auto_pages_dxf.py` + emitters.
- Full page generation from source DXF is orchestrated in `cadream/backend/page_generation_pipeline.py` with modes:
  - `manifest14` (heuristic baseline aligned to canonical auto pages),
  - `heuristic`,
  - `ml` (ML-predicted view boxes + fallback),
  - `provided` (explicit specs).

### 5) How editable CAD is exported

- `/dxf/export` and `/planset/preserved-dxf/export` prefer preserve-mode when source DXF bytes are cached (`source_token`) in the backend session.
- Preserve-mode appends overlays (BESS, POI, cable paths) onto the original DXF modelspace via `export_dxf_from_source_bytes` in `cadream/backend/cad_export.py`.
- Fallback mode can emit from CAD IR (`export_dxf_from_cad_ir`), including layers, entities, and blocks.
- Result: exported DXF remains editable geometry (not rasterized output).

### 6) What to build next (ML-focused auto-page improvements)

If we had more time, the highest ROI upgrades would be:

1. **Per-page multi-head model instead of only page 1/2 boxes**  
	Extend the model from `SITE_PLAN`/`EQUIPMENT_LAYOUT` to all auto pages in `AUTO_GENERATED_PAGES`, with a shared backbone and per-page heads.

2. **Confidence-calibrated hybrid routing**  
	Keep the current heuristic+teacher fallback, but add explicit confidence calibration and uncertainty thresholds so low-confidence predictions automatically defer to heuristics page-by-page.

3. **Richer input channels and semantic masks**  
	Expand rasterized features beyond current 4-channel tensors (equipment, boundary/context, density maps) and include layer-presence embeddings from parser stats.

4. **Better training data generation and hard-negative mining**  
	Scale synthetic crops from `build_ml_dataset.py` with targeted hard cases (sparse boundaries, skewed title blocks, noisy layers) and active-learning loops from failed production samples.

5. **Geometry-aware loss + postprocessing constraints**  
	Add losses for boundary containment, aspect consistency, and minimum context coverage; enforce simple CAD constraints post-inference (non-zero area, in-bounds, overlap sanity).

6. **Online evaluation and regression dashboards**  
	Persist per-page IoU/coverage, fallback rate, and manifest pass rate to track drift and keep auto-page quality stable as new customer DXFs arrive.

## Notes

- Backend relies on in-memory source DXF caching (`source_token`) for preserve-mode exports in the current session.
- The repo includes both page generation and package export endpoints (`/planset/*`) for DXF, ZIP, and PDF outputs.
