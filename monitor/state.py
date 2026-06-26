import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional


class CheckState:
    """SQLite-хранилище состояния проверенных файлов."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._init_db()

    def _init_db(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS checked_files (
                filepath TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                filesize INTEGER NOT NULL DEFAULT 0,
                file_mtime REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                has_errors INTEGER NOT NULL DEFAULT 0,
                total_problems INTEGER NOT NULL DEFAULT 0,
                report_path TEXT,
                checked_at TEXT,
                error_details TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_checked_files_status
            ON checked_files(status)
        """)
        self._conn.commit()

    def is_checked(self, filepath: str) -> bool:
        """Проверяет, был ли файл уже проверен."""
        row = self._conn.execute(
            "SELECT filepath FROM checked_files WHERE filepath = ?", (filepath,)
        ).fetchone()
        return row is not None

    def needs_check(self, filepath: str, filesize: int, mtime: float) -> bool:
        """Проверяет, нужно ли перепроверить файл (новый или изменённый)."""
        row = self._conn.execute(
            "SELECT filesize, file_mtime FROM checked_files WHERE filepath = ?",
            (filepath,),
        ).fetchone()
        if row is None:
            return True
        return row[0] != filesize or abs(row[1] - mtime) > 0.001

    def mark_checked(
        self,
        filepath: str,
        filename: str,
        filesize: int,
        mtime: float,
        status: str,
        has_errors: bool,
        total_problems: int,
        report_path: Optional[str] = None,
        error_details: Optional[dict] = None,
    ):
        self._conn.execute(
            """INSERT OR REPLACE INTO checked_files
               (filepath, filename, filesize, file_mtime, status,
                has_errors, total_problems, report_path, checked_at, error_details)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)""",
            (
                filepath,
                filename,
                filesize,
                mtime,
                status,
                1 if has_errors else 0,
                total_problems,
                report_path,
                json.dumps(error_details) if error_details else None,
            ),
        )
        self._conn.commit()

    def get_stats(self) -> dict:
        """Возвращает статистику по проверкам."""
        total = self._conn.execute("SELECT COUNT(*) FROM checked_files").fetchone()[0]
        with_errors = self._conn.execute(
            "SELECT COUNT(*) FROM checked_files WHERE has_errors = 1"
        ).fetchone()[0]
        today_checked = self._conn.execute(
            "SELECT COUNT(*) FROM checked_files WHERE date(checked_at) = date('now')"
        ).fetchone()[0]
        return {
            "total": total,
            "with_errors": with_errors,
            "today_checked": today_checked,
        }

    def get_recent(self, limit: int = 50) -> list:
        rows = self._conn.execute(
            "SELECT filepath, filename, status, has_errors, total_problems, "
            "report_path, checked_at FROM checked_files "
            "ORDER BY checked_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "filepath": r[0],
                "filename": r[1],
                "status": r[2],
                "has_errors": bool(r[3]),
                "total_problems": r[4],
                "report_path": r[5],
                "checked_at": r[6],
                "report_exists": r[5] is not None and Path(r[5]).exists(),
            }
            for r in rows
        ]

    def get_file_info(self, filepath: str) -> dict | None:
        """Возвращает детальную информацию о файле."""
        row = self._conn.execute(
            "SELECT filepath, filename, status, has_errors, total_problems, "
            "report_path, checked_at, error_details FROM checked_files "
            "WHERE filepath = ?",
            (filepath,),
        ).fetchone()
        if row is None:
            return None
        rp = row[5]
        return {
            "filepath": row[0],
            "filename": row[1],
            "status": row[2],
            "has_errors": bool(row[3]),
            "total_problems": row[4],
            "report_path": rp,
            "report_exists": rp is not None and Path(rp).exists(),
            "checked_at": row[6],
            "error_details": json.loads(row[7]) if row[7] else None,
        }

    def close(self):
        self._conn.close()
