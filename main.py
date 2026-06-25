#!/usr/bin/env python3
"""
DXF Double Line Checker — сервис мониторинга DXF файлов на двойные линии.

Использование:
  python main.py                          # проверить сегодняшнюю папку
  python main.py --date 2026-06-24       # проверить папку за конкретную дату
  python main.py --path Z:/path/to/folder # проверить произвольную папку
  python main.py --once                   # однократная проверка без watchdog
  python main.py --web-only               # только веб-сервер (без мониторинга)
"""

import sys
import argparse
from pathlib import Path
from datetime import date

from monitor.state import CheckState
from monitor.watcher import DxfWatcher
from config import DATA_DIR, WEB_ENABLED, WEB_HOST, WEB_PORT, get_today_path


def main():
    parser = argparse.ArgumentParser(
        description="DXF Double Line Checker — поиск двойных линий в DXF файлах"
    )
    parser.add_argument("--date", type=str, help="Дата в формате ГГГГ-ММ-ДД")
    parser.add_argument("--path", type=str, help="Путь к папке с DXF файлами")
    parser.add_argument("--once", action="store_true", help="Однократная проверка (без watchdog)")
    parser.add_argument("--web-only", action="store_true", help="Только веб-сервер")
    parser.add_argument("--no-web", action="store_true", help="Без веб-сервера")
    args = parser.parse_args()

    # Определяем директорию
    if args.path:
        watch_dir = args.path
    elif args.date:
        from datetime import date as dt_date
        d = dt_date.fromisoformat(args.date)
        from config import get_path_for_date
        watch_dir = get_path_for_date(d)
    else:
        watch_dir = get_today_path()

    watch_dir = Path(watch_dir)
    print(f"Целевая папка: {watch_dir}")

    # Инициализация состояния
    db_path = DATA_DIR / "dxf_checker.db"
    state = CheckState(db_path)

    # Веб-сервер
    web_server = None
    if WEB_ENABLED and not args.no_web:
        from web.server import run_server
        web_server = run_server(state, WEB_HOST, WEB_PORT)

    if args.web_only:
        print("Режим только веб-сервер. Нажмите Ctrl+C для остановки.")
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nОстановка.")
        return

    # Мониторинг
    watcher = DxfWatcher(state)

    if args.once:
        print("Однократная проверка...")
        watcher.scan_directory(watch_dir)
        print("Готово.")
    else:
        try:
            watcher.run(watch_dir)
        except KeyboardInterrupt:
            print("\nОстановка.")
        finally:
            if web_server:
                web_server.shutdown()


if __name__ == "__main__":
    main()
