"""单丝曲线分析的持久层（表结构见 data/db.py 迁移 v3）。"""

import json
import math
import sqlite3


def create_curve_analysis(conn: sqlite3.Connection, sample_name: str,
                          diameter_um: float, gauge_mm: float, result,
                          disp_mm, force_n, fit_lo: float = 0.2,
                          fit_hi: float = 0.7, remark=None,
                          test_date=None) -> int:
    """保存曲线分析：结果缓存列 + 拟合区间 + 原始曲线点（JSON）。"""
    name = (sample_name or "").strip()
    if not name:
        raise ValueError("样品名称不能为空")
    x_values = [float(x) for x in disp_mm]
    y_values = [float(y) for y in force_n]
    if len(x_values) != len(y_values):
        raise ValueError("位移与力数据长度不一致，无法保存")
    if not x_values:
        raise ValueError("没有可保存的曲线数据")
    if any(not math.isfinite(v) for v in x_values + y_values):
        raise ValueError("曲线数据包含无效数值，无法保存")
    # 数据库保留原始浮点精度；显示和报告层再按需要格式化。
    points = [[x, y] for x, y in zip(x_values, y_values)]
    cur = conn.execute(
        "INSERT INTO fiber_curves (sample_name, diameter_um, gauge_length_mm, "
        "fit_lo, fit_hi, e_gpa, strength_mpa, elongation_pct, toe_eps_pct, r2, "
        "points_json, remark, test_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (name, diameter_um, gauge_mm, fit_lo, fit_hi, result.e_gpa,
         result.strength_mpa, result.elongation_pct, result.toe_eps_pct,
         result.r2, json.dumps(points), remark, test_date))
    conn.commit()
    return cur.lastrowid


def get_curve_analysis(conn: sqlite3.Connection, cid: int) -> tuple:
    """返回 (记录行, [(位移, 力), ...])。"""
    row = conn.execute("SELECT * FROM fiber_curves WHERE id = ?", (cid,)).fetchone()
    if row is None:
        raise ValueError(f"曲线分析记录不存在：id={cid}")
    points = json.loads(row["points_json"] or "[]")
    return row, points


def list_curve_analyses(conn: sqlite3.Connection, keyword: str | None = None) -> list:
    sql = "SELECT * FROM fiber_curves WHERE 1=1"
    params: list = []
    if keyword:
        sql += " AND sample_name LIKE ?"
        params.append(f"%{keyword}%")
    sql += " ORDER BY created_at DESC, id DESC"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def delete_curve_analysis(conn: sqlite3.Connection, cid: int) -> None:
    conn.execute("DELETE FROM fiber_curves WHERE id = ?", (cid,))
    conn.commit()
