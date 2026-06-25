import os
from pathlib import Path

# Базовый путь к сетевой папке с DXF файлами
BASE_PATH = Path("Z:/LASERTECHNO")

# Допуск для определения "двойной линии" в мм
TOLERANCE = 0.1

# Паттерн имени файла: буквы + _ + цифры.dxf
FILE_PATTERN = "*_*.dxf"

# Папка для HTML-отчетов
REPORTS_DIR = Path(__file__).parent / "reports"

# Папка для SQLite БД
DATA_DIR = Path(__file__).parent / "data"

# Интервал периодической проверки в секундах
POLL_INTERVAL = 30

# Включить/отключить watchdog (реального времени)
USE_WATCHDOG = True

# Путь к Python (для запуска планировщиком)
PYTHON_PATH = "python"

# Настройки веб-сервера
WEB_HOST = "0.0.0.0"
WEB_PORT = 8080
WEB_ENABLED = True

# Количество воркеров при параллельной проверке
MAX_WORKERS = 4

def get_today_path():
    """Возвращает путь к今天的 папке вида Z:\\LASERTECHNO\\2026\\06\\25"""
    from datetime import date
    today = date.today()
    return BASE_PATH / str(today.year) / f"{today.month:02d}" / f"{today.day:02d}"

def get_path_for_date(d: date):
    return BASE_PATH / str(d.year) / f"{d.month:02d}" / f"{d.day:02d}"
