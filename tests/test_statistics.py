"""core/statistics.py 测试。"""

import math

import numpy as np
import pytest

from fiber_tensile.core.statistics import batch_statistics


def test_basic():
    # 经典数据集 [2,4,4,4,5,5,7,9]：均值 5，样本方差 32/7
    values = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
    r = batch_statistics(values)
    assert r.n == 8
    assert r.mean == pytest.approx(5.0)
    assert r.std == pytest.approx(math.sqrt(32.0 / 7.0))
    assert r.cv_percent == pytest.approx(math.sqrt(32.0 / 7.0) / 5.0 * 100.0)
    assert r.min_val == 2.0
    assert r.max_val == 9.0


def test_single_value():
    r = batch_statistics([3.5])
    assert r.n == 1
    assert r.mean == pytest.approx(3.5)
    assert r.std is None
    assert r.cv_percent is None


def test_empty_raises():
    with pytest.raises(ValueError):
        batch_statistics([])


def test_nonpositive_raises():
    with pytest.raises(ValueError):
        batch_statistics([1.0, 0.0])
    with pytest.raises(ValueError):
        batch_statistics([1.0, -2.0])


def test_matches_numpy_ddof1():
    values = [3.1, 3.9, 4.2, 5.0, 5.8]
    r = batch_statistics(values)
    assert r.std == pytest.approx(np.std(values, ddof=1))
    assert r.cv_percent == pytest.approx(np.std(values, ddof=1) / np.mean(values) * 100.0)
