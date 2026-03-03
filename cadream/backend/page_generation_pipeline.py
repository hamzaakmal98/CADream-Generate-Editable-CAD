from __future__ import annotations

import json
import logging
from dataclasses import replace
from io import BytesIO
from io import StringIO
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import ezdxf
from ezdxf.addons import Importer

from cad_parser import load_dxf_from_bytes
from page_builder_preserve_source import build_page_dxf_from_source_bytes
from page_view_spec import PageViewSpec, TemplateSpec, parse_page_view_specs
from view_spec_heuristics import HeuristicViewSpecConfig, make_view_specs_from_source
from planset_manifest import AUTO_GENERATED_PAGES
from planset_ml_view_specs import predict_view_specs
from planset_site_page_profiles import PAGE_TITLE_NAMING_SPECS


_LOGGER = logging.getLogger(__name__)



def _with_template_override(spec: PageViewSpec, template_id: str | None) -> PageViewSpec:
    if not isinstance(template_id, str) or not template_id.strip():
        return spec

    template_name = template_id.strip()
    inferred_block_name = f"CADREAM_TITLEBLOCK_{template_name.upper().replace('-', '_')}"
    return replace(
        spec,
        template=TemplateSpec(id=template_name, title_block_block_name=inferred_block_name),
    )


def _serialize_doc(doc: ezdxf.document.Drawing) -> bytes:
    doc.audit()
    stream = StringIO()
    doc.write(stream)
    encoding = getattr(doc, "output_encoding", None) or "cp1252"
    return stream.getvalue().encode(encoding, errors="replace")


def _normalize_source_dxf_bytes(source_bytes: bytes) -> bytes:
    source_doc = load_dxf_from_bytes(source_bytes)
    normalized_doc = ezdxf.new("R2013")
    importer = Importer(source_doc, normalized_doc)

    block_names = [
        block.name
        for block in source_doc.blocks
        if not block.name.startswith("*") and block.name not in {"*Model_Space", "*Paper_Space"}
    ]
    if block_names:
        importer.import_blocks(block_names)

    importer.import_modelspace()
    importer.finalize()
    return _serialize_doc(normalized_doc)


def _normalize_specs(
    source_bytes: bytes,
    *,
    view_spec_mode: str,
    provided_view_specs: Any = None,
    template_id: str | None = None,
) -> list[PageViewSpec]:
    mode = (view_spec_mode or "manifest14").strip().lower()

    if mode == "manifest14":
        doc = load_dxf_from_bytes(source_bytes)
        baseline_specs = make_view_specs_from_source(
            doc,
            config=HeuristicViewSpecConfig(
                include_overall_page=True,
                start_page_number=1,
                grid_rows=5,
                grid_cols=5,
                max_grid_pages=13,
                use_density_ranking=True,
            ),
        )
        if len(baseline_specs) < len(AUTO_GENERATED_PAGES):
            raise ValueError("manifest14 mode could not generate enough baseline specs")

        specs: list[PageViewSpec] = []
        for index, page_number in enumerate(AUTO_GENERATED_PAGES):
            base = baseline_specs[index]
            page_title = PAGE_TITLE_NAMING_SPECS.get(page_number, f"Auto Page {page_number}")
            specs.append(replace(base, page_number=page_number, page_name=page_title))

    elif mode == "ml":
        try:
            specs = predict_view_specs(source_bytes, None)
        except Exception as error:
            _LOGGER.warning("ML view spec prediction failed; falling back to heuristic. error=%s", error)
            doc = load_dxf_from_bytes(source_bytes)
            specs = make_view_specs_from_source(doc, config=HeuristicViewSpecConfig())

    elif mode == "heuristic":
        doc = load_dxf_from_bytes(source_bytes)
        specs = make_view_specs_from_source(doc, config=HeuristicViewSpecConfig())
    elif mode == "provided":
        specs = parse_page_view_specs(provided_view_specs)
    else:
        raise ValueError("view_spec_mode must be 'manifest14', 'heuristic', 'ml', or 'provided'")

    return [_with_template_override(spec, template_id) for spec in specs]


def generate_page_files_from_source_bytes(
    source_bytes: bytes,
    *,
    view_spec_mode: str,
    provided_view_specs: Any = None,
    template_id: str | None = None,
    overlays: dict[str, Any] | None = None,
) -> tuple[dict[str, bytes], list[PageViewSpec]]:
    normalized_source_bytes = _normalize_source_dxf_bytes(source_bytes)

    specs = _normalize_specs(
        normalized_source_bytes,
        view_spec_mode=view_spec_mode,
        provided_view_specs=provided_view_specs,
        template_id=template_id,
    )

    files: dict[str, bytes] = {}
    for spec in specs:
        filename = f"page_{spec.page_number:02d}.dxf"
        files[filename] = build_page_dxf_from_source_bytes(normalized_source_bytes, spec, overlays=overlays)

    return files, specs


def generate_page_zip_from_source_bytes(
    source_bytes: bytes,
    *,
    view_spec_mode: str,
    provided_view_specs: Any = None,
    template_id: str | None = None,
    overlays: dict[str, Any] | None = None,
) -> bytes:
    files, specs = generate_page_files_from_source_bytes(
        source_bytes,
        view_spec_mode=view_spec_mode,
        provided_view_specs=provided_view_specs,
        template_id=template_id,
        overlays=overlays,
    )

    manifest = {
        "schema_version": "page-generation-package-v1",
        "view_spec_mode": view_spec_mode,
        "template_id": template_id,
        "pages": [spec.to_dict() for spec in specs],
        "files": sorted(files.keys()),
    }

    stream = BytesIO()
    with ZipFile(stream, mode="w", compression=ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            archive.writestr(name, content)
        archive.writestr("view_specs.json", json.dumps([spec.to_dict() for spec in specs], indent=2).encode("utf-8"))
        archive.writestr("manifest.json", json.dumps(manifest, indent=2).encode("utf-8"))

    return stream.getvalue()


def write_page_generation_outputs(
    source_dxf_path: Path,
    output_dir: Path,
    *,
    view_spec_mode: str,
    provided_view_specs: Any = None,
    template_id: str | None = None,
    overlays: dict[str, Any] | None = None,
) -> list[PageViewSpec]:
    output_dir.mkdir(parents=True, exist_ok=True)

    source_bytes = source_dxf_path.read_bytes()
    files, specs = generate_page_files_from_source_bytes(
        source_bytes,
        view_spec_mode=view_spec_mode,
        provided_view_specs=provided_view_specs,
        template_id=template_id,
        overlays=overlays,
    )

    for name, content in sorted(files.items()):
        (output_dir / name).write_bytes(content)

    (output_dir / "view_specs.json").write_text(
        json.dumps([spec.to_dict() for spec in specs], indent=2),
        encoding="utf-8",
    )

    manifest = {
        "schema_version": "page-generation-package-v1",
        "view_spec_mode": view_spec_mode,
        "template_id": template_id,
        "pages": [spec.to_dict() for spec in specs],
        "files": sorted(files.keys()),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    return specs
