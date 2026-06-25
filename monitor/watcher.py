import os
import time
import re
import glob
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent

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
    get_today_path,
)


def _normalize_path(p: str) -> str:
    """Приводит путь к единому формату."""
    return Path(p).as_posix()


class DxfHandler(FileSystemEventHandler):
    """Watchdog-обработчик для новых/изменённых DXF файлов."""

    def __init__(self, check_callback: Callable):
        self.check_callback = check_callback
        self._debounce = {}  # filepath -> last_event_time

    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith(".dxf"):
            self._debounce_and_check(event.src_path)

    def on_modified(self, event):
        if not event.is_directory and event.src_path.lower().endswith(".dxf"):
            self._debounce_and_check(event.src_path)

    def _debounce_and_check(self, filepath: str, delay: float = 1.0):
        """Дебаунс: ждём delay секунд после последнего события."""
        now = time.time()
        last = self._debounce.get(filepath, 0)
        if now - last < delay:
            return
        self._debounce[filepath] = now
        time.sleep(delay)
        self.check_callback(filepath)


class DxfWatcher:
    """Мониторинг папки с DXF файлами — watchdog + периодический polling."""

    def __init__(self, state: CheckState):
        self.state = state
        self.observer: Optional[Observer] = None
        self._running = False
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    def check_file(self, filepath: str) -> dict:
        """Проверяет один DXF файл и возвращает результат."""
        filepath = _normalize_path(filepath)
        fp = Path(filepath)

        if not fp.exists():
            return {"filepath": filepath, "status": "error", "error": "Файл не найден"}

        filesize = fp.stat().st_size
        mtime = fp.stat().st_mtime

        # Пропускаем если уже проверяли и файл не менялся
        if not self.state.needs_check(filepath, filesize, mtime):
            return {"filepath": filepath, "status": "skipped"}

        # Паттерн имени
        if not re.match(r"^[A-Za-z]+_\d+\.dxf$", fp.name, re.IGNORECASE):
            return {"filepath": filepath, "status": "skipped", "reason": "Не соответствует паттерну"}

        print(f"[CHECK] {filepath}")
        try:
            result = generate_report(filepath, str(REPORTS_DIR), tolerance=TOLERANCE)

            self.state.mark_checked(
                filepath=filepath,
                filename=result["filename"],
                filesize=filesize,
                mtime=mtime,
                status="checked",
                has_errors=result["has_errors"],
                total_problems=result["total_problems"],
                report_path=result.get("report_file"),
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
        """Сканирует директорию и проверяет все новые DXF файлы."""
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
            pass  # результаты уже сохранены в check_file

    def start_watchdog(self, directory: str | Path):
        """Запускает watchdog для отслеживания изменений в реальном времени."""
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
        """Периодический polling для файлов, которые могли появиться между проверками."""
        directory = Path(directory)
        if not directory.exists():
            print(f"[POLL] Директория не найдена: {directory}")
            return

        while self._running:
            self.scan_directory(directory)
            time.sleep(POLL_INTERVAL)

    def run(self, directory: Optional[str | Path] = None):
        """Запускает полный мониторинг: сканирование + watchdog + polling."""
        if directory is None:
            directory = get_today_path()

        directory = Path(directory)
        print(f"=== DXF Checker ===")
        print(f"Директория: {directory}")
        print(f"Допуск: {TOLERANCE} мм")
        print(f"Отчёты: {REPORTS_DIR}")
        print()

        # Первичное сканирование
        print("[INIT] Первичное сканирование...")
        self.scan_directory(directory)
        print()

        self._running = True

        # Watchdog
        if USE_WATCHDOG:
            self.start_watchdog(directory)

        # Polling (в том же потоке)
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
