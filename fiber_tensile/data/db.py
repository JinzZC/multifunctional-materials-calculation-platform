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

# v2：表面能计算模块（第二个功能域）
#   se_measurements 测量记录（结果缓存列由持久层在创建时写入）
#   se_liquid_points 每条测量使用的液体与接触角（级联删除）
#   se_liquids 液体参数库（内置 8 种 + 用户自定义）
_SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS se_measurements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_name TEXT    NOT NULL,
    method      TEXT    NOT NULL CHECK(method IN ('owrk','wu','fowkes','zisman')),
    gamma_d     REAL,
    gamma_p     REAL,
    gamma_total REAL,
    gamma_c     REAL,
    r2          REAL,
    remark      TEXT,
    test_date   TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS se_liquid_points (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    measurement_id INTEGER NOT NULL REFERENCES se_measurements(id) ON DELETE CASCADE,
    liquid_name    TEXT    NOT NULL,
    gamma_total    REAL    NOT NULL,
    gamma_d        REAL,
    gamma_p        REAL,
    angle_deg      REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS se_liquids (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    gamma_total REAL    NOT NULL,
    gamma_d     REAL    NOT NULL,
    gamma_p     REAL    NOT NULL,
    builtin     INTEGER NOT NULL DEFAULT 0
);

INSERT OR IGNORE INTO se_liquids (name, gamma_total, gamma_d, gamma_p, builtin) VALUES
 ('水', 72.8, 21.8, 51.0, 1),
 ('二碘甲烷', 50.8, 50.8, 0.0, 1),
 ('乙二醇', 48.0, 29.0, 19.0, 1),
 ('甘油', 64.0, 34.0, 30.0, 1),
 ('甲酰胺', 58.2, 39.5, 18.7, 1),
 ('α-溴萘', 44.4, 44.4, 0.0, 1),
 ('十六烷', 27.6, 27.6, 0.0, 1),
 ('苯甲醇', 39.0, 30.3, 8.7, 1);
"""
# v3：单丝拉伸曲线分析（平台校正）+ 复合材料基础计算
_SCHEMA_V3 = """
CREATE TABLE IF NOT EXISTS fiber_curves (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_name      TEXT    NOT NULL,
    diameter_um      REAL    NOT NULL,
    gauge_length_mm  REAL    NOT NULL,
    fit_lo           REAL,
    fit_hi           REAL,
    e_gpa            REAL,
    strength_mpa     REAL,
    elongation_pct   REAL,
    toe_eps_pct      REAL,
    r2               REAL,
    points_json      TEXT,
    remark           TEXT,
    test_date        TEXT,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS cm_calcs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    calc_type    TEXT    NOT NULL CHECK(calc_type IN ('rom','volume_fraction')),
    sample_name  TEXT    NOT NULL,
    inputs_json  TEXT    NOT NULL,
    e1_gpa       REAL,
    e2_gpa       REAL,
    g12_gpa      REAL,
    nu12         REAL,
    rho_gcm3     REAL,
    vf           REAL,
    vm           REAL,
    vv           REAL,
    remark       TEXT,
    test_date    TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);
"""
MIGRATIONS: list[tuple[int, str]] = [
    (1, _SCHEMA_V1),
    (2, _SCHEMA_V2),
    (3, _SCHEMA_V3),
]


def get_connection(db_path: str) -> sqlite3.Connection:
    """建立连接：启用外键级联删除，行以字典形式返回。"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """按版本顺序应用尚未执行的迁移（幂等，可重复调用）。"""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version INTEGER PRIMARY KEY,"
        "applied_at TEXT NOT NULL DEFAULT (datetime('now','localtime')))")
    conn.commit()
    applied = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
    for version, script in sorted(MIGRATIONS):
        if version in applied:
            continue
        # executescript 会先提交已有事务，因此把 BEGIN、结构修改和版本标记放进
        # 同一段脚本；任何 SQL 失败都不会留下“结构已变、版本未记录”的半迁移状态。
        migration_sql = (
            "BEGIN IMMEDIATE;\n" + script +
            f"\nINSERT INTO schema_migrations (version) VALUES ({int(version)});\n"
            "COMMIT;")
        try:
            conn.executescript(migration_sql)
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise


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
