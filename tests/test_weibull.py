"""core/weibull.py 测试。"""

import math

import numpy as np
import pytest

from fiber_tensile.core.weibull import median_ranks, weibull_fit


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
