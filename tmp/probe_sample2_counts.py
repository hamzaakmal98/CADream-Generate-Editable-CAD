from pathlib import Path
import sys

sys.path.insert(0, r"c:\Users\hamza\CADream-Generate-Editable-CAD\cadream\backend")

from cad_parser import load_dxf_from_bytes
from page_generation_pipeline import generate_page_files_from_source_bytes

sample = Path(r"c:\Users\hamza\CADream-Generate-Editable-CAD\sample-files\Input_Sample_2.dxf")
source_bytes = sample.read_bytes()

src = load_dxf_from_bytes(source_bytes)
print("SRC", src.dxfversion, sum(1 for _ in src.modelspace()))

files, specs = generate_page_files_from_source_bytes(
    source_bytes,
    view_spec_mode="manifest14",
    template_id="template-v1",
)

page = load_dxf_from_bytes(files["page_01.dxf"])
print("PG", page.dxfversion, sum(1 for _ in page.modelspace()))
print("PAGES", len(specs), specs[0].page_number, specs[-1].page_number)
