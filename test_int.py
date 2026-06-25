import sys; sys.path.insert(0, ".")
from monitor.state import CheckState
from monitor.watcher import DxfWatcher
from config import DATA_DIR

state = CheckState(DATA_DIR / "test_int.db")
watcher = DxfWatcher(state)
result = watcher.check_file("test_comprehensive.dxf")
print(f"Result status: {result['status']}")
print(f"Problems: {result.get('total_problems', 0)}")
state.close()
