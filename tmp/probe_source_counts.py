from pathlib import Path
import sys
sys.path.insert(0, r"c:\Users\hamza\CADream-Generate-Editable-CAD\cadream\backend")

from cad_parser import load_dxf_from_bytes

root = Path(r"c:\Users\hamza\CADream-Generate-Editable-CAD")
for p in sorted((root / "sample-files").glob("Input_Sample_*.dxf")):
    d = load_dxf_from_bytes(p.read_bytes())
    cnt = sum(1 for _ in d.modelspace())
    ins = sum(1 for e in d.modelspace() if e.dxftype() == "INSERT")
    print(p.name, d.dxfversion, cnt, ins)
