import sys; sys.path.insert(0, ".")
import math
from checker.dxf_loader import load_dxf_segments
from checker.geometry import find_double_lines, find_overlapping_segments
from checker.geometry import _cluster_problems

segs, meta = load_dxf_segments("test_comprehensive.dxf")
dl = find_double_lines(segs, 0.1)
ov = find_overlapping_segments(segs, 0.1)

all_problems = dl + ov

# Build adjacency manually and debug
n = len(all_problems)
adj = [[] for _ in range(n)]

for i in range(n):
    ix, iy = all_problems[i]["location"]
    for j in range(i + 1, n):
        jx, jy = all_problems[j]["location"]
        d = math.hypot(ix - jx, iy - jy)
        if d < 20.0:
            adj[i].append(j)
            adj[j].append(i)

# Check component sizes
visited = [False] * n
components = []
for i in range(n):
    if visited[i]:
        continue
    stack = [i]
    visited[i] = True
    comp = []
    while stack:
        v = stack.pop()
        comp.append(v)
        for u in adj[v]:
            if not visited[u]:
                visited[u] = True
                stack.append(u)
    components.append(comp)

print(f"Total problems: {n}")
print(f"Number of components: {len(components)}")
for ci, comp in enumerate(components):
    locs = [all_problems[v]["location"] for v in comp]
    print(f"  Component {ci}: {len(comp)} problems")
    # Show range
    xs = [l[0] for l in locs]
    ys = [l[1] for l in locs]
    print(f"    x: {min(xs):.2f} - {max(xs):.2f}")
    print(f"    y: {min(ys):.2f} - {max(ys):.2f}")

# Now run the real cluster
clustered = _cluster_problems(all_problems, 20.0)
print(f"\nClustered: {len(clustered)}")
for p in clustered:
    print(f"  #{p['id']}: ({p['location'][0]:.2f},{p['location'][1]:.2f}) size={p.get('cluster_size', 1)}")
