import sys; sys.path.insert(0, ".")
from checker.dxf_loader import load_dxf_segments
from checker.geometry import find_double_lines, find_overlapping_segments, run_full_check

segs, meta = load_dxf_segments("test_comprehensive.dxf")
print(f"Segments: {len(segs)}")

dl = find_double_lines(segs, 0.1)
print(f"Double lines: {len(dl)}")

ov = find_overlapping_segments(segs, 0.1)
print(f"Overlaps: {len(ov)}")

for p in ov:
    print(f"  Overlap: i={p['i']} j={p['j']} ratio={p.get('overlap_ratio', '?')} loc=({p['location'][0]:.2f},{p['location'][1]:.2f})")

result = run_full_check(segs, 0.1)
print(f"\nTotal problems after merge: {result['total_problems']}")
for p in result["problems"]:
    print(f"  #{p['id']}: ({p['location'][0]:.2f},{p['location'][1]:.2f}) cluster={p.get('cluster_size', 1)}")
