"""批次与样本的 CRUD、强度缓存重算。

只存原始输入（断裂强力、直径/线密度等），strength / strength_mpa 为缓存列，
任何写入后调用 recalculate_batch() 统一重算，保证查询时直接读缓存即可。
"""

import sqlite3
from typing import Sequence

from ..core.formulas import compute_strength
from ..core.models import VALID_FORCE_UNITS, VALID_MODES, Batch, Sample
from ..core.units import force_to_cn

# update_batch 允许修改的字段（模式不可改：换模式需新建批次）
_UPDATABLE_FIELDS = ("batch_name", "fiber_type", "density", "remark")


def _validate_mode(mode: str) -> None:
    if mode not in VALID_MODES:
        raise ValueError(f"未知模式：{mode!r}（仅支持 {VALID_MODES}）")


def _sample_from_row(row: sqlite3.Row) -> Sample:
    return Sample(
        breaking_force=row["breaking_force"],
        force_unit=row["force_unit"],
        diameter_um=row["diameter_um"],
        linear_density_dtex=row["linear_density_dtex"],
        sample_no=row["sample_no"],
        remark=row["remark"],
        test_date=row["test_date"],
        id=row["id"],
        batch_id=row["batch_id"],
        strength=row["strength"],
        strength_mpa=row["strength_mpa"],
    )


def _batch_from_row(row: sqlite3.Row, sample_count: int = 0) -> Batch:
    return Batch(
        batch_name=row["batch_name"],
        mode=row["mode"],
        fiber_type=row["fiber_type"],
        density=row["density"],
        remark=row["remark"],
        created_at=row["created_at"],
        id=row["id"],
        sample_count=sample_count,
    )


def create_batch(conn: sqlite3.Connection, batch: Batch) -> int:
    """新建批次，返回批次 id。"""
    _validate_mode(batch.mode)
    name = (batch.batch_name or "").strip()
    if not name:
        raise ValueError("批次名称不能为空")
    cur = conn.execute(
        "INSERT INTO batches (batch_name, fiber_type, mode, density, remark) VALUES (?,?,?,?,?)",
        (name, batch.fiber_type, batch.mode, batch.density, batch.remark),
    )
    conn.commit()
    return cur.lastrowid


def update_batch(conn: sqlite3.Connection, batch_id: int, **fields) -> None:
    """修改批次信息（名称/纤维类型/密度/备注），随后重算强度缓存。"""
    unknown = set(fields) - set(_UPDATABLE_FIELDS)
    if unknown:
        raise ValueError(f"不允许修改的字段：{sorted(unknown)}")
    if not fields:
        return
    if "batch_name" in fields and not (fields["batch_name"] or "").strip():
        raise ValueError("批次名称不能为空")
    get_batch_meta(conn, batch_id)  # 确保批次存在
    assignments = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(
        f"UPDATE batches SET {assignments} WHERE id = ?",
        (*fields.values(), batch_id),
    )
    conn.commit()
    recalculate_batch(conn, batch_id)


def delete_batch(conn: sqlite3.Connection, batch_id: int) -> None:
    """删除批次（外键级联删除其下所有样本）。"""
    conn.execute("DELETE FROM batches WHERE id = ?", (batch_id,))
    conn.commit()


def add_samples(conn: sqlite3.Connection, batch_id: int, samples: Sequence[Sample]) -> int:
    """向批次追加样本，写入时即时计算强度缓存。返回写入条数。"""
    batch = get_batch_meta(conn, batch_id)
    if not samples:
        return 0
    rows = []
    for i, s in enumerate(samples):
        if s.force_unit not in VALID_FORCE_UNITS:
            raise ValueError(f"第 {i + 1} 条数据的强力单位无效：{s.force_unit!r}")
        force_cn = force_to_cn(s.breaking_force, s.force_unit)
        strength, strength_mpa = compute_strength(
            batch.mode, force_cn, s.diameter_um, s.linear_density_dtex, batch.density)
        rows.append((
            batch_id, s.sample_no, s.breaking_force, s.force_unit,
            s.diameter_um, s.linear_density_dtex,
            strength, strength_mpa, s.remark, s.test_date,
        ))
    conn.executemany(
        "INSERT INTO samples (batch_id, sample_no, breaking_force, force_unit, "
        "diameter_um, linear_density_dtex, strength, strength_mpa, remark, test_date) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    return len(rows)


def recalculate_batch(conn: sqlite3.Connection, batch_id: int) -> int:
    """按当前批次信息重算该批次全部样本的强度缓存，返回样本数。"""
    batch = get_batch_meta(conn, batch_id)
    rows = conn.execute(
        "SELECT id, breaking_force, force_unit, diameter_um, linear_density_dtex "
        "FROM samples WHERE batch_id = ? ORDER BY id",
        (batch_id,),
    ).fetchall()
    for row in rows:
        force_cn = force_to_cn(row["breaking_force"], row["force_unit"])
        strength, strength_mpa = compute_strength(
            batch.mode, force_cn, row["diameter_um"], row["linear_density_dtex"], batch.density)
        conn.execute(
            "UPDATE samples SET strength = ?, strength_mpa = ? WHERE id = ?",
            (strength, strength_mpa, row["id"]),
        )
    conn.commit()
    return len(rows)


def get_batch_meta(conn: sqlite3.Connection, batch_id: int) -> Batch:
    """按 id 取批次信息（不含样本）。"""
    row = conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if row is None:
        raise ValueError(f"批次不存在：id={batch_id}")
    return _batch_from_row(row)


def get_batch(conn: sqlite3.Connection, batch_id: int) -> Batch:
    """按 id 取批次及其全部样本（按录入顺序）。"""
    batch = get_batch_meta(conn, batch_id)
    rows = conn.execute(
        "SELECT * FROM samples WHERE batch_id = ? ORDER BY id", (batch_id,)).fetchall()
    batch.sample_count = len(rows)
    batch.samples = [_sample_from_row(r) for r in rows]
    return batch


def list_batches(conn: sqlite3.Connection, keyword: str | None = None,
                 mode: str | None = None, date_from: str | None = None,
                 date_to: str | None = None) -> list[Batch]:
    """按条件查询批次列表（含样本数），按创建时间倒序。日期格式 YYYY-MM-DD。"""
    sql = (
        "SELECT b.*, (SELECT COUNT(*) FROM samples s WHERE s.batch_id = b.id) AS sample_count "
        "FROM batches b WHERE 1=1"
    )
    params: list = []
    if keyword:
        sql += " AND b.batch_name LIKE ?"
        params.append(f"%{keyword}%")
    if mode:
        _validate_mode(mode)
        sql += " AND b.mode = ?"
        params.append(mode)
    if date_from:
        sql += " AND date(b.created_at) >= date(?)"
        params.append(date_from)
    if date_to:
        sql += " AND date(b.created_at) <= date(?)"
        params.append(date_to)
    sql += " ORDER BY b.created_at DESC, b.id DESC"
    rows = conn.execute(sql, params).fetchall()
    return [_batch_from_row(r, r["sample_count"]) for r in rows]


def get_strengths(conn: sqlite3.Connection, batch_id: int) -> list[float]:
    """取该批次全部样本的强度（模式本征单位：单丝=MPa，纺织=cN/dtex），按录入顺序。"""
    get_batch_meta(conn, batch_id)
    rows = conn.execute(
        "SELECT strength FROM samples WHERE batch_id = ? ORDER BY id", (batch_id,)).fetchall()
    return [float(r["strength"]) for r in rows]
