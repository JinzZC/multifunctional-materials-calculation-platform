"""data/db.py 版本化迁移测试。"""

import sqlite3

import pytest

import fiber_tensile.data.db as db_module
from fiber_tensile.data.db import MIGRATIONS, get_schema_version, migrate, open_database


def test_fresh_database_gets_latest_version(tmp_path):
    conn = open_database(str(tmp_path / "a.db"))
    try:
        assert get_schema_version(conn) == MIGRATIONS[-1][0]
        tables = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"batches", "samples", "schema_migrations"} <= tables
    finally:
        conn.close()


def test_migrate_is_idempotent(tmp_path):
    path = str(tmp_path / "b.db")
    conn = open_database(path)
    migrate(conn)
    migrate(conn)
    assert get_schema_version(conn) == MIGRATIONS[-1][0]
    conn.close()


def test_legacy_database_is_adopted_without_data_loss(tmp_path):
    """老版本数据库（有表但无 schema_migrations）打开后自动补记录，数据完好。"""
    path = str(tmp_path / "legacy.db")
    raw = sqlite3.connect(path)
    raw.executescript(MIGRATIONS[0][1])     # 模拟老代码建的表
    raw.execute("INSERT INTO batches (batch_name, mode) VALUES ('老批次', 'filament')")
    raw.commit()
    raw.close()

    conn = open_database(path)
    try:
        assert get_schema_version(conn) == MIGRATIONS[-1][0]
        assert conn.execute("SELECT COUNT(*) AS c FROM batches").fetchone()["c"] == 1
    finally:
        conn.close()


def test_new_migration_script_is_applied(monkeypatch, tmp_path):
    """模拟未来追加迁移：只应用未执行的新版本。"""
    v4_script = "CREATE TABLE IF NOT EXISTS emi_evaluations (id INTEGER PRIMARY KEY);"
    monkeypatch.setattr(db_module, "MIGRATIONS", MIGRATIONS + [(4, v4_script)])

    conn = open_database(str(tmp_path / "c.db"))
    try:
        assert get_schema_version(conn) == 4
        tables = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "emi_evaluations" in tables
        assert "se_measurements" in tables      # v2 也一并应用
        assert "fiber_curves" in tables         # v3 也一并应用
    finally:
        conn.close()


def test_existing_database_upgraded_when_new_version_added(monkeypatch, tmp_path):
    """已有 v1 数据库，追加新版后重新打开应自动升级且旧数据保留。"""
    path = str(tmp_path / "d.db")
    conn = open_database(path)
    conn.execute("INSERT INTO batches (batch_name, mode) VALUES ('已有批次', 'textile')")
    conn.commit()
    assert get_schema_version(conn) == MIGRATIONS[-1][0]
    conn.close()

    v4_script = "CREATE TABLE IF NOT EXISTS emi_evaluations (id INTEGER PRIMARY KEY);"
    monkeypatch.setattr(db_module, "MIGRATIONS", MIGRATIONS + [(4, v4_script)])
    conn = open_database(path)
    try:
        assert get_schema_version(conn) == 4
        assert conn.execute("SELECT COUNT(*) AS c FROM batches").fetchone()["c"] == 1
    finally:
        conn.close()


def test_failed_migration_rolls_back_schema_and_version(monkeypatch, tmp_path):
    """迁移中途失败时，新表和版本标记必须一起回滚。"""
    broken = ("CREATE TABLE half_applied (id INTEGER PRIMARY KEY);"
              "INSERT INTO table_that_does_not_exist VALUES (1);")
    monkeypatch.setattr(db_module, "MIGRATIONS", MIGRATIONS + [(4, broken)])
    path = str(tmp_path / "atomic.db")
    with pytest.raises(sqlite3.OperationalError):
        open_database(path)

    raw = sqlite3.connect(path)
    try:
        tables = {row[0] for row in raw.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        versions = {row[0] for row in raw.execute(
            "SELECT version FROM schema_migrations")}
        assert "half_applied" not in tables
        assert 4 not in versions
    finally:
        raw.close()
