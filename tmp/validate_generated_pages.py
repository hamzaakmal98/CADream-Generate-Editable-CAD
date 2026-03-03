import json
import hashlib
import sys
from pathlib import Path
import ezdxf

root = Path(r"c:\Users\hamza\CADream-Generate-Editable-CAD")
if len(sys.argv) > 1:
    out_dir = Path(sys.argv[1])
else:
    out_dir = root / "tmp" / "generated_pages"

view_specs_path = out_dir / "view_specs.json"
if not view_specs_path.exists():
    raise FileNotFoundError(f"Missing {view_specs_path}")

view_specs = json.loads(view_specs_path.read_text(encoding="utf-8"))

spec_bounds = []
for s in view_specs:
    bounds = s["view_bounds"]
    min_pt = bounds["min"]
    max_pt = bounds["max"]
    spec_bounds.append(
        (
            int(s["page_number"]),
            str(s["page_name"]),
            round(float(min_pt[0]), 3),
            round(float(min_pt[1]), 3),
            round(float(max_pt[0]), 3),
            round(float(max_pt[1]), 3),
        )
    )

viewport_rows = []
file_hashes = []
missing_pages = []
assertion_failures = []
for page_num, page_name, *_ in spec_bounds:
    page_path = out_dir / f"page_{page_num:02d}.dxf"
    if not page_path.exists():
        missing_pages.append(page_path.name)
        continue

    file_hashes.append((page_path.name, hashlib.sha256(page_path.read_bytes()).hexdigest()[:16]))
    doc = ezdxf.readfile(str(page_path))
    layout = doc.layouts.get(f"PAGE_{page_num:02d}")
    vps = [entity for entity in layout if entity.dxftype() == "VIEWPORT"]

    if not vps:
        viewport_rows.append((page_num, page_name, None, None, None))
        assertion_failures.append(f"{page_path.name}: missing VIEWPORT in PAGE_{page_num:02d}")
        continue

    if len(vps) != 1:
        assertion_failures.append(f"{page_path.name}: expected 1 VIEWPORT, found {len(vps)}")

    vp = vps[0]
    center = (round(float(vp.dxf.center.x), 3), round(float(vp.dxf.center.y), 3))
    view_center = (
        round(float(vp.dxf.view_center_point.x), 3),
        round(float(vp.dxf.view_center_point.y), 3),
    )
    view_height = round(float(vp.dxf.view_height), 3)
    viewport_rows.append((page_num, page_name, center, view_center, view_height))

    spec = next(row for row in spec_bounds if row[0] == page_num)
    expected_view_center = (
        round((spec[2] + spec[4]) * 0.5, 3),
        round((spec[3] + spec[5]) * 0.5, 3),
    )
    if abs(view_center[0] - expected_view_center[0]) > 0.01 or abs(view_center[1] - expected_view_center[1]) > 0.01:
        assertion_failures.append(
            f"{page_path.name}: view_center {view_center} != expected {expected_view_center}"
        )
    if view_height <= 0:
        assertion_failures.append(f"{page_path.name}: non-positive view_height {view_height}")

unique_spec_bounds = len({row[2:] for row in spec_bounds})
unique_view_states = len({(row[3], row[4]) for row in viewport_rows if row[3] is not None})
unique_hashes = len({h for _, h in file_hashes})

print(f"SPEC_COUNT={len(spec_bounds)}")
print(f"UNIQUE_SPEC_BOUNDS={unique_spec_bounds}")
print(f"UNIQUE_VIEWPORT_VIEWCENTER_HEIGHT={unique_view_states}")
print(f"UNIQUE_DXF_HASHES={unique_hashes}")
print(f"MISSING_PAGES={missing_pages}")
print(f"ASSERTION_FAILURES={len(assertion_failures)}")

print("SPEC_BOUNDS_START")
for row in spec_bounds:
    print(row)
print("SPEC_BOUNDS_END")

print("VIEWPORTS_START")
for row in viewport_rows:
    print(row)
print("VIEWPORTS_END")

print("HASHES_START")
for row in file_hashes:
    print(row)
print("HASHES_END")

if assertion_failures:
    print("ASSERTIONS_START")
    for failure in assertion_failures:
        print(failure)
    print("ASSERTIONS_END")
    raise SystemExit(1)
