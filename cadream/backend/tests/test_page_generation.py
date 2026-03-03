from __future__ import annotations

from io import BytesIO
import tempfile
import unittest
from pathlib import Path
import os

import ezdxf
from ezdxf import recover
from cad_parser import load_dxf_from_bytes
from page_builder_preserve_source import (
    SHEET_BORDER_LAYER,
    SHEET_CALLOUTS_LAYER,
    SHEET_OVERLAYS_LAYER,
    SHEET_TEXT_LAYER,
    SHEET_TITLEBLOCK_LAYER,
    SHEET_VIEWPORT_FRAME_LAYER,
)
from page_generation_pipeline import generate_page_files_from_source_bytes
from planset_manifest import AUTO_GENERATED_PAGES


REQUIRED_SHEET_LAYERS = {
    SHEET_BORDER_LAYER,
    SHEET_TITLEBLOCK_LAYER,
    SHEET_TEXT_LAYER,
    SHEET_CALLOUTS_LAYER,
    SHEET_VIEWPORT_FRAME_LAYER,
    SHEET_OVERLAYS_LAYER,
}


class PageGenerationInvariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[3]
        cls.sample_dir = cls.repo_root / "sample-files"
        cls.sample_paths = sorted(cls.sample_dir.glob("Input_Sample_*.dxf"))
        if not cls.sample_paths:
            raise AssertionError(f"No sample DXFs found under {cls.sample_dir}")

    def test_manifest14_generation_invariants_for_samples(self) -> None:
        for sample_path in self.sample_paths:
            with self.subTest(sample=sample_path.name):
                self._assert_sample_invariants(sample_path)

    def _assert_sample_invariants(self, sample_path: Path) -> None:
        source_bytes = sample_path.read_bytes()
        source_doc = load_dxf_from_bytes(source_bytes)
        source_modelspace = source_doc.modelspace()
        source_entity_count = sum(1 for _ in source_modelspace)
        source_insert_count = sum(1 for entity in source_modelspace if entity.dxftype() == "INSERT")

        files, specs = generate_page_files_from_source_bytes(
            source_bytes,
            view_spec_mode="manifest14",
            template_id="template-v1",
        )

        self.assertEqual(len(specs), len(AUTO_GENERATED_PAGES), "manifest14 must generate 14 page specs")
        self.assertEqual(
            [spec.page_number for spec in specs],
            AUTO_GENERATED_PAGES,
            "manifest14 page IDs must match canonical auto page IDs",
        )

        expected_names = {f"page_{page_number:02d}.dxf" for page_number in AUTO_GENERATED_PAGES}
        self.assertEqual(set(files.keys()), expected_names, "Generated DXF file set mismatch")

        for spec in specs:
            page_name = f"page_{spec.page_number:02d}.dxf"
            page_doc = self._open_dxf_from_bytes(files[page_name])
            page_modelspace = page_doc.modelspace()

            page_entity_count = sum(1 for _ in page_modelspace)
            page_insert_count = sum(1 for entity in page_modelspace if entity.dxftype() == "INSERT")

            min_entity_count = max(0, source_entity_count - max(20, int(source_entity_count * 0.08)))
            min_insert_count = max(0, source_insert_count - max(5, int(source_insert_count * 0.08)))

            self.assertGreaterEqual(
                page_entity_count,
                min_entity_count,
                f"{sample_path.name}:{page_name} modelspace entity count dropped beyond tolerance",
            )
            self.assertGreaterEqual(
                page_insert_count,
                min_insert_count,
                f"{sample_path.name}:{page_name} INSERT count dropped beyond tolerance",
            )

            for layer_name in REQUIRED_SHEET_LAYERS:
                self.assertIn(layer_name, page_doc.layers, f"{sample_path.name}:{page_name} missing sheet layer {layer_name}")

            if "Layout1" in page_doc.layouts:
                layout = page_doc.layouts.get("Layout1")
            else:
                layout_name = f"PAGE_{spec.page_number:02d}"
                layout = page_doc.layouts.get(layout_name)

            title_block_refs = [
                entity
                for entity in layout
                if entity.dxftype() == "INSERT" and entity.dxf.name == spec.template.title_block_block_name
            ]
            self.assertGreaterEqual(
                len(title_block_refs),
                1,
                f"{sample_path.name}:{page_name} missing title block INSERT {spec.template.title_block_block_name}",
            )

            viewport_rect = spec.viewport_rect
            x1, y1, x2, y2 = viewport_rect
            sheet_w, sheet_h = spec.sheet.width, spec.sheet.height

            self.assertGreaterEqual(x1, 0.0, f"{sample_path.name}:{page_name} viewport x1 outside sheet")
            self.assertGreaterEqual(y1, 0.0, f"{sample_path.name}:{page_name} viewport y1 outside sheet")
            self.assertLessEqual(x2, sheet_w, f"{sample_path.name}:{page_name} viewport x2 outside sheet")
            self.assertLessEqual(y2, sheet_h, f"{sample_path.name}:{page_name} viewport y2 outside sheet")

            viewports = [entity for entity in layout if entity.dxftype() == "VIEWPORT"]
            self.assertEqual(1, len(viewports), f"{sample_path.name}:{page_name} must have exactly one paperspace VIEWPORT")

            viewport = viewports[0]
            self.assertAlmostEqual(viewport.dxf.center.x, (x1 + x2) * 0.5, places=3)
            self.assertAlmostEqual(viewport.dxf.center.y, (y1 + y2) * 0.5, places=3)
            self.assertAlmostEqual(viewport.dxf.width, x2 - x1, places=3)
            self.assertAlmostEqual(viewport.dxf.height, y2 - y1, places=3)

            expected_view_center_x = (spec.view_bounds.min_x + spec.view_bounds.max_x) * 0.5
            expected_view_center_y = (spec.view_bounds.min_y + spec.view_bounds.max_y) * 0.5
            self.assertAlmostEqual(viewport.dxf.view_center_point.x, expected_view_center_x, places=3)
            self.assertAlmostEqual(viewport.dxf.view_center_point.y, expected_view_center_y, places=3)
            self.assertGreater(viewport.dxf.view_height, 0.0, f"{sample_path.name}:{page_name} view_height must be positive")

            frame_polylines = [
                entity
                for entity in layout
                if entity.dxftype() == "LWPOLYLINE" and entity.dxf.layer == SHEET_VIEWPORT_FRAME_LAYER
            ]
            self.assertTrue(
                any(self._polyline_matches_rect(entity, viewport_rect) for entity in frame_polylines),
                f"{sample_path.name}:{page_name} missing viewport frame polyline",
            )

    @staticmethod
    def _polyline_matches_rect(polyline, rect: tuple[float, float, float, float], tolerance: float = 1e-3) -> bool:
        x1, y1, x2, y2 = rect
        expected_points = {
            (round(x1, 3), round(y1, 3)),
            (round(x2, 3), round(y1, 3)),
            (round(x2, 3), round(y2, 3)),
            (round(x1, 3), round(y2, 3)),
        }

        points = list(polyline.get_points("xy"))
        if len(points) < 4:
            return False

        actual_points = {(round(float(x), 3), round(float(y), 3)) for x, y in points[:4]}
        if actual_points == expected_points:
            return True

        for expected in expected_points:
            if not any(abs(actual[0] - expected[0]) <= tolerance and abs(actual[1] - expected[1]) <= tolerance for actual in actual_points):
                return False
        return True

    @staticmethod
    def _open_dxf_from_bytes(data: bytes):
        byte_stream = BytesIO(data)
        try:
            return ezdxf.read(byte_stream)
        except Exception:
            pass

        handle_fd, handle_path = tempfile.mkstemp(suffix=".dxf")
        try:
            with os.fdopen(handle_fd, "wb") as handle:
                handle.write(data)

            try:
                return ezdxf.readfile(handle_path)
            except Exception:
                pass

            try:
                document, _auditor = recover.readfile(handle_path)
                return document
            except Exception:
                pass
        finally:
            try:
                os.remove(handle_path)
            except FileNotFoundError:
                pass

        raise ValueError("Could not read generated DXF bytes")


if __name__ == "__main__":
    unittest.main()
