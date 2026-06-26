import json
from pathlib import Path
from typing import Any

DEFAULT_SETTINGS = {
    "checker": {
        "tolerance": 0.1,
        "min_problem_distance": 0.001,
        "double_line_layers": [],
        "double_line_check": True,
        "bridge_check": True,
        "bridge_min": 1.0,
        "bridge_max": 6.0,
        "bridge_exclude_colors": ["#00ffff"],
        "bridge_max_hole_diameter": 10.0,
    },
    "monitor": {
        "poll_interval": 30,
        "watchdog": True,
        "max_workers": 4,
        "base_path": "Z:/LASERTECHNO",
    },
    "email": {
        "enabled": True,
        "smtp_host": "192.168.1.100",
        "smtp_port": 25,
        "from_addr": "ab@lasertechno.ru",
        "to_addr": "shtamp_error@lasertechno.ru",
        "smtp_password": "",
        "use_tls": False,
    },
    "ui": {
        "language": "ru",
        "theme": "dark",
    },
    "web": {
        "port": 8080,
        "host": "0.0.0.0",
    },
}


class SettingsManager:
    def __init__(self, filepath: str | Path):
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self) -> dict:
        if self.filepath.exists():
            try:
                return json.loads(self.filepath.read_text("utf-8"))
            except Exception:
                pass
        return dict(DEFAULT_SETTINGS)

    def _save(self):
        self.filepath.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), "utf-8")

    def get(self, *keys: str, default: Any = None) -> Any:
        val = self._data
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
                if val is None:
                    return default
            else:
                return default
        return val

    def set(self, *args) -> None:
        if len(args) < 3:
            return
        *keys, value = args
        val = self._data
        for k in keys[:-1]:
            if k not in val or not isinstance(val[k], dict):
                val[k] = {}
            val = val[k]
        val[keys[-1]] = value
        self._save()

    def update_from_dict(self, d: dict, prefix: str = "") -> None:
        for k, v in d.items():
            key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                self.update_from_dict(v, key)
            else:
                parts = key.split(".")
                if len(parts) == 1:
                    self._data[k] = v
                else:
                    val = self._data
                    for p in parts[:-1]:
                        if p not in val or not isinstance(val[p], dict):
                            val[p] = {}
                        val = val[p]
                    val[parts[-1]] = v
        self._save()

    def all(self) -> dict:
        return dict(self._data)

    def to_flat(self) -> dict:
        """Flatten nested dict with dot notation."""
        result = {}
        def _flatten(d, prefix=""):
            for k, v in d.items():
                key = f"{prefix}.{k}" if prefix else k
                if isinstance(v, dict):
                    _flatten(v, key)
                else:
                    result[key] = v
        _flatten(self._data)
        return result
