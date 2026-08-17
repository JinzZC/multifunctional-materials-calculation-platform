"""core/weibull.py 测试。"""

import math

import numpy as np
import pytest

from fiber_tensile.core.weibull import (
    median_ranks,
    weibull_fit,
    weibull_fit_3p,
    weibull_fit_mle,
)


def test_median_ranks():
    assert median_ranks(4) == pytest.approx([0.125, 0.375, 0.625, 0.875])
    assert median_ranks(2) == pytest.approx([0.25, 0.75])


def test_inverse_construction_roundtrip():
    # 逆构造：给定 m0、σ0，按 σᵢ = σ0·(−ln(1−F̂ᵢ))^(1/m0) 生成数据，
    # 数据点应精确落在拟合直线上，拟合还原 m、σ0 且 R²≈1。
    m0, sigma0 = 6.0, 3200.0
    n = 20
    f = np.asarray(median_ranks(n))
    strengths = sigma0 * (-np.log(1.0 - f)) ** (1.0 / m0)

    r = weibull_fit(strengths.tolist())
    assert r.m == pytest.approx(m0, rel=1e-6)
    assert r.sigma0 == pytest.approx(sigma0, rel=1e-6)
    assert r.r2 == pytest.approx(1.0, abs=1e-6)


def test_shuffled_input_invariance():
    rng = np.random.default_rng(42)
    strengths = 3200.0 * (-np.log(1.0 - np.asarray(median_ranks(15)))) ** (1.0 / 6.0)
    perm = rng.permutation(15)

    a = weibull_fit(strengths.tolist())
    b = weibull_fit(strengths[perm].tolist())
    assert a.m == pytest.approx(b.m)
    assert a.sigma0 == pytest.approx(b.sigma0)
    assert a.strengths_sorted == sorted(strengths.tolist())


def test_n2_r2_is_one():
    # 两个点必然共线，R² 恒为 1
    r = weibull_fit([100.0, 200.0])
    assert r.r2 == pytest.approx(1.0)
    assert r.m > 0
    assert r.sigma0 > 0


def test_insufficient_data_raises():
    with pytest.raises(ValueError):
        weibull_fit([100.0])
    with pytest.raises(ValueError):
        weibull_fit([])


def test_nonpositive_raises():
    for bad in ([100.0, 0.0], [100.0, -5.0], [100.0, float("nan")], [100.0, float("inf")]):
        with pytest.raises(ValueError):
            weibull_fit(bad)


def test_all_equal_raises():
    # 全部相等 → 斜率 0 → 无法拟合
    with pytest.raises(ValueError):
        weibull_fit([50.0, 50.0, 50.0])


def test_matches_manual_regression():
    # m 应等于手工线性回归的斜率，σ0 = exp(−a/m)
    strengths = [1000.0, 2000.0, 3000.0]
    r = weibull_fit(strengths)
    f = np.asarray(median_ranks(3))
    x = np.log(np.asarray(strengths))
    y = np.log(-np.log(1.0 - f))
    slope, intercept = np.polyfit(x, y, 1)
    assert r.m == pytest.approx(slope)
    assert r.sigma0 == pytest.approx(math.exp(-intercept / slope))


def test_median_rank_bounds():
    # median rank 天然落在 (0, 1) 内，无 0/1 取对数问题
    ranks = median_ranks(50)
    assert all(0.0 < f < 1.0 for f in ranks)


def test_mle_recovers_known_params():
    """MLE 应能从已知 (m, σ₀) 的合成数据中恢复参数。"""
    rng = np.random.default_rng(7)
    strengths = 3000.0 * rng.weibull(6.0, size=200)
    r = weibull_fit_mle(strengths)
    assert r.m == pytest.approx(6.0, rel=0.12)
    assert r.sigma0 == pytest.approx(3000.0, rel=0.05)
    assert r.gamma == 0.0
    assert 0.0 <= r.r2 <= 1.0
    assert any("极大似然" in s for s in r.steps)


def test_mle_validation():
    with pytest.raises(ValueError):
        weibull_fit_mle([100.0])
    with pytest.raises(ValueError):
        weibull_fit_mle([100.0, -1.0])


def test_3p_fallback_honest():
    """3 参数目标对 γ 单调趋于边界（文献已知病理），应退回 2 参数并如实说明。"""
    rng = np.random.default_rng(11)
    strengths = 200.0 + 3000.0 * rng.weibull(6.0, size=200)
    r = weibull_fit_3p(strengths)
    assert r.gamma == 0.0
    assert any("退回" in s for s in r.steps)
    assert 0.0 <= r.r2 <= 1.0


def test_3p_result_consistency():
    """3 参数结果（无论退化与否）的 x 坐标必须与 γ 自洽。"""
    rng = np.random.default_rng(11)
    strengths = 200.0 + 3000.0 * rng.weibull(6.0, size=200)
    r = weibull_fit_3p(strengths)
    expected_x = [math.log(s - r.gamma) for s in r.strengths_sorted]
    assert r.x == pytest.approx(expected_x, rel=1e-9)


def test_3p_validation():
    with pytest.raises(ValueError):
        weibull_fit_3p([50.0])
    with pytest.raises(ValueError):
        weibull_fit_3p([50.0, 0.0])


def test_fit_invariance_under_unit_scaling():
    """强度单位缩放（MPa→GPa）：m 不变、σ₀ 同比例缩放、x 平移 ln(scale)。"""
    rng = np.random.default_rng(3)
    strengths = 3000.0 * rng.weibull(6.0, size=100)
    r_mpa = weibull_fit(strengths)
    r_gpa = weibull_fit([s / 1000.0 for s in strengths])
    assert r_gpa.m == pytest.approx(r_mpa.m, rel=1e-9)
    assert r_gpa.sigma0 == pytest.approx(r_mpa.sigma0 / 1000.0, rel=1e-9)
    assert r_gpa.r2 == pytest.approx(r_mpa.r2, rel=1e-9)
    assert r_gpa.x == pytest.approx(
        [x - math.log(1000.0) for x in r_mpa.x], rel=1e-9)
