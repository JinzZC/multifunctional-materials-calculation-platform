"""plotting.py 测试：拟合图包含直线方程标注。"""

import math

import matplotlib.pyplot as plt
import numpy as np

from fiber_tensile.core.models import WeibullResult
from fiber_tensile.core.weibull import median_ranks, weibull_fit
from fiber_tensile.plotting import build_weibull_figure, fit_equation_text


def _make_result(m0=6.0, sigma0=3200.0, n=20):
    f = np.asarray(median_ranks(n))
    strengths = sigma0 * (-np.log(1.0 - f)) ** (1.0 / m0)
    return weibull_fit(strengths.tolist())


def _figure_texts(fig):
    texts = []
    for ax in fig.axes:
        texts += [t.get_text() for t in ax.texts]
    return texts


def test_fit_equation_text_formula():
    w = _make_result()
    a = -w.m * math.log(w.sigma0)
    assert fit_equation_text(w) == f"$y = {w.m:.4f}x - {abs(a):.4f}$"


def test_fit_equation_text_positive_intercept():
    # σ₀ < 1 时 a = −m·ln(σ₀) > 0，应显示加号
    w = WeibullResult(m=2.0, sigma0=0.5, r2=1.0, strengths_sorted=[], median_ranks=[], x=[], y=[])
    assert fit_equation_text(w) == "$y = 2.0000x + 1.3863$"


def test_single_series_equation_annotated():
    w = _make_result()
    fig = build_weibull_figure([w], labels=["批次A"], sigma0_unit="MPa")
    try:
        texts = _figure_texts(fig)
        a = -w.m * math.log(w.sigma0)
        expected = f"$y = {w.m:.4f}x - {abs(a):.4f}$"
        assert any(expected in t for t in texts)
        assert any("拟合直线方程" in t for t in texts)
        assert any(r"$x = \ln\sigma$" in t for t in texts)     # 坐标含义说明
    finally:
        plt.close(fig)


def test_multi_series_equations_annotated():
    w1, w2 = _make_result(5.0, 3000.0), _make_result(8.0, 3400.0)
    fig = build_weibull_figure([w1, w2], labels=["甲", "乙"])
    try:
        texts = _figure_texts(fig)
        assert any("甲" in t and f"y = {w1.m:.4f}x" in t for t in texts)
        assert any("乙" in t and f"y = {w2.m:.4f}x" in t for t in texts)
    finally:
        plt.close(fig)
