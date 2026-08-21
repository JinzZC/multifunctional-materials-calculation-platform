"""core/weibull.py 测试。"""

import math
import warnings

import numpy as np
import pytest

from fiber_tensile.core.weibull import (
    median_ranks,
    plotting_positions,
    weibull_fit,
    weibull_fit_3p,
    weibull_fit_mle,
)


def test_median_ranks():
    assert median_ranks(4) == pytest.approx([0.125, 0.375, 0.625, 0.875])
    assert median_ranks(2) == pytest.approx([0.25, 0.75])


def test_plotting_position_methods():
    assert plotting_positions(4, "hazen") == pytest.approx([0.125, 0.375, 0.625, 0.875])
    assert plotting_positions(4, "mean_rank") == pytest.approx([0.2, 0.4, 0.6, 0.8])
    assert plotting_positions(4, "benard") == pytest.approx(
        [(i - 0.3) / 4.4 for i in range(1, 5)])
    assert plotting_positions(4, "blom") == pytest.approx(
        [(i - 0.375) / 4.25 for i in range(1, 5)])
    with pytest.raises(ValueError, match="未知"):
        plotting_positions(4, "invalid")


def test_origin_compatible_regression_from_user_dataset():
    """用用户的 30 个原始强力锁定 Origin Mean Rank 复现结果。"""
    strengths = [
        7.9948261, 8.7058648, 9.5925353, 9.8672293, 10.2418341,
        10.315311, 10.6747173, 10.9676309, 11.3073803, 11.6906174,
        11.7233329, 11.7986359, 12.050537, 12.9041731, 13.0018219,
        13.0114347, 13.0813301, 13.3777604, 13.3815527, 14.0973866,
        14.3221736, 14.6102726, 15.9069508, 16.185455, 16.4450139,
        17.3650101, 17.5802946, 17.7544311, 19.9730173, 21.6461375,
    ]
    origin = weibull_fit(strengths, "mean_rank")
    existing = weibull_fit(strengths, "hazen")
    assert origin.m == pytest.approx(4.5584510733, rel=1e-10)
    assert existing.m == pytest.approx(5.0096934453, rel=1e-10)
    assert origin.rank_method == "mean_rank"


def test_rank_method_propagates_to_mle_and_3p():
    strengths = [8.0, 9.2, 10.1, 11.5, 13.0, 15.4]
    mle = weibull_fit_mle(strengths, "mean_rank")
    three_p = weibull_fit_3p(strengths, "benard")
    assert mle.rank_method == "mean_rank"
    assert mle.median_ranks == pytest.approx(plotting_positions(6, "mean_rank"))
    assert three_p.rank_method == "benard"
    assert three_p.median_ranks == pytest.approx(plotting_positions(6, "benard"))


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


def test_mle_has_no_overflow_warning_and_is_scale_invariant():
    rng = np.random.default_rng(7)
    strengths = 3000.0 * rng.weibull(6.0, size=200)
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        base = weibull_fit_mle(strengths)
        scaled = weibull_fit_mle(strengths * 1e100)
    # 浮点数乘 1e100 再取对数本身会带来约 1e-8 量级舍入，参数应在 1e-7 内不变。
    assert scaled.m == pytest.approx(base.m, rel=1e-7)
    assert scaled.sigma0 == pytest.approx(base.sigma0 * 1e100, rel=1e-7)


def test_mle_extreme_dynamic_range_remains_finite():
    strengths = np.geomspace(1e-150, 1e150, 30)
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        result = weibull_fit_mle(strengths)
    assert math.isfinite(result.m) and result.m > 0
    assert math.isfinite(result.sigma0) and result.sigma0 > 0


def test_mle_and_3p_reject_constant_data():
    for fit in (weibull_fit_mle, weibull_fit_3p):
        with pytest.raises(ValueError, match="全部相等"):
            fit([5.0, 5.0, 5.0])
