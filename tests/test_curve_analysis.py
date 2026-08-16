"""curve_analysis/core.py 单丝曲线分析（平台校正）测试。"""

import math

import numpy as np
import pytest

from fiber_tensile.curve_analysis.core import analyze_curve

GAUGE_MM = 25.0
DIAMETER_UM = 5.4


def _area():
    return math.pi * (DIAMETER_UM * 1e-6) ** 2 / 4.0


def _make_curve(toe_mm=0.5, e_true_gpa=230.0, eps_b_pct=1.8, n=200, seed=42):
    """合成曲线：起始 toe_mm 平台（只伸长不增力），随后线弹性到断裂。"""
    rng = np.random.default_rng(seed)
    k = e_true_gpa * 1e9 * _area() / (GAUGE_MM / 1000.0) / 1000.0   # N/mm
    x_break = toe_mm + eps_b_pct / 100.0 * GAUGE_MM
    x = np.linspace(0.0, x_break, n)
    f = np.where(x <= toe_mm, 0.0, k * (x - toe_mm))
    f = f + rng.normal(0.0, 1e-5, n)    # 微小噪声
    return x, np.maximum(f, 0.0)


def test_toe_correction_recovers_true_values():
    x, f = _make_curve(toe_mm=0.5, e_true_gpa=230.0, eps_b_pct=1.8)
    r = analyze_curve(x, f, DIAMETER_UM, GAUGE_MM)
    assert r.e_gpa == pytest.approx(230.0, rel=1e-3)
    assert r.elongation_pct == pytest.approx(1.8, rel=1e-3)
    assert r.toe_disp_mm == pytest.approx(0.5, rel=1e-3)
    assert r.toe_eps_pct == pytest.approx(0.5 / GAUGE_MM * 100, rel=1e-3)
    assert r.r2 == pytest.approx(1.0, abs=1e-4)
    # 断裂强度 = k×(断裂位移−平台)/面积
    expected_sigma = 230e9 * 1.8 / 100 * 1e-6   # E × ε_b = σ
    assert r.strength_mpa == pytest.approx(expected_sigma, rel=1e-3)


def test_no_toe_curve():
    x, f = _make_curve(toe_mm=0.0, eps_b_pct=2.0)
    r = analyze_curve(x, f, DIAMETER_UM, GAUGE_MM)
    assert r.toe_disp_mm == pytest.approx(0.0, abs=1e-3)
    assert r.elongation_pct == pytest.approx(2.0, rel=1e-3)


def test_large_toe_is_fully_corrected():
    # 平台 2 mm + 真实伸长 1%：校正后应为 1%
    x, f = _make_curve(toe_mm=2.0, eps_b_pct=1.0)
    r = analyze_curve(x, f, DIAMETER_UM, GAUGE_MM)
    assert r.elongation_pct == pytest.approx(1.0, rel=1e-3)
    assert r.toe_disp_mm == pytest.approx(2.0, rel=1e-3)


def test_steps_present():
    x, f = _make_curve()
    r = analyze_curve(x, f, DIAMETER_UM, GAUGE_MM)
    assert any("平台" in s for s in r.steps)
    assert any("断裂伸长率" in s for s in r.steps)
    assert any("弹性模量" in s for s in r.steps)


def test_validation_errors():
    with pytest.raises(ValueError, match="点不足"):
        analyze_curve([1, 2], [1, 2], DIAMETER_UM, GAUGE_MM)
    with pytest.raises(ValueError, match="直径"):
        analyze_curve([1, 2, 3, 4, 5], [1, 2, 3, 4, 5], 0.0, GAUGE_MM)
    with pytest.raises(ValueError, match="拟合区间"):
        analyze_curve([1, 2, 3, 4, 5], [1, 2, 3, 4, 5], DIAMETER_UM, GAUGE_MM,
                      fit_lo=0.8, fit_hi=0.5)
    # 拟合区间太窄（点数不足）
    x = np.linspace(0, 1, 10)
    f = np.linspace(0, 1, 10)
    with pytest.raises(ValueError, match="区间内数据点不足"):
        analyze_curve(x, f, DIAMETER_UM, GAUGE_MM, fit_lo=0.4, fit_hi=0.5)


def test_negative_force_rejected():
    with pytest.raises(ValueError, match="不能为负"):
        analyze_curve(np.linspace(0, 1, 6), np.array([0, 0.1, 0.2, -0.1, 0.4, 0.5]),
                      DIAMETER_UM, GAUGE_MM)


def test_all_equal_force_message():
    with pytest.raises(ValueError, match="全部相等"):
        analyze_curve(np.linspace(0, 1, 6), np.ones(6), DIAMETER_UM, GAUGE_MM)


def test_plateau_break_takes_last_max():
    """峰值保持平台：断裂点取平台终点，伸长率按平台终点计。"""
    toe = 0.5
    k = 230e9 * _area() / (GAUGE_MM / 1000.0) / 1000.0
    x_rise = toe + 0.01 * GAUGE_MM          # 上升段结束（真实应变 1%）
    f_peak = k * (x_rise - toe)
    # 上升段 + 峰值保持平台（3 个点力相同）→ 平台终点应变 1.5%
    x = np.concatenate([
        np.linspace(0.0, x_rise, 100),
        np.linspace(x_rise, x_rise + 0.005 * GAUGE_MM, 3),
    ])
    f = np.concatenate([np.where(np.linspace(0, x_rise, 100) <= toe, 0.0,
                                 k * (np.linspace(0, x_rise, 100) - toe)),
                        np.full(3, f_peak)])
    r = analyze_curve(x, f, DIAMETER_UM, GAUGE_MM)
    assert r.elongation_pct == pytest.approx(1.5, rel=1e-3)
    assert r.strength_mpa == pytest.approx(f_peak / _area() / 1e6, rel=1e-3)
