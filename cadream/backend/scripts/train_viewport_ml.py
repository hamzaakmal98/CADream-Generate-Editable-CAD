from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from planset_viewport_ml_train import train_viewport_ml_v1


def main() -> int:
    parser = argparse.ArgumentParser(description="Train viewport ML v1 config from sample DXF corpus.")
    parser.add_argument(
        "--samples",
        default="../../sample-files",
        help="Directory containing Input_Sample_*.dxf files",
    )
    parser.add_argument(
        "--out-config",
        default="config/viewport_ml_v1.json",
        help="Output config JSON path",
    )
    parser.add_argument(
        "--out-metrics",
        default="../../tmp/viewport_ml_v1_metrics.json",
        help="Output metrics JSON path",
    )

    args = parser.parse_args()

    samples_dir = Path(args.samples).resolve()
    out_config = Path(args.out_config).resolve()
    out_metrics = Path(args.out_metrics).resolve()

    config, metrics = train_viewport_ml_v1(samples_dir)

    out_config.parent.mkdir(parents=True, exist_ok=True)
    out_metrics.parent.mkdir(parents=True, exist_ok=True)

    out_config.write_text(json.dumps(config, indent=2), encoding="utf-8")
    out_metrics.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    print(f"Wrote viewport config: {out_config}")
    print(f"Wrote training metrics: {out_metrics}")
    print(f"Selected quantile q_low: {metrics['selected']['quantile_q_low']}")
    print(f"Selected densest grid: {metrics['selected']['densest_grid']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
