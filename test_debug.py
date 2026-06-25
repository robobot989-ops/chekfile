import sys; sys.path.insert(0, ".")
from checker.dxf_loader import load_dxf_segments
from checker.geometry import find_double_lines, _cluster_problems

segs, meta = load_dxf_segments("test_comprehensive.dxf")
problems = find_double_lines(segs, 0.1)
print(f"Raw problems: {len(problems)}")

# Show arc-related points (near center 500,500)
arc_pts = [(i, p["location"]) for i, p in enumerate(problems) if abs(p["location"][0] - 500) < 200 and abs(p["location"][1] - 500) < 200]
print(f"Arc points count: {len(arc_pts)}")
for idx, loc in arc_pts:
    print(f"  idx={idx}: ({loc[0]:.2f}, {loc[1]:.2f})")

# Test clustering
clustered = _cluster_problems(problems, 20.0)
print(f"\nClustered: {len(clustered)}")
for p in clustered:
    cs = p.get("cluster_size", 1)
    print(f"  #{p['id']}: ({p['location'][0]:.2f}, {p['location'][1]:.2f}) size={cs}")
