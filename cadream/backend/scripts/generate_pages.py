from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from page_generation_pipeline import write_page_generation_outputs


def _load_json_if_present(path: str | None) -> Any:
    if not path:
        return None
    source = Path(path)
    return json.loads(source.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate one DXF page per view spec from a source DXF.")
    parser.add_argument("--input", required=True, help="Path to input source DXF")
    parser.add_argument("--out", required=True, help="Output directory for generated page DXFs")
    parser.add_argument(
        "--mode",
        choices=["manifest14", "heuristic", "provided"],
        default="manifest14",
        help="View spec mode",
    )
    parser.add_argument("--provided-view-specs", default=None, help="Path to JSON file containing page view specs")
    parser.add_argument("--template", default="template-v1", help="Template identifier")

    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.out)

    if not input_path.exists():
        raise FileNotFoundError(f"Input DXF not found: {input_path}")

    provided_specs = _load_json_if_present(args.provided_view_specs)
    if args.mode == "provided" and provided_specs is None:
        raise ValueError("--provided-view-specs is required when --mode provided")

    specs = write_page_generation_outputs(
        input_path,
        output_dir,
        view_spec_mode=args.mode,
        provided_view_specs=provided_specs,
        template_id=args.template,
    )

    print(f"Generated {len(specs)} pages in {output_dir}")
    print(f"View specs: {output_dir / 'view_specs.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
