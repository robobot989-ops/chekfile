import os
import time
import re
import glob
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .state import CheckState
from checker.report import generate_report
from config import (
    FILE_PATTERN,
    REPORTS_DIR,
    DATA_DIR,
    POLL_INTERVAL,
    USE_WATCHDOG,
    MAX_WORKERS,
    TOLERANCE,
    MIN_PROBLEM_DISTANCE,
    get_today_path,
)
from web.settings_manager import SettingsManager

SETTINGS_PATH = Path(DATA_DIR) / "settings.json"


def _normalize_path(p: str) -> str:
    return Path(p).as_posix()


class DxfHandler(FileSystemEventHandler):
    def __init__(self, check_callback: Callable):
        self.check_callback = check_callback
        self._debounce = {}

    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith(".dxf"):
            self._debounce_and_check(event.src_path)

    def on_modified(self, event):
        if not event.is_directory and event.src_path.lower().endswith(".dxf"):
            self._debounce_and_check(event.src_path)

    def _debounce_and_check(self, filepath: str, delay: float = 1.0):
        now = time.time()
        last = self._debounce.get(filepath, 0)
        if now - last < delay:
            return
        self._debounce[filepath] = now
        time.sleep(delay)
        self.check_callback(filepath)


class DxfWatcher:
    def __init__(self, state: CheckState):
        self.state = state
        self.observer: Optional[Observer] = None
        self._running = False
        self.settings = SettingsManager(str(SETTINGS_PATH))
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    def get_settings(self) -> dict:
        return self.settings.all()

    def check_file(self, filepath: str) -> dict:
        filepath = _normalize_path(filepath)
        fp = Path(filepath)

        if not fp.exists():
            return {"filepath": filepath, "status": "error", "error": "Файл не найден"}

        filesize = fp.stat().st_size
        mtime = fp.stat().st_mtime

        if not self.state.needs_check(filepath, filesize, mtime):
            return {"filepath": filepath, "status": "skipped"}

        if not re.match(r"^[A-Za-z]+_\d+\.dxf$", fp.name, re.IGNORECASE):
            return {"filepath": filepath, "status": "skipped", "reason": "Не соответствует паттерну"}

        print(f"[CHECK] {filepath}")
        try:
            flat = self.settings.to_flat()
            result = generate_report(filepath, str(REPORTS_DIR), settings=flat, lang="ru")

            details = None
            if result.get("problems"):
                details = [
                    {
                        "id": p.get("id"),
                        "distance": p.get("distance", 0),
                        "location": p.get("location", (0, 0)),
                        "layer": p.get("segment1", {}).layer if hasattr(p.get("segment1"), "layer") else "?",
                        "entity_type": p.get("segment1", {}).entity_type if hasattr(p.get("segment1"), "entity_type") else "?",
                        "problem_type": p.get("problem_type", "double_line"),
                    }
                    for p in result["problems"]
                ]

            self.state.mark_checked(
                filepath=filepath,
                filename=result["filename"],
                filesize=filesize,
                mtime=mtime,
                status="checked",
                has_errors=result["has_errors"],
                total_problems=result["total_problems"],
                report_path=result.get("report_file"),
                error_details={"problems": details} if details else None,
            )

            status = "error" if result["has_errors"] else "ok"
            if result["has_errors"]:
                print(f"  [!] {result['total_problems']} problem(s) -> {result['report_file']}")
            else:
                print(f"  [+] OK")

            return {
                "filepath": filepath,
                "status": status,
                "total_problems": result["total_problems"],
                "report_file": result.get("report_file"),
            }

        except Exception as e:
            print(f"  [X] Error: {e}")
            try:
                self.state.mark_checked(
                    filepath=filepath,
                    filename=fp.name,
                    filesize=filesize,
                    mtime=mtime,
                    status="error",
                    has_errors=True,
                    total_problems=0,
                    error_details={"error": str(e)},
                )
            except Exception:
                pass
            return {"filepath": filepath, "status": "crash", "error": str(e)}

    def scan_directory(self, directory: str | Path):
        directory = Path(directory)
        if not directory.exists():
            print(f"[SCAN] Директория не найдена: {directory}")
            return

        pattern = str(directory / "*.dxf")
        files = sorted(glob.glob(pattern))
        futures = []

        for filepath in files:
            if re.match(r"^[A-Za-z]+_\d+\.dxf$", Path(filepath).name, re.IGNORECASE):
                future = self.executor.submit(self.check_file, filepath)
                futures.append(future)

        for future in as_completed(futures):
            pass

    def start_watchdog(self, directory: str | Path):
        if not USE_WATCHDOG:
            return
        directory = Path(directory)
        if not directory.exists():
            print(f"[WATCHDOG] Директория не найдена: {directory}")
            return
        event_handler = DxfHandler(self.check_file)
        self.observer = Observer()
        self.observer.schedule(event_handler, str(directory), recursive=False)
        self.observer.start()
        print(f"[WATCHDOG] Мониторинг: {directory}")

    def start_polling(self, directory: str | Path):
        directory = Path(directory)
        if not directory.exists():
            print(f"[POLL] Директория не найдена: {directory}")
            return
        while self._running:
            self.scan_directory(directory)
            time.sleep(POLL_INTERVAL)

    def run(self, directory: Optional[str | Path] = None):
        if directory is None:
            directory = get_today_path()
        directory = Path(directory)
        print(f"=== DXF Checker ===")
        print(f"Директория: {directory}")
        print(f"Допуск: {TOLERANCE} мм")
        print(f"Отчёты: {REPORTS_DIR}")
        print()

        print("[INIT] Первичное сканирование...")
        self.scan_directory(directory)
        print()

        self._running = True

        if USE_WATCHDOG:
            self.start_watchdog(directory)

        try:
            self.start_polling(directory)
        except KeyboardInterrupt:
            print("\n[STOP] Остановка...")
        finally:
            self._running = False
            if self.observer:
                self.observer.stop()
                self.observer.join()
            self.executor.shutdown(wait=True)
            self.state.close()

    def stop(self):
        self._running = False
        if self.observer:
            self.observer.stop()
