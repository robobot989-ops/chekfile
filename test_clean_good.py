"""Test with a clean DXF (no double lines)."""
import ezdxf
import sys; sys.path.insert(0, ".")
from checker.dxf_loader import load_dxf_segments
from checker.geometry import run_full_check
from checker.report import generate_report

doc = ezdxf.new()
msp = doc.modelspace()
msp.add_line((0, 0), (100, 0))
msp.add_line((0, 100), (100, 100))
msp.add_line((0, 0), (0, 100))
msp.add_line((100, 0), (100, 100))
msp.add_circle((200, 200), 50)
doc.saveas("test_good.dxf")

segs, meta = load_dxf_segments("test_good.dxf")
result = run_full_check(segs, tolerance=0.1)
print(f"Segments: {len(segs)}, Problems: {result['total_problems']}")

r = generate_report("test_good.dxf", "reports", tolerance=0.1)
print(f"Has errors: {r['has_errors']}")
print(f"Report: {r['report_file']}")
print("DONE")
