from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from typing import Any, Awaitable, Callable
from cad_parser import dxf_to_render_json, extract_blocks, load_dxf_from_bytes
from cad_export import export_dxf_from_cad_ir, export_dxf_from_source_bytes
from cad_ir_validation import validate_cad_ir_payload
from planset_manifest import build_plan_set_manifest
from planset_pdf_export import generate_planset_fixed_pages_pdf, generate_planset_pages_pdf
from planset_payload_stubs import build_plan_set_payload_stubs
from planset_request_envelope import enrich_payload_with_normalized_inputs
from planset_right_panel_validation import validate_right_panel_payload
from planset_site_page_profiles import get_site_page_profile, get_site_page_profiles
from planset_sld_pages import export_sld_vertical_slice_zip
from planset_auto_pages_dxf import export_auto_pages_dxf_zip
from planset_package import export_planset_package_zip
from planset_template_sample import generate_common_template_sample_dxf
from page_generation_pipeline import generate_page_zip_from_source_bytes
import json
import hashlib

SOURCE_DXF_CACHE: dict[str, bytes] = {}


def _download_response(content: bytes, *, media_type: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _resolve_metadata_payload(payload: dict) -> dict:
    metadata_payload = payload.get("right_panel_metadata")
    if metadata_payload is None:
        metadata_payload = payload
    if not isinstance(metadata_payload, dict):
        raise HTTPException(status_code=400, detail="right_panel_metadata must be an object")
    return metadata_payload


def _validate_right_panel_metadata_or_raise(payload: dict) -> None:
    validation_errors = validate_right_panel_payload(_resolve_metadata_payload(payload))
    if validation_errors:
        raise HTTPException(
            status_code=400,
            detail="Right panel metadata validation failed: " + "; ".join(validation_errors),
        )


def _raise_bad_request(error_prefix: str, error: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=f"{error_prefix}: {repr(error)}")


def _run_with_bad_request(error_prefix: str, operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except HTTPException:
        raise
    except Exception as error:
        raise _raise_bad_request(error_prefix, error)


async def _run_async_with_bad_request(error_prefix: str, operation: Callable[[], Awaitable[Any]]) -> Any:
    try:
        return await operation()
    except HTTPException:
        raise
    except Exception as error:
        raise _raise_bad_request(error_prefix, error)

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
    async def _operation() -> dict:
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

    return await _run_async_with_bad_request("DXF parse failed", _operation)


@app.post("/dxf/export")
async def export_dxf(payload: dict):
    def _operation() -> Response:
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

        return _download_response(dxf_bytes, media_type="application/dxf", filename=filename)

    return _run_with_bad_request("DXF export failed", _operation)


@app.post("/cad-ir/validate")
async def validate_cad_ir(payload: dict):
    def _operation() -> dict:
        cad_ir = payload.get("cad_ir")
        result = validate_cad_ir_payload(cad_ir)
        return result

    return _run_with_bad_request("CAD IR validation failed", _operation)


@app.post("/planset/preview")
async def preview_plan_set(payload: dict):
    def _operation() -> dict:
        normalized_payload = enrich_payload_with_normalized_inputs(payload)
        manifest = build_plan_set_manifest(normalized_payload)
        return manifest

    return _run_with_bad_request("Plan-set preview failed", _operation)


@app.post("/planset/payload-stubs")
async def preview_plan_set_payload_stubs(payload: dict):
    def _operation() -> dict:
        normalized_payload = enrich_payload_with_normalized_inputs(payload)
        result = build_plan_set_payload_stubs(normalized_payload)
        return result

    return _run_with_bad_request("Plan-set payload stub preview failed", _operation)


@app.post("/planset/pages-24-25/export")
async def export_planset_vertical_slice_pages_24_25(payload: dict):
    def _operation() -> Response:
        normalized_payload = enrich_payload_with_normalized_inputs(payload)
        zip_bytes = export_sld_vertical_slice_zip(normalized_payload)
        return _download_response(zip_bytes, media_type="application/zip", filename="planset-pages-24-25.zip")

    return _run_with_bad_request("Plan-set pages 24/25 export failed", _operation)


@app.post("/planset/auto-pages/export")
async def export_planset_auto_pages_dxf(payload: dict):
    def _operation() -> Response:
        normalized_payload = enrich_payload_with_normalized_inputs(payload)

        export_payload = dict(normalized_payload)
        source_token = export_payload.get("source_token")
        if not isinstance(source_token, str) or source_token not in SOURCE_DXF_CACHE:
            raise HTTPException(
                status_code=400,
                detail="Source DXF is not available in backend cache for preserve-mode auto page export. Please re-upload the DXF in this session, then export again.",
            )
        export_payload["__source_dxf_bytes"] = SOURCE_DXF_CACHE[source_token]

        zip_bytes = export_auto_pages_dxf_zip(export_payload)
        return _download_response(zip_bytes, media_type="application/zip", filename="planset-auto-pages.zip")

    return _run_with_bad_request("Plan-set auto pages DXF export failed", _operation)


@app.post("/planset/preserved-dxf/export")
async def export_planset_preserved_dxf(payload: dict):
    def _operation() -> Response:
        normalized_payload = enrich_payload_with_normalized_inputs(payload)

        source_token = normalized_payload.get("source_token")
        if not isinstance(source_token, str) or source_token not in SOURCE_DXF_CACHE:
            raise HTTPException(
                status_code=400,
                detail="Source DXF is not available in backend cache. Please re-upload the DXF in this session, then export again.",
            )

        site_placements = normalized_payload.get("site_placements")
        if not isinstance(site_placements, dict):
            raise HTTPException(status_code=400, detail="Missing site_placements in request body")

        source_name = normalized_payload.get("source_file_name")
        if not isinstance(source_name, str) or not source_name.strip():
            source_name = "planset-preserved"

        dxf_bytes = export_dxf_from_source_bytes(SOURCE_DXF_CACHE[source_token], site_placements)
        filename = f"{source_name.rsplit('.', 1)[0]}-preserved.dxf"
        return _download_response(dxf_bytes, media_type="application/dxf", filename=filename)

    return _run_with_bad_request("Plan-set preserved DXF export failed", _operation)


@app.post("/planset/export")
async def export_planset_package(payload: dict):
    def _operation() -> Response:
        normalized_payload = enrich_payload_with_normalized_inputs(payload)
        _validate_right_panel_metadata_or_raise(normalized_payload)

        package_payload = dict(normalized_payload)
        source_token = package_payload.get("source_token")
        if isinstance(source_token, str) and source_token in SOURCE_DXF_CACHE:
            package_payload["__source_dxf_bytes"] = SOURCE_DXF_CACHE[source_token]

        zip_bytes = export_planset_package_zip(package_payload)
        return _download_response(zip_bytes, media_type="application/zip", filename="planset-export.zip")

    return _run_with_bad_request("Plan-set full export failed", _operation)


@app.get("/planset/site-page-profiles")
async def get_planset_site_page_profiles(include_follow_on: bool = True):
    return get_site_page_profiles(include_follow_on=include_follow_on)


@app.get("/planset/site-page-profiles/{page_number}")
async def get_planset_site_page_profile(page_number: int):
    profile = get_site_page_profile(page_number)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"No locked site-page profile for page {page_number}")
    return {
        "schema_version": "site-page-profiles-v1",
        "profile": profile,
    }


@app.post("/planset/template-sample/export")
async def export_planset_template_sample(payload: dict):
    def _operation() -> Response:
        normalized_payload = enrich_payload_with_normalized_inputs(payload)
        _validate_right_panel_metadata_or_raise(normalized_payload)
        dxf_bytes = generate_common_template_sample_dxf(normalized_payload)
        return _download_response(dxf_bytes, media_type="application/dxf", filename="planset-template-sample.dxf")

    return _run_with_bad_request("Template sample export failed", _operation)


@app.post("/planset/pages/pdf-export")
async def export_planset_pages_pdf(payload: dict):
    def _operation() -> Response:
        normalized_payload = enrich_payload_with_normalized_inputs(payload)
        _validate_right_panel_metadata_or_raise(normalized_payload)
        pdf_bytes = generate_planset_pages_pdf(normalized_payload)
        return _download_response(pdf_bytes, media_type="application/pdf", filename="planset-pages.pdf")

    return _run_with_bad_request("Plan-set pages PDF export failed", _operation)


@app.post("/planset/pages/fixed/pdf-export")
async def export_planset_fixed_pages_pdf(payload: dict):
    def _operation() -> Response:
        normalized_payload = enrich_payload_with_normalized_inputs(payload)
        _validate_right_panel_metadata_or_raise(normalized_payload)
        pdf_bytes = generate_planset_fixed_pages_pdf(normalized_payload)
        return _download_response(pdf_bytes, media_type="application/pdf", filename="planset-fixed-pages.pdf")

    return _run_with_bad_request("Plan-set fixed pages PDF export failed", _operation)


@app.post("/planset/generate-from-dxf")
async def generate_pages_from_dxf(
    file: UploadFile = File(...),
    view_spec_mode: str = Form("manifest14"),
    provided_view_specs: str | None = Form(None),
    template_id: str | None = Form("template-v1"),
):
    async def _operation() -> Response:
        source_bytes = await file.read()

        provided_specs_payload = None
        if isinstance(provided_view_specs, str) and provided_view_specs.strip():
            provided_specs_payload = json.loads(provided_view_specs)

        zip_bytes = generate_page_zip_from_source_bytes(
            source_bytes,
            view_spec_mode=view_spec_mode,
            provided_view_specs=provided_specs_payload,
            template_id=template_id,
        )

        return _download_response(
            zip_bytes,
            media_type="application/zip",
            filename="generated-pages.zip",
        )

    return await _run_async_with_bad_request("Plan-set DXF page generation failed", _operation)
