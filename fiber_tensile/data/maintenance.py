"""数据库备份与维护；只使用 SQLite 在线备份，不直接复制活动数据库。"""

from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime
from pathlib import Path


def backup_database(conn: sqlite3.Connection, target) -> Path:
    """把当前一致性快照原子写入 target，并在替换前执行完整性检查。"""
    destination = Path(target)
    db_row = conn.execute("PRAGMA database_list").fetchone()
    source_path = Path(db_row[2]) if db_row and db_row[2] else None
    if source_path is not None and destination.resolve() == source_path.resolve():
        raise ValueError("备份目标不能与当前正在使用的数据库文件相同")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists():
        temporary.unlink()
    try:
        backup_conn = sqlite3.connect(temporary)
        try:
            conn.backup(backup_conn)
            result = backup_conn.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise sqlite3.DatabaseError(f"备份完整性检查失败：{result!r}")
        finally:
            backup_conn.close()
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    os.replace(temporary, destination)
    return destination


def create_daily_backup(conn: sqlite3.Connection, db_path, *,
                        day: date | None = None, retention: int = 14) -> Path | None:
    """每天首次启动创建一个备份，返回新文件；当天已有备份时返回 None。"""
    source = Path(db_path)
    if str(db_path) == ":memory:" or not source.name:
        return None
    current_day = day or date.today()
    folder = source.parent / "backups"
    target = folder / f"{source.stem}-自动-{current_day:%Y%m%d}.db"
    if target.exists():
        return None
    backup_database(conn, target)
    keep = max(1, int(retention))
    old = sorted(folder.glob(f"{source.stem}-自动-*.db"), reverse=True)
    for path in old[keep:]:
        path.unlink()
    return target


def suggested_backup_name(db_path) -> str:
    source = Path(db_path)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{source.stem or '多功能计算平台'}-手动备份-{stamp}.db"
