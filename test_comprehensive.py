"""Comprehensive test of the DXF checker algorithm."""
import sys
sys.path.insert(0, ".")

from checker.dxf_loader import load_dxf_segments
from checker.geometry import run_full_check
from checker.report import generate_report
import ezdxf
import math

# Create test DXF
doc = ezdxf.new()
msp = doc.modelspace()

# Scenario 1: Two lines very close (0.05mm) - should be detected
msp.add_line((0, 0), (100, 0))
msp.add_line((0, 0.05), (100, 0.05))

# Scenario 2: Two lines far apart (1mm) - should NOT be detected
msp.add_line((0, 100), (100, 100))
msp.add_line((0, 101), (100, 101))

# Scenario 3: Overlapping lines (same position) - should be detected
msp.add_line((200, 0), (300, 0))
msp.add_line((200, 0), (300, 0))

# Scenario 4: Lines at angle, close
msp.add_line((0, 200), (100, 200))
msp.add_line((0.03, 200.03), (100.03, 200.03))

# Scenario 5: Shared endpoint - should NOT be detected
msp.add_line((400, 0), (400, 100))
msp.add_line((400, 100), (400, 200))

# Scenario 6: Two arcs almost overlapping
center = (500, 500)
for angle in range(0, 90, 10):
    rad = math.radians(angle)
    r = 100
    x1 = center[0] + r * math.cos(rad)
    y1 = center[1] + r * math.sin(rad)
    rad2 = math.radians(angle + 10)
    x2 = center[0] + r * math.cos(rad2)
    y2 = center[1] + r * math.sin(rad2)
    msp.add_line((x1, y1), (x2, y2))

# Slightly offset arc
for angle in range(0, 90, 10):
    rad = math.radians(angle)
    r = 100.05
    x1 = center[0] + r * math.cos(rad)
    y1 = center[1] + r * math.sin(rad)
    rad2 = math.radians(angle + 10)
    x2 = center[0] + r * math.cos(rad2)
    y2 = center[1] + r * math.sin(rad2)
    msp.add_line((x1, y1), (x2, y2))

test_file = "test_comprehensive.dxf"
doc.saveas(test_file)
print(f"Created {test_file}")

# Check
segs, meta = load_dxf_segments(test_file)
print(f"Total segments: {len(segs)}")

result = run_full_check(segs, tolerance=0.1)
print(f"Problems found: {result['total_problems']}")

for p in result["problems"]:
    print(f"  #{p['id']}: dist={p['distance']}mm at ({p['location'][0]:.2f},{p['location'][1]:.2f})")

# Generate report
r = generate_report(test_file, "reports", tolerance=0.1)
print(f"\nReport: {r['report_file']}")
print("DONE")
