"""SQLite 连接与版本化迁移。

数据库结构升级一律通过向 MIGRATIONS 追加新版本实现，规则：
    1. 只增不改：历史版本的脚本内容冻结，新结构写在新版本里；
    2. 每个版本的 SQL 用 IF NOT EXISTS 保证幂等；
    3. open_database 按版本号顺序应用尚未执行的迁移并记录到
       schema_migrations 表；老版本数据库（无该表）打开时自动补记录，数据不受影响。
"""

import os
import sqlite3

# ---------- 迁移脚本（按版本号递增追加，勿修改历史版本） ----------

_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS batches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_name  TEXT    NOT NULL,
    fiber_type  TEXT,
    mode        TEXT    NOT NULL CHECK(mode IN ('filament','textile')),
    density     REAL,
    remark      TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS samples (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id            INTEGER NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    sample_no           TEXT,
    breaking_force      REAL    NOT NULL,
    force_unit          TEXT    NOT NULL DEFAULT 'cN' CHECK(force_unit IN ('cN','N','mN')),
    diameter_um         REAL,
    linear_density_dtex REAL,
    strength            REAL,
    strength_mpa        REAL,
    remark              TEXT,
    test_date           TEXT
);

CREATE INDEX IF NOT EXISTS idx_samples_batch ON samples(batch_id);
CREATE INDEX IF NOT EXISTS idx_batches_created ON batches(created_at);
"""

# 未来扩展示例：
#   - 新增计算模式（core/modes.py 注册表）时：batches.mode 的 CHECK 约束需要放宽，
#     需写 v2 迁移重建 batches 表（SQLite 不支持修改 CHECK），并迁移旧数据；
#   - 追加复合材料电磁屏蔽等新功能域的表：
# _SCHEMA_V2 = """
# CREATE TABLE IF NOT EXISTS emi_evaluations (
#     id INTEGER PRIMARY KEY AUTOINCREMENT, ...);
# """
MIGRATIONS: list[tuple[int, str]] = [
    (1, _SCHEMA_V1),
]


def get_connection(db_path: str) -> sqlite3.Connection:
    """建立连接：启用外键级联删除，行以字典形式返回。"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """按版本顺序应用尚未执行的迁移（幂等，可重复调用）。"""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version INTEGER PRIMARY KEY,"
        "applied_at TEXT NOT NULL DEFAULT (datetime('now','localtime')))")
    applied = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
    for version, script in sorted(MIGRATIONS):
        if version in applied:
            continue
        conn.executescript(script)   # 注意：executescript 会先提交当前事务
        conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
    conn.commit()


def get_schema_version(conn: sqlite3.Connection) -> int:
    """当前数据库已应用的最高 schema 版本（未迁移过的新库为 0）。"""
    row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
    return row["v"] or 0


def open_database(db_path: str) -> sqlite3.Connection:
    """打开数据库并迁移到最新 schema；父目录不存在时自动创建。"""
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = get_connection(db_path)
    migrate(conn)
    return conn
