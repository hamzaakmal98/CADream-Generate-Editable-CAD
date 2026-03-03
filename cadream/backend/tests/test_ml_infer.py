from __future__ import annotations

import unittest
from pathlib import Path

from ml.infer import infer_view_specs_from_dxf_bytes


class MlInferRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[3]
        cls.sample_dir = cls.repo_root / "sample-files"
        cls.samples = [
            cls.sample_dir / "Input_Sample_0.dxf",
            cls.sample_dir / "Input_Sample_1.dxf",
        ]
        missing = [path.name for path in cls.samples if not path.exists()]
        if missing:
            raise AssertionError(f"Missing required sample files: {missing}")

    def test_infer_fallback_and_bounds_are_valid_for_sample_0_and_1(self) -> None:
        for sample_path in self.samples:
            with self.subTest(sample=sample_path.name):
                specs, report = infer_view_specs_from_dxf_bytes(
                    sample_path.read_bytes(),
                    model_path="nonexistent_model.pt",
                    viewport_aspect=1.6,
                )

                self.assertEqual([spec.page_number for spec in specs], [1, 2])
                self.assertEqual(len(specs), 2)

                for spec in specs:
                    self.assertLess(spec.view_bounds.min_x, spec.view_bounds.max_x)
                    self.assertLess(spec.view_bounds.min_y, spec.view_bounds.max_y)

                self.assertIn("fallback", report.get("selection_debug", {}))
                teacher_debug = report.get("teacher_debug", {})
                self.assertIn("site_plan", teacher_debug)
                self.assertIn("equipment_layout", teacher_debug)


if __name__ == "__main__":
    unittest.main()
