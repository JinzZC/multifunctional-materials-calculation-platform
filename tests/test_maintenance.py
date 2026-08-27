"""数据库备份、全局搜索和诊断包测试（全部使用临时库）。"""

import json
import sqlite3
import zipfile
from datetime import date, timedelta

from fiber_tensile.data.db import open_database
from fiber_tensile.data.maintenance import backup_database, create_daily_backup
from fiber_tensile.data.search import search_all
from fiber_tensile.fileio.diagnostics import create_diagnostic_zip


def _database(tmp_path):
    path = tmp_path / "test.db"
    return path, open_database(str(path))


def test_online_backup_is_consistent_and_independent(tmp_path):
    path, conn = _database(tmp_path)
    conn.execute("INSERT INTO batches (batch_name, mode) VALUES ('CF-A', 'filament')")
    conn.commit()
    output = backup_database(conn, tmp_path / "copy.db")
    with sqlite3.connect(output) as copied:
        assert copied.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert copied.execute("SELECT batch_name FROM batches").fetchone()[0] == "CF-A"
    conn.execute("DELETE FROM batches")
    conn.commit()
    with sqlite3.connect(output) as copied:
        assert copied.execute("SELECT COUNT(*) FROM batches").fetchone()[0] == 1
    conn.close()


def test_backup_refuses_to_replace_active_database(tmp_path):
    path, conn = _database(tmp_path)
    import pytest
    with pytest.raises(ValueError, match="当前正在使用"):
        backup_database(conn, path)
    conn.close()


def test_daily_backup_once_and_retention(tmp_path):
    path, conn = _database(tmp_path)
    start = date(2026, 8, 1)
    for offset in range(4):
        assert create_daily_backup(conn, path, day=start + timedelta(days=offset),
                                   retention=3) is not None
    assert create_daily_backup(conn, path, day=start + timedelta(days=3),
                               retention=3) is None
    backups = list((tmp_path / "backups").glob("test-自动-*.db"))
    assert len(backups) == 3
    conn.close()


def test_search_all_domains(tmp_path):
    _path, conn = _database(tmp_path)
    conn.execute("INSERT INTO batches (batch_name, mode, remark) VALUES (?, ?, ?)",
                 ("碳纤维-A", "filament", "检索标记"))
    conn.execute("INSERT INTO se_measurements (sample_name, method, remark) VALUES (?, ?, ?)",
                 ("碳纤维表面", "owrk", "检索标记"))
    conn.execute("INSERT INTO fiber_curves (sample_name, diameter_um, gauge_length_mm, remark) "
                 "VALUES (?, ?, ?, ?)", ("曲线-A", 7, 20, "检索标记"))
    conn.execute("INSERT INTO cm_calcs (calc_type, sample_name, inputs_json, remark) "
                 "VALUES (?, ?, ?, ?)", ("rom", "复材-A", "{}", "检索标记"))
    conn.commit()
    results = search_all(conn, "检索标记")
    assert {item.module for item in results} == {
        "纤维拉伸强度", "接触角表面能", "单丝曲线", "复合材料"}
    conn.close()


def test_diagnostics_excludes_database_content(tmp_path):
    _path, conn = _database(tmp_path)
    secret = "SECRET_SAMPLE_987654"
    conn.execute("INSERT INTO batches (batch_name, mode) VALUES (?, 'filament')", (secret,))
    conn.commit()
    log = tmp_path / "app.log"
    log.write_text("normal diagnostic log", encoding="utf-8")
    output = create_diagnostic_zip(tmp_path / "diag.zip", conn, log)
    with zipfile.ZipFile(output) as archive:
        assert set(archive.namelist()) == {"system-info.json", "app.log", "说明.txt"}
        info = json.loads(archive.read("system-info.json"))
        assert info["table_row_counts"]["batches"] == 1
        combined = b"".join(archive.read(name) for name in archive.namelist())
        assert secret.encode("utf-8") not in combined
    conn.close()
