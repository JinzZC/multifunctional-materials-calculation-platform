"""surface_energy/repository.py 持久层测试。"""

import pytest

from fiber_tensile.data.db import open_database
from fiber_tensile.surface_energy.core import METHOD_OWRK, LiquidPoint
from fiber_tensile.surface_energy.repository import (
    add_liquid,
    create_measurement,
    delete_measurement,
    get_measurement,
    list_liquids,
    list_measurements,
)

WATER = LiquidPoint("水", 72.8, 108.0, gamma_d=21.8, gamma_p=51.0)
DIIODOMETHANE = LiquidPoint("二碘甲烷", 50.8, 77.0, gamma_d=50.8, gamma_p=0.0)


@pytest.fixture
def db_conn(tmp_path):
    conn = open_database(str(tmp_path / "se.db"))
    yield conn
    conn.close()


def test_create_and_get_measurement(db_conn):
    mid = create_measurement(db_conn, "PTFE 样品", METHOD_OWRK,
                             [WATER, DIIODOMETHANE], remark="测试", test_date="2026-08-15")
    row, points = get_measurement(db_conn, mid)
    assert row["sample_name"] == "PTFE 样品"
    assert row["method"] == METHOD_OWRK
    assert row["gamma_d"] > 0 and row["gamma_p"] > 0
    assert row["gamma_total"] == pytest.approx(row["gamma_d"] + row["gamma_p"])
    assert row["r2"] == pytest.approx(1.0, abs=1e-9)
    assert len(points) == 2
    assert points[0].liquid_name == "水"


def test_cascade_delete(db_conn):
    mid = create_measurement(db_conn, "A", METHOD_OWRK, [WATER, DIIODOMETHANE])
    delete_measurement(db_conn, mid)
    assert list_measurements(db_conn) == []
    n = db_conn.execute("SELECT COUNT(*) AS c FROM se_liquid_points").fetchone()["c"]
    assert n == 0


def test_list_filters(db_conn):
    mid1 = create_measurement(db_conn, "碳纤维上浆剂", METHOD_OWRK, [WATER, DIIODOMETHANE])
    mid2 = create_measurement(db_conn, "环氧树脂", METHOD_OWRK, [WATER, DIIODOMETHANE])
    rows = list_measurements(db_conn)
    assert {r["id"] for r in rows} == {mid1, mid2}
    assert {r["point_count"] for r in rows} == {2}
    assert [r["id"] for r in list_measurements(db_conn, keyword="环氧")] == [mid2]
    assert len(list_measurements(db_conn, method=METHOD_OWRK)) == 2


def test_invalid_inputs(db_conn):
    with pytest.raises(ValueError, match="样品名称"):
        create_measurement(db_conn, "  ", METHOD_OWRK, [WATER, DIIODOMETHANE])
    with pytest.raises(ValueError):
        create_measurement(db_conn, "X", "bad_method", [WATER, DIIODOMETHANE])
    with pytest.raises(ValueError, match="至少需要"):
        create_measurement(db_conn, "X", METHOD_OWRK, [WATER])


def test_unknown_id_raises(db_conn):
    with pytest.raises(ValueError, match="不存在"):
        get_measurement(db_conn, 999)


def test_liquid_library_seeded(db_conn):
    liquids = list_liquids(db_conn)
    names = {l["name"] for l in liquids}
    assert {"水", "二碘甲烷", "乙二醇", "甘油", "甲酰胺",
            "α-溴萘", "十六烷", "苯甲醇"} <= names
    assert len(liquids) >= 8
    assert all(l["builtin"] == 1 for l in liquids if l["name"] in names)


def test_add_custom_liquid(db_conn):
    lid = add_liquid(db_conn, "自定义液体X", 40.0, 30.0, 10.0)
    assert lid > 0
    names = {l["name"] for l in list_liquids(db_conn)}
    assert "自定义液体X" in names


def test_add_liquid_validation(db_conn):
    with pytest.raises(ValueError, match="已存在"):
        add_liquid(db_conn, "水", 72.8, 21.8, 51.0)
    with pytest.raises(ValueError, match="正数"):
        add_liquid(db_conn, "坏液体", 0.0, 1.0, 1.0)
    with pytest.raises(ValueError, match="分量之和"):
        add_liquid(db_conn, "坏液体2", 40.0, 30.0, 20.0)
    with pytest.raises(ValueError, match="名称"):
        add_liquid(db_conn, "  ", 40.0, 30.0, 10.0)


def test_add_nonpolar_liquid_with_zero_polar(db_conn):
    # 非极性液体（极性分量为 0）应能加入库，与内置库（二碘甲烷等）一致
    lid = add_liquid(db_conn, "正十二烷", 25.4, 25.4, 0.0)
    assert lid > 0
    liquids = {l["name"]: l for l in list_liquids(db_conn)}
    assert liquids["正十二烷"]["gamma_p"] == 0.0
