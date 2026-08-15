"""复合材料基础计算的持久层（表结构见 data/db.py 迁移 v3 的 cm_calcs）。"""

import json
import sqlite3


def _insert(conn, calc_type, sample_name, inputs, result, remark, test_date,
            e1=None, e2=None, g12=None, nu12=None, rho=None,
            vf=None, vm=None, vv=None) -> int:
    name = (sample_name or "").strip()
    if not name:
        raise ValueError("样品名称不能为空")
    cur = conn.execute(
        "INSERT INTO cm_calcs (calc_type, sample_name, inputs_json, "
        "e1_gpa, e2_gpa, g12_gpa, nu12, rho_gcm3, vf, vm, vv, remark, test_date) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (calc_type, name, json.dumps(inputs, ensure_ascii=False),
         e1, e2, g12, nu12, rho, vf, vm, vv, remark, test_date))
    conn.commit()
    return cur.lastrowid


def create_rom(conn, sample_name: str, inputs: dict, result,
               remark=None, test_date=None) -> int:
    return _insert(conn, "rom", sample_name, inputs, result, remark, test_date,
                   e1=result.e1_gpa, e2=result.e2_gpa, g12=result.g12_gpa,
                   nu12=result.nu12, rho=result.rho_gcm3)


def create_vf(conn, sample_name: str, inputs: dict, result,
              remark=None, test_date=None) -> int:
    return _insert(conn, "volume_fraction", sample_name, inputs, result,
                   remark, test_date, vf=result.vf, vm=result.vm, vv=result.vv)


def get_cm_calc(conn, cid: int) -> dict:
    row = conn.execute("SELECT * FROM cm_calcs WHERE id = ?", (cid,)).fetchone()
    if row is None:
        raise ValueError(f"计算记录不存在：id={cid}")
    d = dict(row)
    d["inputs"] = json.loads(d["inputs_json"])
    return d


def list_cm_calcs(conn, calc_type: str | None = None,
                  keyword: str | None = None) -> list:
    sql = "SELECT * FROM cm_calcs WHERE 1=1"
    params: list = []
    if calc_type:
        sql += " AND calc_type = ?"
        params.append(calc_type)
    if keyword:
        sql += " AND sample_name LIKE ?"
        params.append(f"%{keyword}%")
    sql += " ORDER BY created_at DESC, id DESC"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def delete_cm_calc(conn, cid: int) -> None:
    conn.execute("DELETE FROM cm_calcs WHERE id = ?", (cid,))
    conn.commit()
