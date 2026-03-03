from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path



def main() -> int:
    parser = argparse.ArgumentParser(description="Train ML boxes model from dataset artifacts.")
    parser.add_argument("--dataset_dir", default="../../dataset")
    parser.add_argument("--out", default="../../cadream/ml/model.pt")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch", type=int, default=16)
    args = parser.parse_args()

    script = Path(__file__).resolve().parents[2] / "ml" / "train.py"
    cmd = [
        sys.executable,
        str(script),
        "--dataset_dir",
        str(Path(args.dataset_dir).resolve()),
        "--out",
        str(Path(args.out).resolve()),
        "--epochs",
        str(args.epochs),
        "--batch",
        str(args.batch),
    ]

    result = subprocess.run(cmd, check=False)
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
