"""data/db.py 与 data/repository.py 测试。"""

import pytest

from fiber_tensile.core.models import MODE_FILAMENT, MODE_TEXTILE, Batch, Sample
from fiber_tensile.data.db import open_database
from fiber_tensile.data.repository import (
    add_samples,
    create_batch,
    delete_batch,
    get_batch,
    get_strengths,
    list_batches,
    recalculate_batch,
    update_batch,
)

# 锚点：F=10 cN、d=7 μm → 2598.45 MPa；5 cN/dtex、ρ=1.14 → 570 MPa
ANCHOR_MPA = 2598.45


@pytest.fixture
def db_conn(tmp_path):
    conn = open_database(str(tmp_path / "test.db"))
    yield conn
    conn.close()


def make_filament_samples(n=3):
    return [
        Sample(breaking_force=10.0, force_unit="cN", diameter_um=7.0, sample_no=f"F{i}")
        for i in range(1, n + 1)
    ]


def test_create_and_get_batch(db_conn):
    bid = create_batch(db_conn, Batch(batch_name="B1", mode=MODE_FILAMENT, fiber_type="碳纤维"))
    add_samples(db_conn, bid, make_filament_samples(3))

    b = get_batch(db_conn, bid)
    assert b.batch_name == "B1"
    assert b.mode == MODE_FILAMENT
    assert b.fiber_type == "碳纤维"
    assert b.sample_count == 3
    assert len(b.samples) == 3
    assert b.samples[0].sample_no == "F1"
    assert all(s.strength == pytest.approx(ANCHOR_MPA, rel=1e-3) for s in b.samples)
    assert all(s.strength_mpa is None for s in b.samples)


def test_textile_sample_without_density(db_conn):
    bid = create_batch(db_conn, Batch(batch_name="T1", mode=MODE_TEXTILE))
    add_samples(db_conn, bid, [Sample(breaking_force=10.0, linear_density_dtex=2.0)])
    s = get_batch(db_conn, bid).samples[0]
    assert s.strength == pytest.approx(5.0)   # cN/dtex
    assert s.strength_mpa is None


def test_force_unit_conversion(db_conn):
    # 0.1 N = 10 cN，计算结果应与 cN 录入一致
    bid = create_batch(db_conn, Batch(batch_name="N1", mode=MODE_FILAMENT))
    add_samples(db_conn, bid, [Sample(breaking_force=0.1, force_unit="N", diameter_um=7.0)])
    assert get_batch(db_conn, bid).samples[0].strength == pytest.approx(ANCHOR_MPA, rel=1e-3)


def test_cascade_delete(db_conn):
    bid = create_batch(db_conn, Batch(batch_name="B1", mode=MODE_FILAMENT))
    add_samples(db_conn, bid, make_filament_samples(3))
    delete_batch(db_conn, bid)
    assert list_batches(db_conn) == []
    n = db_conn.execute("SELECT COUNT(*) AS c FROM samples").fetchone()["c"]
    assert n == 0


def test_recalculate_after_density_change(db_conn):
    bid = create_batch(db_conn, Batch(batch_name="T1", mode=MODE_TEXTILE))
    add_samples(db_conn, bid, [Sample(breaking_force=10.0, linear_density_dtex=2.0)])
    assert get_batch(db_conn, bid).samples[0].strength_mpa is None

    update_batch(db_conn, bid, density=1.14)
    s = get_batch(db_conn, bid).samples[0]
    assert s.strength == pytest.approx(5.0)
    assert s.strength_mpa == pytest.approx(570.0)


def test_recalculate_after_raw_value_change(db_conn):
    # 手工改原始强力后，重算应刷新缓存
    bid = create_batch(db_conn, Batch(batch_name="B1", mode=MODE_FILAMENT))
    add_samples(db_conn, bid, [Sample(breaking_force=10.0, diameter_um=7.0)])
    db_conn.execute("UPDATE samples SET breaking_force = 20.0 WHERE batch_id = ?", (bid,))
    db_conn.commit()

    recalculate_batch(db_conn, bid)
    assert get_batch(db_conn, bid).samples[0].strength == pytest.approx(2 * ANCHOR_MPA, rel=1e-3)


def test_list_batches_filters(db_conn):
    b1 = create_batch(db_conn, Batch(batch_name="碳纤维-A", mode=MODE_FILAMENT))
    b2 = create_batch(db_conn, Batch(batch_name="涤纶-B", mode=MODE_TEXTILE))
    add_samples(db_conn, b1, make_filament_samples(2))
    add_samples(db_conn, b2, [Sample(breaking_force=10.0, linear_density_dtex=2.0)])

    all_batches = list_batches(db_conn)
    assert len(all_batches) == 2
    assert all_batches[0].id in (b1, b2)

    assert [b.id for b in list_batches(db_conn, keyword="涤纶")] == [b2]
    assert [b.id for b in list_batches(db_conn, mode=MODE_TEXTILE)] == [b2]
    assert [b.id for b in list_batches(db_conn, keyword="涤纶", mode=MODE_FILAMENT)] == []
    counts = {b.id: b.sample_count for b in all_batches}
    assert counts == {b1: 2, b2: 1}


def test_get_strengths(db_conn):
    bid = create_batch(db_conn, Batch(batch_name="B1", mode=MODE_FILAMENT))
    add_samples(db_conn, bid, make_filament_samples(2))
    strengths = get_strengths(db_conn, bid)
    assert strengths == pytest.approx([ANCHOR_MPA, ANCHOR_MPA], rel=1e-3)


def test_invalid_mode_raises(db_conn):
    with pytest.raises(ValueError):
        create_batch(db_conn, Batch(batch_name="X", mode="bad"))


def test_empty_name_raises(db_conn):
    with pytest.raises(ValueError):
        create_batch(db_conn, Batch(batch_name="   ", mode=MODE_FILAMENT))


def test_add_sample_missing_required_field_raises(db_conn):
    bid = create_batch(db_conn, Batch(batch_name="F1", mode=MODE_FILAMENT))
    with pytest.raises(ValueError):
        add_samples(db_conn, bid, [Sample(breaking_force=10.0)])   # 缺直径
    assert get_batch(db_conn, bid).sample_count == 0


def test_add_sample_invalid_force_unit_raises(db_conn):
    bid = create_batch(db_conn, Batch(batch_name="F1", mode=MODE_FILAMENT))
    with pytest.raises(ValueError):
        add_samples(db_conn, bid, [Sample(breaking_force=10.0, force_unit="kN", diameter_um=7.0)])


def test_unknown_batch_id_raises(db_conn):
    with pytest.raises(ValueError):
        get_batch(db_conn, 999)
    with pytest.raises(ValueError):
        add_samples(db_conn, 999, make_filament_samples(1))


def test_update_batch_rejects_mode_change(db_conn):
    bid = create_batch(db_conn, Batch(batch_name="F1", mode=MODE_FILAMENT))
    with pytest.raises(ValueError):
        update_batch(db_conn, bid, mode=MODE_TEXTILE)
    with pytest.raises(ValueError):
        update_batch(db_conn, bid, batch_name="")


def test_open_database_idempotent_and_creates_dir(tmp_path):
    db_path = str(tmp_path / "nested" / "dir" / "app.db")
    conn = open_database(db_path)   # 目录不存在时自动创建
    conn.close()
    conn = open_database(db_path)   # 重复打开幂等
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"batches", "samples"} <= tables
