from pathlib import Path
import traceback

import sys
sys.path.insert(0, r"c:\Users\hamza\CADream-Generate-Editable-CAD\cadream\backend")

from tests.test_page_generation import PageGenerationInvariantTests

sample = Path(r"c:\Users\hamza\CADream-Generate-Editable-CAD\sample-files\Input_Sample_2.dxf")
obj = PageGenerationInvariantTests(methodName="test_manifest14_generation_invariants_for_samples")
try:
    obj._assert_sample_invariants(sample)
    print("SAMPLE2_OK")
except Exception:
    traceback.print_exc()
    raise
