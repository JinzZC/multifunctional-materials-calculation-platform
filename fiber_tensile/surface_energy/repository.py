"""表面能测量记录的持久层（SQLite，表结构见 data/db.py 迁移 v2）。

测量结果在创建时用计算核心求出并缓存到 se_measurements 的结果列，
列表查询直接读缓存；原始液体数据保存在 se_liquid_points。
"""

import sqlite3

from .core import LiquidPoint, compute_surface_energy


def _point_from_row(row: sqlite3.Row) -> LiquidPoint:
    return LiquidPoint(
        liquid_name=row["liquid_name"],
        gamma_total=row["gamma_total"],
        angle_deg=row["angle_deg"],
        gamma_d=row["gamma_d"],
        gamma_p=row["gamma_p"],
    )


def create_measurement(conn: sqlite3.Connection, sample_name: str, method: str,
                       points: list, remark: str | None = None,
                       test_date: str | None = None) -> int:
    """新建测量记录：先计算（校验失败抛 ValueError），再连同液体数据写入。"""
    name = (sample_name or "").strip()
    if not name:
        raise ValueError("样品名称不能为空")
    pts = [p if isinstance(p, LiquidPoint) else LiquidPoint(**p) for p in points]
    result = compute_surface_energy(method, pts)

    cur = conn.execute(
        "INSERT INTO se_measurements "
        "(sample_name, method, gamma_d, gamma_p, gamma_total, gamma_c, r2, remark, test_date) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (name, method, result.gamma_d, result.gamma_p, result.gamma_total,
         result.gamma_c, result.r2, remark, test_date))
    mid = cur.lastrowid
    conn.executemany(
        "INSERT INTO se_liquid_points "
        "(measurement_id, liquid_name, gamma_total, gamma_d, gamma_p, angle_deg) "
        "VALUES (?,?,?,?,?,?)",
        [(mid, p.liquid_name, p.gamma_total, p.gamma_d, p.gamma_p, p.angle_deg)
         for p in pts])
    conn.commit()
    return mid


def get_measurement(conn: sqlite3.Connection, mid: int) -> tuple:
    """返回 (测量记录行, 液体点列表)。"""
    row = conn.execute("SELECT * FROM se_measurements WHERE id = ?", (mid,)).fetchone()
    if row is None:
        raise ValueError(f"测量记录不存在：id={mid}")
    points = [_point_from_row(r) for r in conn.execute(
        "SELECT * FROM se_liquid_points WHERE measurement_id = ? ORDER BY id",
        (mid,)).fetchall()]
    return row, points


def list_measurements(conn: sqlite3.Connection, keyword: str | None = None,
                      method: str | None = None) -> list:
    """按条件查询测量记录（含液体种数），按创建时间倒序。"""
    sql = ("SELECT m.*, (SELECT COUNT(*) FROM se_liquid_points p "
           "WHERE p.measurement_id = m.id) AS point_count "
           "FROM se_measurements m WHERE 1=1")
    params: list = []
    if keyword:
        sql += " AND m.sample_name LIKE ?"
        params.append(f"%{keyword}%")
    if method:
        sql += " AND m.method = ?"
        params.append(method)
    sql += " ORDER BY m.created_at DESC, m.id DESC"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def delete_measurement(conn: sqlite3.Connection, mid: int) -> None:
    """删除测量记录（级联删除其液体点）。"""
    conn.execute("DELETE FROM se_measurements WHERE id = ?", (mid,))
    conn.commit()


def list_liquids(conn: sqlite3.Connection) -> list:
    """液体参数库（内置在前，自定义在后）。"""
    return [dict(r) for r in conn.execute(
        "SELECT * FROM se_liquids ORDER BY builtin DESC, id").fetchall()]


def add_liquid(conn: sqlite3.Connection, name: str, gamma_total: float,
               gamma_d: float, gamma_p: float) -> int:
    """添加自定义液体到参数库，返回 id；重名或数值无效抛 ValueError。"""
    name = (name or "").strip()
    if not name:
        raise ValueError("液体名称不能为空")
    if not isinstance(gamma_total, (int, float)) or gamma_total <= 0:
        raise ValueError("总表面张力必须为正数")
    # 分量为非负即可（非极性液体的极性分量为 0，如二碘甲烷/烷烃）
    for label, v in (("色散分量", gamma_d), ("极性分量", gamma_p)):
        if not isinstance(v, (int, float)) or v < 0:
            raise ValueError(f"{label}不能为负数")
    if gamma_d + gamma_p > gamma_total + 1e-6:
        raise ValueError("分量之和不能大于总表面张力")
    try:
        cur = conn.execute(
            "INSERT INTO se_liquids (name, gamma_total, gamma_d, gamma_p, builtin) "
            "VALUES (?,?,?,?,0)", (name, gamma_total, gamma_d, gamma_p))
    except sqlite3.IntegrityError:
        raise ValueError(f"液体「{name}」已存在于参数库") from None
    conn.commit()
    return cur.lastrowid
