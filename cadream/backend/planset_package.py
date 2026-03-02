from __future__ import annotations

import json
from io import BytesIO
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from planset_auto_pages_dxf import generate_auto_pages_dxf_files
from planset_manifest import build_plan_set_manifest
from planset_pdf_export import generate_planset_fixed_pages_pdf, generate_planset_pages_pdf


def _page_numbers(pages: list[dict[str, Any]], *, generation_mode: str | None = None) -> list[int]:
    out: list[int] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        if generation_mode is not None and page.get("generation_mode") != generation_mode:
            continue
        page_number = page.get("page_number")
        if isinstance(page_number, int) and page_number > 0:
            out.append(page_number)
    return sorted(set(out))


def _build_export_manifest(
    *,
    manifest: dict[str, Any],
    auto_files: dict[str, bytes],
    include_pdf_artifacts: bool,
    pdf_artifact_errors: list[str],
) -> dict[str, Any]:
    pages = manifest.get("pages") if isinstance(manifest.get("pages"), list) else []
    auto_pages = _page_numbers(pages, generation_mode="auto")
    fixed_pages = _page_numbers(pages, generation_mode="fixed")

    exported_auto_pages: list[int] = []
    for file_name in sorted(auto_files.keys()):
        token = file_name.replace("planset-page-", "").replace(".dxf", "")
        if token.isdigit():
            exported_auto_pages.append(int(token))

    return {
        "schema_version": "planset-export-package-v1",
        "package": {
            "format": "zip",
            "dxf_first": True,
            "dwg_conversion": {
                "configured": False,
                "hook": None,
            },
        },
        "summary": {
            "total_pages": len(_page_numbers(pages)),
            "auto_pages_declared": len(auto_pages),
            "auto_pages_exported": len(exported_auto_pages),
            "fixed_pages_declared": len(fixed_pages),
        },
        "canonical_page_order": _page_numbers(pages),
        "auto_pages": {
            "declared": auto_pages,
            "exported": sorted(exported_auto_pages),
            "files": sorted(auto_files.keys()),
        },
        "fixed_pages": {
            "declared": fixed_pages,
            "artifacts": [
                "fixed-pages/planset-fixed-pages.pdf",
            ],
        },
        "full_planset": {
            "artifacts": ["full-planset/planset-pages.pdf"] if include_pdf_artifacts and len(pdf_artifact_errors) == 0 else [],
        },
        "fixed_pages_pdf": {
            "artifacts": ["fixed-pages/planset-fixed-pages.pdf"] if include_pdf_artifacts and len(pdf_artifact_errors) == 0 else [],
            "errors": pdf_artifact_errors,
        },
    }


def export_planset_package_zip(payload: dict[str, Any]) -> bytes:
    manifest = build_plan_set_manifest(payload)
    auto_files = generate_auto_pages_dxf_files(payload)
    include_pdf_artifacts = bool(payload.get("include_pdf_artifacts"))

    full_pdf_bytes: bytes | None = None
    fixed_pdf_bytes: bytes | None = None
    pdf_artifact_errors: list[str] = []
    if include_pdf_artifacts:
        try:
            full_pdf_bytes = generate_planset_pages_pdf(payload)
            fixed_pdf_bytes = generate_planset_fixed_pages_pdf(payload)
        except Exception as error:
            pdf_artifact_errors.append(str(error))

    export_manifest = _build_export_manifest(
        manifest=manifest,
        auto_files=auto_files,
        include_pdf_artifacts=include_pdf_artifacts,
        pdf_artifact_errors=pdf_artifact_errors,
    )
    export_manifest_bytes = json.dumps(export_manifest, indent=2, sort_keys=True).encode("utf-8")
    planset_manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")

    zip_stream = BytesIO()
    with ZipFile(zip_stream, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("manifests/planset-manifest.json", planset_manifest_bytes)
        archive.writestr("manifests/planset-export-manifest.json", export_manifest_bytes)

        for file_name, content in sorted(auto_files.items()):
            archive.writestr(f"auto-pages/{file_name}", content)

        if isinstance(fixed_pdf_bytes, (bytes, bytearray)):
            archive.writestr("fixed-pages/planset-fixed-pages.pdf", fixed_pdf_bytes)
        if isinstance(full_pdf_bytes, (bytes, bytearray)):
            archive.writestr("full-planset/planset-pages.pdf", full_pdf_bytes)

    return zip_stream.getvalue()
