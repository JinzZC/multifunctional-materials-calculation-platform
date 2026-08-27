"""生成不包含用户原始数据的诊断压缩包。"""

from __future__ import annotations

import json
import os
import platform
import sqlite3
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from ..config import APP_NAME, APP_VERSION
from ..data.db import get_schema_version


def create_diagnostic_zip(target, conn: sqlite3.Connection, log_path=None) -> Path:
    """写出环境、表计数和日志；不写数据库文件、记录内容或绝对数据库路径。"""
    output = Path(target)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    if temporary.exists():
        temporary.unlink()
    tables = {}
    for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        name = row[0]
        # 表名来自 sqlite_master，而非外部输入。
        safe_name = name.replace('"', '""')
        tables[name] = conn.execute(
            f'SELECT COUNT(*) FROM "{safe_name}"').fetchone()[0]
    info = {
        "application": APP_NAME,
        "version": APP_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "python": sys.version,
        "platform": platform.platform(),
        "schema_version": get_schema_version(conn),
        "table_row_counts": tables,
    }
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("system-info.json", json.dumps(info, ensure_ascii=False, indent=2))
        if log_path and Path(log_path).is_file():
            data = Path(log_path).read_bytes()[-1_000_000:]
            archive.writestr("app.log", data)
        archive.writestr(
            "说明.txt",
            "此诊断包包含软件版本、运行环境、数据库表记录数量和最近日志，"
            "不包含数据库文件或样品原始数据。\n")
    os.replace(temporary, output)
    return output
