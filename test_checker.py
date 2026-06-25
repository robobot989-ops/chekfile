import sys
sys.path.insert(0, ".")
from checker.dxf_loader import load_dxf_segments
from checker.geometry import run_full_check
from checker.report import generate_report

# Тест 1: загрузка
segs, meta = load_dxf_segments("test_clean.dxf")
print(f"Loaded segments: {len(segs)}")
for s in segs:
    print(f"  {s.entity_type:10s} layer={s.layer} len={s.geom.length:.2f}")

# Тест 2: поиск двойных линий
result = run_full_check(segs, tolerance=0.1)
print(f"\nProblems found: {result['total_problems']}")
for p in result["problems"]:
    print(f"  #{p['id']}: dist={p['distance']}mm loc=({p['location'][0]:.2f},{p['location'][1]:.2f})")

# Тест 3: генерация отчета
r = generate_report("test_clean.dxf", "reports", tolerance=0.1)
print(f"\nReport: {r['report_file']}")
print(f"Has errors: {r['has_errors']}")
print("DONE")
