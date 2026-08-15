"""surface_energy/core.py 计算方法测试。"""

import math

import numpy as np
import pytest

from fiber_tensile.surface_energy.core import (
    METHOD_FOWKES,
    METHOD_OWRK,
    METHOD_WU,
    METHOD_ZISMAN,
    METHODS,
    LiquidPoint,
    compute_owrk,
    compute_surface_energy,
    compute_wu,
    get_method_spec,
)

# 锚点液体对（PTFE 常见算例）：水 θ=108°，二碘甲烷 θ=77°
WATER = LiquidPoint("水", 72.8, 108.0, gamma_d=21.8, gamma_p=51.0)
DIIODOMETHANE = LiquidPoint("二碘甲烷", 50.8, 77.0, gamma_d=50.8, gamma_p=0.0)


def test_registry_complete():
    assert set(METHODS) == {METHOD_OWRK, METHOD_WU, METHOD_FOWKES, METHOD_ZISMAN}
    for key, spec in METHODS.items():
        assert spec.key == key and spec.label and callable(spec.compute)
        assert spec.min_points >= 1


def test_owrk_anchor_ptfe():
    # 手算推导（二碘甲烷 γ^p=0 可直接解出 x）：γ^d ≈ 19.06，γ^p ≈ 0.446
    c2 = 50.8 * (1 + math.cos(math.radians(77.0)))
    x = c2 / (2 * math.sqrt(50.8))
    c1 = 72.8 * (1 + math.cos(math.radians(108.0)))
    y = (c1 - 2 * math.sqrt(21.8) * x) / (2 * math.sqrt(51.0))
    r = compute_owrk([WATER, DIIODOMETHANE])
    assert r.gamma_d == pytest.approx(x ** 2, rel=1e-6)
    assert r.gamma_p == pytest.approx(y ** 2, rel=1e-6)
    assert r.gamma_total == pytest.approx(x ** 2 + y ** 2)
    assert r.r2 == pytest.approx(1.0, abs=1e-9)
    # 界面能与粘附功
    name, gamma_sl, wa = r.per_liquid[0]
    assert name == "水"
    assert wa == pytest.approx(72.8 * (1 + math.cos(math.radians(108.0))))
    assert gamma_sl > 0


def test_owrk_three_liquids_least_squares():
    eg = LiquidPoint("乙二醇", 48.0, 92.0, gamma_d=29.0, gamma_p=19.0)
    r2p = compute_owrk([WATER, DIIODOMETHANE])
    r3p = compute_owrk([WATER, DIIODOMETHANE, eg])
    # 三点最小二乘与两点解同量级，且 R² 在合理区间
    assert r3p.gamma_total > 0
    assert 0.0 <= r3p.r2 <= 1.0
    assert abs(r3p.gamma_total - r2p.gamma_total) / r2p.gamma_total < 0.5


def test_owrk_negative_root_raises():
    # 两个极性液体且 θ 均很大 → 可能出现负根
    bad1 = LiquidPoint("水", 72.8, 160.0, gamma_d=21.8, gamma_p=51.0)
    bad2 = LiquidPoint("甘油", 64.0, 150.0, gamma_d=34.0, gamma_p=30.0)
    with pytest.raises(ValueError, match="负的平方根"):
        compute_owrk([bad1, bad2])


def test_wu_self_consistency():
    """Wu 法结果代回调和平均方程，残差应接近 0。"""
    r = compute_wu([WATER, DIIODOMETHANE])
    assert r.gamma_d > 0 and r.gamma_p > 0
    for p in (WATER, DIIODOMETHANE):
        lhs = p.gamma_total * (1 + math.cos(math.radians(p.angle_deg)))
        rhs = (4 * r.gamma_d * p.gamma_d / (r.gamma_d + p.gamma_d)
               + 4 * r.gamma_p * p.gamma_p / (r.gamma_p + p.gamma_p))
        assert lhs == pytest.approx(rhs, abs=1e-6)


def test_wu_all_nonpolar():
    hexa = LiquidPoint("十六烷", 27.6, 46.0, gamma_d=27.6, gamma_p=0.0)
    r = compute_wu([DIIODOMETHANE, hexa])
    assert r.gamma_p == pytest.approx(0.0)
    assert r.gamma_d > 0


def test_fowkes_anchor():
    # 十六烷 θ=46°：γ^d = (27.6×(1+cos46°))²/(4×27.6)
    hexa = LiquidPoint("十六烷", 27.6, 46.0, gamma_d=27.6, gamma_p=0.0)
    r = compute_surface_energy(METHOD_FOWKES, [hexa])
    expected = (27.6 * (1 + math.cos(math.radians(46.0)))) ** 2 / (4 * 27.6)
    assert r.gamma_d == pytest.approx(expected, rel=1e-9)
    assert r.gamma_total == pytest.approx(expected)
    assert r.gamma_p is None


def test_fowkes_point_count_enforced():
    hexa = LiquidPoint("十六烷", 27.6, 46.0, gamma_d=27.6, gamma_p=0.0)
    with pytest.raises(ValueError, match="最多允许 1 种"):
        compute_surface_energy(METHOD_FOWKES, [hexa, hexa])


def test_zisman_synthetic():
    # 构造严格线性数据：cosθ = 1.4 − 0.02·γ_L → γ_c = 20
    points = []
    for gamma_l in (30.0, 40.0, 50.0, 60.0, 70.0):
        cos_theta = 1.4 - 0.02 * gamma_l
        points.append(LiquidPoint(
            f"液体{gamma_l:g}", gamma_l, math.degrees(math.acos(cos_theta))))
    r = compute_surface_energy(METHOD_ZISMAN, points)
    assert r.gamma_c == pytest.approx(20.0, rel=1e-9)
    assert r.r2 == pytest.approx(1.0, abs=1e-9)


def test_zisman_flat_data_raises():
    points = [LiquidPoint("A", 30.0, 60.0), LiquidPoint("B", 40.0, 60.0)]
    with pytest.raises(ValueError, match="斜率"):
        compute_surface_energy(METHOD_ZISMAN, points)


def test_min_points_enforced():
    with pytest.raises(ValueError, match="至少需要 2 种"):
        compute_surface_energy(METHOD_OWRK, [WATER])
    with pytest.raises(ValueError, match="至少需要 2 种"):
        compute_surface_energy(METHOD_ZISMAN, [LiquidPoint("A", 30.0, 60.0)])


def test_angle_validation():
    bad = LiquidPoint("水", 72.8, 180.0, gamma_d=21.8, gamma_p=51.0)
    with pytest.raises(ValueError, match="0–180"):
        compute_surface_energy(METHOD_OWRK, [WATER, bad])
    bad2 = LiquidPoint("水", 72.8, 0.0, gamma_d=21.8, gamma_p=51.0)
    with pytest.raises(ValueError, match="0–180"):
        compute_surface_energy(METHOD_OWRK, [WATER, bad2])


def test_components_validation():
    bad = LiquidPoint("水", 72.8, 108.0, gamma_d=40.0, gamma_p=40.0)   # 分量和 > 总量
    with pytest.raises(ValueError, match="分量之和"):
        compute_surface_energy(METHOD_OWRK, [bad, DIIODOMETHANE])


def test_missing_components_raises():
    no_comp = LiquidPoint("自定义", 50.0, 80.0)
    with pytest.raises(ValueError, match="γ\\^d"):
        compute_surface_energy(METHOD_OWRK, [no_comp, DIIODOMETHANE])


def test_unknown_method_raises():
    with pytest.raises(ValueError):
        get_method_spec("foobar")
    with pytest.raises(ValueError):
        compute_surface_energy("foobar", [WATER, DIIODOMETHANE])


def test_method_equations_present():
    for key, spec in METHODS.items():
        assert spec.equations.strip(), f"{key} 缺少公式展示文本"


def test_steps_generated_for_all_methods():
    r_owrk = compute_owrk([WATER, DIIODOMETHANE])
    assert any("最小二乘" in s for s in r_owrk.steps)
    assert any("总表面能" in s for s in r_owrk.steps)

    r_wu = compute_wu([WATER, DIIODOMETHANE])
    assert any("迭代" in s for s in r_wu.steps)
    assert any("残差" in s for s in r_wu.steps)

    hexa = LiquidPoint("十六烷", 27.6, 46.0, gamma_d=27.6, gamma_p=0.0)
    r_fowkes = compute_surface_energy(METHOD_FOWKES, [hexa])
    assert any("公式" in s for s in r_fowkes.steps)

    pts = [LiquidPoint(f"液{g:g}", g, math.degrees(math.acos(1.4 - 0.02 * g)))
           for g in (30.0, 40.0, 50.0)]
    r_z = compute_surface_energy(METHOD_ZISMAN, pts)
    assert any("线性回归" in s for s in r_z.steps)
    assert any("临界表面张力" in s for s in r_z.steps)


def test_wu_per_liquid_uses_harmonic_formula():
    """Wu 法的界面能应按调和平均公式计算（而非 OWRK 几何平均）。"""
    r = compute_wu([WATER, DIIODOMETHANE])
    for p, (name, gamma_sl, _) in zip([WATER, DIIODOMETHANE], r.per_liquid):
        expected = (r.gamma_d + r.gamma_p + p.gamma_total
                    - 4 * r.gamma_d * p.gamma_d / (r.gamma_d + p.gamma_d)
                    - 4 * r.gamma_p * p.gamma_p / (r.gamma_p + p.gamma_p))
        assert gamma_sl == pytest.approx(expected, rel=1e-9)
    # 与 OWRK 几何平均公式的结果应不同（公式不同）
    r_owrk = compute_owrk([WATER, DIIODOMETHANE])
    assert r.per_liquid[0][1] != pytest.approx(r_owrk.per_liquid[0][1])
